#!/usr/bin/env python3
"""Configure private Tailscale Serve access for Docker or native runtimes."""
import argparse
import ipaddress
import json
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

from native import DEFAULT_GATEWAY_PORT, gateway_port, project_values, runtime_env

KIT = Path(__file__).resolve().parent.parent
SERVICES = (("openclaw", DEFAULT_GATEWAY_PORT, 8443), ("hermes", 9119, 8444))
PAPERCLIP_HTTPS_PORT = 8445
PAPERCLIP_CONFIG = KIT / "paperclip/.local/instances/team/config.json"


def paperclip_port():
    value = project_values(KIT).get("PAPERCLIP_PORT", "").strip() or "3100"
    if not value.isdigit():
        raise ValueError("PAPERCLIP_PORT in .env must be a TCP port.")
    return int(value)


def selected_services(mode, with_paperclip=False):
    """Local listeners and their HTTPS ports; Docker publishes the Gateway on the default port."""
    openclaw = DEFAULT_GATEWAY_PORT if mode == "docker" else gateway_port(KIT)
    services = [("openclaw", openclaw, 8443), ("hermes", 9119, 8444)]
    if with_paperclip:
        services.append(("paperclip", paperclip_port(), PAPERCLIP_HTTPS_PORT))
    return tuple(services)


def check_paperclip(health, config, hostname):
    """Paperclip may only be served when it requires login and knows the browser hostname."""
    if not health or health.get("status") != "ok":
        raise ValueError("Start Paperclip first; its health endpoint did not answer.")
    if health.get("deploymentMode") != "authenticated":
        raise ValueError("Paperclip runs in local_trusted mode, where every visitor would be the board. "
                         "Run `python3 paperclip/instance.py secure --allow-host " + hostname + "`, restart it, then rerun.")
    server = (config or {}).get("server", {})
    allowed = [h.lower() for h in server.get("allowedHostnames", [])]
    if hostname.lower() not in allowed or server.get("bind", "loopback") != "loopback":
        raise ValueError("Paperclip must allow this Tailscale hostname and stay on loopback; "
                         "run `python3 paperclip/instance.py secure --allow-host " + hostname + "` and restart it.")


def run(args, *, data=None):
    result = subprocess.run(args, cwd=KIT, input=data, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(f"{' '.join(args[:3])} failed; inspect that command locally.")
    return result.stdout


def compose(*args, data=None):
    return run(["docker", "compose", *args], data=data)


def native(service, *args, data=None):
    return run([sys.executable, str(KIT / "scripts/native.py"), service, *args], data=data)


def gateway_patch(gateway, hostname, peers, mode, port=DEFAULT_GATEWAY_PORT):
    if gateway.get("auth", {}).get("mode", "token") != "token":
        raise ValueError("Expected token authentication; existing auth was left unchanged.")
    ui = gateway.get("controlUi", {})
    if ui.get("dangerouslyDisableDeviceAuth") or ui.get("allowInsecureAuth"):
        raise ValueError("Restore normal OpenClaw device authentication before sharing it.")
    origin = f"https://{hostname}:8443"
    return {"gateway": {
        "bind": "lan" if mode == "docker" else "loopback", "port": port,
        "trustedProxies": list(dict.fromkeys([*gateway.get("trustedProxies", []), *peers])),
        "controlUi": {"allowedOrigins": list(dict.fromkeys([*ui.get("allowedOrigins", []), origin]))},
        "auth": {"mode": "token", "allowTailscale": False}, "tailscale": {"mode": "off"},
    }}


def check_native_settings(gateway, dashboard, hostname, port=DEFAULT_GATEWAY_PORT):
    origin = f"https://{hostname}:8443"
    ui = gateway.get("controlUi", {})
    valid = (gateway.get("bind") == "loopback" and gateway.get("port") == port
             and gateway.get("auth", {}).get("mode") == "token"
             and gateway.get("auth", {}).get("allowTailscale") is False
             and gateway.get("tailscale", {}).get("mode") == "off"
             and origin in ui.get("allowedOrigins", [])
             and {"127.0.0.1", "::1"}.issubset(gateway.get("trustedProxies", []))
             and dashboard.get("public_url") == f"https://{hostname}:8444"
             and {"127.0.0.1", "::1"}.issubset(dashboard.get("trusted_proxies", [])))
    if not valid:
        raise ValueError("Run --mode native --configure-only, restart both native servers, then rerun --mode native.")


def serve(hostname, services=SERVICES):
    for service, local_port, https_port in services:
        # Let the CLI display HTTPS-enablement instructions for a new tailnet.
        command = ["tailscale", "serve", "--bg", "--yes", f"--https={https_port}", f"http://127.0.0.1:{local_port}"]
        if subprocess.run(command, cwd=KIT).returncode:
            raise RuntimeError("Tailscale Serve did not start; follow its message above, then rerun.")
        print(f"{service}: https://{hostname}:{https_port}")


def socket_peers(text, port):
    """Read Linux's little-endian address words, including IPv4-mapped IPv6."""
    peers = set()
    for line in text.splitlines():
        fields = line.split()
        if len(fields) < 4 or fields[3] != "01":
            continue
        if int(fields[1].split(":")[1], 16) != port:
            continue
        address, remote_port = fields[2].split(":")
        raw = bytes.fromhex(address)
        packed = b"".join(raw[n:n + 4][::-1] for n in range(0, len(raw), 4))
        ip = ipaddress.ip_address(packed)
        peers.add((str(getattr(ip, "ipv4_mapped", None) or ip), int(remote_port, 16)))
    return peers


def discover_peer(service, port):
    probe = "from pathlib import Path; print('\\n'.join(Path(p).read_text() for p in ('/proc/net/tcp','/proc/net/tcp6') if Path(p).exists()))"
    def snapshot():
        return socket_peers(compose("exec", "-T", service, "python3", "-c", probe), port)
    before = snapshot()
    # Use the same host-published target as Serve; keep this socket open while inspecting it.
    with socket.create_connection(("127.0.0.1", port), timeout=5):
        addresses = {ip for ip, _ in snapshot() - before}
    if len(addresses) != 1:
        raise ValueError(f"Could not identify one incoming proxy peer for {service}; retry when idle.")
    return addresses.pop()


def check_routes(config, hostname, services=SERVICES):
    for _, local_port, https_port in services:
        port, endpoint = str(https_port), f"{hostname}:{https_port}"
        expected = {"Handlers": {"/": {"Proxy": f"http://127.0.0.1:{local_port}"}}}
        tcp, web = config.get("TCP", {}), config.get("Web", {})
        on_port = {key: value for key, value in web.items() if key.rsplit(":", 1)[-1] == port}
        if (port in tcp or on_port) and (tcp.get(port) != {"HTTPS": True} or on_port != {endpoint: expected}):
            raise ValueError(f"Tailscale port {port} already has another route; it was left unchanged.")
        if config.get("AllowFunnel", {}).get(endpoint):
            raise ValueError(f"Tailscale port {port} has Funnel enabled; review that route first.")
        for foreground in config.get("Foreground", {}).values():
            if port in foreground.get("TCP", {}):
                raise ValueError(f"Tailscale port {port} belongs to a foreground service.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("docker", "native"), default="docker")
    parser.add_argument("--configure-only", action="store_true", help="Configure native apps before starting them; do not create Serve routes.")
    parser.add_argument("--with-paperclip", action="store_true", help="Also serve the Paperclip console on HTTPS 8445 (native, authenticated mode only).")
    args = parser.parse_args()
    if args.configure_only and args.mode != "native":
        raise ValueError("--configure-only applies to native runtimes.")
    if args.with_paperclip and args.mode != "native":
        raise ValueError("--with-paperclip applies to the native route; see README-paperclip.md for Docker.")
    services = selected_services(args.mode, args.with_paperclip)
    if not (KIT / ".env").is_file():
        raise ValueError("Run python3 docker/init.py env or python3 scripts/native.py init first.")
    status = json.loads(run(["tailscale", "status", "--json"]))
    own = status.get("Self") or {}
    hostname = str(own.get("DNSName", "")).rstrip(".")
    if status.get("BackendState") != "Running" or not own.get("Online"):
        raise ValueError("Open Tailscale and sign in on this host first.")
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]*\.ts\.net", hostname):
        raise ValueError("Tailscale has not supplied a usable DNS name.")
    check_routes(json.loads(run(["tailscale", "serve", "status", "--json"])) or {}, hostname, services)
    if args.mode == "docker":
        running = set(compose("ps", "--status", "running", "--services").split())
        if not {"openclaw", "hermes"}.issubset(running):
            raise ValueError("Start both services with docker compose up -d first.")
        peers = {service: discover_peer(service, port) for service, port, _ in SERVICES}
        gateway = json.loads(compose("exec", "-T", "openclaw", "openclaw", "config", "get", "gateway", "--json"))
        patch = gateway_patch(gateway, hostname, [peers["openclaw"]], "docker")
    else:
        runtime_env("openclaw")
        runtime_env("hermes")
        gateway = json.loads(native("openclaw", "config", "get", "gateway", "--json"))
        port = gateway_port(KIT)
        patch = gateway_patch(gateway, hostname, ["127.0.0.1", "::1"], "native", port)
        if args.configure_only:
            with tempfile.TemporaryDirectory(dir=KIT / ".local") as scratch:
                path = Path(scratch) / "gateway.patch.json"
                path.write_text(json.dumps(patch))
                native("openclaw", "config", "patch", "--file", str(path))
            native("hermes", "config", "set", "dashboard.public_url", f"https://{hostname}:8444")
            native("hermes", "config", "set", "dashboard.trusted_proxies", '["127.0.0.1", "::1"]')
            print("Native settings ready. Start both servers, then run this helper with --mode native.")
            return
        dashboard = json.loads(native("hermes", "config", "get", "dashboard", "--json"))
        check_native_settings(gateway, dashboard, hostname, port)
        for service, local_port, _ in services:
            path = "/healthz" if service == "openclaw" else "/api/health"
            with urllib.request.urlopen(f"http://127.0.0.1:{local_port}{path}", timeout=5) as response:
                if response.status != 200:
                    raise ValueError("Start the native servers as described in README-native.md first.")
        if args.with_paperclip:
            with urllib.request.urlopen(f"http://127.0.0.1:{paperclip_port()}/api/health", timeout=5) as response:
                health = json.load(response)
            config = json.loads(PAPERCLIP_CONFIG.read_text()) if PAPERCLIP_CONFIG.is_file() else {}
            check_paperclip(health, config, hostname)
        try:
            urllib.request.urlopen("http://127.0.0.1:9119/api/auth-check", timeout=5).close()
        except urllib.error.HTTPError as error:
            if error.code != 401:
                raise ValueError("Hermes did not require login; restart its project-local dashboard before sharing it.")
        else:
            raise ValueError("Hermes did not require login; restart its project-local dashboard before sharing it.")
        serve(hostname, services)
        return
    # The CLI merges this small patch and validates it; other settings and secrets stay intact.
    apply_patch = """import os, subprocess, sys, tempfile
fd, path = tempfile.mkstemp(suffix='.json')
try:
    with os.fdopen(fd, 'w') as out: out.write(sys.stdin.read())
    subprocess.run(['openclaw', 'config', 'patch', '--file', path], check=True)
finally:
    os.unlink(path)
"""
    compose("exec", "-T", "openclaw", "python3", "-c", apply_patch, data=json.dumps(patch))
    update_hermes = """import json, os, pathlib, sys, tempfile, yaml
values = json.load(sys.stdin)
path = pathlib.Path('/opt/data/config.yaml')
config = yaml.safe_load(path.read_text()) or {}
dashboard = config.setdefault('dashboard', {})
dashboard['public_url'] = values['url']
dashboard['trusted_proxies'] = list(dict.fromkeys([*dashboard.get('trusted_proxies', []), values['peer']]))
fd, temporary = tempfile.mkstemp(dir=path.parent, suffix='.yaml')
try:
    with os.fdopen(fd, 'w') as out: yaml.safe_dump(config, out, sort_keys=False, allow_unicode=True)
    os.replace(temporary, path)
finally:
    if os.path.exists(temporary): os.unlink(temporary)
"""
    compose("exec", "-T", "--user", "hermes", "hermes", "python3", "-c", update_hermes,
            data=json.dumps({"url": f"https://{hostname}:8444", "peer": peers["hermes"]}))
    compose("restart", "openclaw", "hermes")
    serve(hostname)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
        sys.exit(f"Stopped: {error}")
