#!/usr/bin/env python3
"""Create, run, secure and supervise this checkout's Paperclip instance."""
import argparse
import json
import os
from pathlib import Path
import plistlib
import re
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "scripts"))
import run  # noqa: E402
from native import service_label  # noqa: E402

HOSTNAME = re.compile(r"^(?=.{1,253}$)[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*$")


def port_open(port):
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def health(timeout=3):
    try:
        with urllib.request.urlopen(run.base_url() + "/api/health", timeout=timeout) as response:
            return json.load(response)
    except (OSError, ValueError):
        return None


def wait_for_health(seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        data = health(2)
        if data and data.get("status") == "ok":
            return data
        time.sleep(0.5)
    return None


def read_config():
    if not run.CONFIG.is_file():
        raise ValueError("No instance yet; run `python3 paperclip/instance.py init` first.")
    return json.loads(run.CONFIG.read_text())


def write_config(data):
    temporary = run.CONFIG.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n")
    temporary.chmod(0o600)
    temporary.replace(run.CONFIG)


def apply_ports(data):
    """Keep the instance on the ports selected in .env; onboarding writes the defaults."""
    changed = False
    server = data.setdefault("server", {})
    database = data.setdefault("database", {})
    if server.get("port") != run.port():
        server["port"] = run.port()
        changed = True
    if database.get("mode") == "embedded-postgres" and database.get("embeddedPostgresPort") != run.db_port():
        database["embeddedPostgresPort"] = run.db_port()
        changed = True
    return changed


def init():
    if health():
        raise ValueError(f"Something already answers on {run.base_url()}; choose PAPERCLIP_PORT in .env or stop it.")
    if run.CONFIG.is_file():
        data = read_config()
        if apply_ports(data):
            write_config(data)
            print("Existing instance kept; ports updated from .env. Restart it to apply them.")
        else:
            print("Existing instance kept; nothing to initialize.")
        return
    env = run.environment()
    env["PORT"] = str(run.port())
    env["PAPERCLIP_EMBEDDED_POSTGRES_PORT"] = str(run.db_port())
    run.PRIVATE.mkdir(mode=0o700, exist_ok=True)
    # Quickstart onboarding starts a foreground server; stop it once it is healthy.
    with (run.PRIVATE / "onboard.log").open("a") as log:
        child = subprocess.Popen([*run.command(env), "onboard", "--yes", "--no-install-service"],
                                 cwd=ROOT, env=env, stdout=log, stderr=log, stdin=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 180
            ready = None
            while time.monotonic() < deadline and child.poll() is None:
                if run.CONFIG.is_file():
                    data = read_config()
                    if apply_ports(data):
                        # The wizard may have ignored the port variables; apply them and restart below.
                        write_config(data)
                        break
                ready = health(2)
                if ready and ready.get("status") == "ok":
                    break
                time.sleep(1)
            if child.poll() is not None:
                raise ValueError("Onboarding exited early; inspect paperclip/.local/onboard.log.")
            if not run.CONFIG.is_file():
                raise ValueError("Onboarding did not write an instance config; inspect paperclip/.local/onboard.log.")
        finally:
            child.send_signal(signal.SIGINT)
            try:
                child.wait(timeout=30)
            except subprocess.TimeoutExpired:
                child.terminate()
                child.wait(timeout=10)
    data = read_config()
    apply_ports(data)
    data.setdefault("telemetry", {})["enabled"] = False
    data.setdefault("updates", {})["checkEnabled"] = False
    write_config(data)
    print(f"Paperclip instance ready in {run.CONFIG.parent}. Mode: {data['server'].get('deploymentMode')}; "
          f"port {run.port()}; embedded PostgreSQL port {run.db_port()}.")
    print("Start it with `python3 paperclip/instance.py run` or the macOS service commands.")


def run_foreground():
    env = run.environment()
    os.chdir(ROOT)
    os.execve(run.command(env)[0], [*run.command(env), "run", "--instance", run.INSTANCE], env)


def secure(hosts):
    """Require login and limit browser access to named hostnames before any remote exposure."""
    data = read_config()
    server = data.setdefault("server", {})
    allowed = [h.strip().lower() for h in server.get("allowedHostnames", [])]
    for host in hosts:
        host = host.strip().lower().split(":")[0]
        if not HOSTNAME.match(host):
            raise ValueError(f"Not a hostname: {host}")
        if host not in allowed:
            allowed.append(host)
    server.update({"deploymentMode": "authenticated", "exposure": "private", "bind": "loopback",
                   "host": "127.0.0.1", "allowedHostnames": allowed})
    data.setdefault("auth", {})["disableSignUp"] = False
    write_config(data)
    print("Authenticated mode configured; the API now rejects anonymous requests.")
    print("Restart Paperclip, then create the first administrator with")
    print(f"  python3 paperclip/run.py auth bootstrap-ceo --force --base-url https://{allowed[0] if allowed else 'HOST.TAILNET.ts.net'}:8445")
    print("(--force replaces the quickstart's local admin). Set auth.disableSignUp to true once your accounts exist.")


def plist_path(label):
    return Path.home() / "Library/LaunchAgents" / (label + ".plist")


def launch(*args):
    return subprocess.run(["/bin/launchctl", *args], capture_output=True, text=True)


def service(action):
    if sys.platform != "darwin":
        raise ValueError("Supervise `python3 paperclip/instance.py run` with your service manager; see README-paperclip.md.")
    label = service_label("paperclip", ROOT.parent)
    target = f"gui/{os.getuid()}/{label}"
    plist = plist_path(label)
    loaded = launch("print", target).returncode == 0
    if action in {"stop", "restart"} and loaded:
        result = launch("bootout", target)
        if result.returncode:
            raise ValueError(result.stderr.strip() or "launchctl bootout failed")
        loaded = False
        # The server drains runs and then stops its embedded PostgreSQL a few seconds later.
        for _ in range(120):
            if not health(1) and not port_open(run.db_port()):
                break
            time.sleep(0.5)
    if action in {"start", "restart"} and not loaded:
        if health(1):
            raise ValueError(f"Something already answers on {run.base_url()}; stop the foreground copy first.")
        logs = run.PRIVATE / "logs"
        logs.mkdir(mode=0o700, parents=True, exist_ok=True)
        expected = {"Label": label,
                    "ProgramArguments": [sys.executable, str(ROOT / "instance.py"), "run"],
                    "WorkingDirectory": str(ROOT), "RunAtLoad": True, "KeepAlive": True,
                    "ThrottleInterval": 5, "Umask": 0o077,
                    "EnvironmentVariables": {"PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"},
                    "StandardOutPath": str(logs / "server.log"),
                    "StandardErrorPath": str(logs / "server.err.log")}
        plist.parent.mkdir(parents=True, exist_ok=True)
        if plist.exists() and plistlib.loads(plist.read_bytes()) != expected:
            raise ValueError(f"A different service definition is at {plist}; inspect it before changing it.")
        if not plist.exists():
            plist.write_bytes(plistlib.dumps(expected))
            plist.chmod(0o600)
        private = ROOT.parent / ".local/services" / plist.name
        private.parent.mkdir(parents=True, exist_ok=True)
        private.write_bytes(plist.read_bytes())
        private.chmod(0o600)
        # launchd can acknowledge bootout before the registration is gone; retry briefly.
        for attempt in range(12):
            result = launch("bootstrap", f"gui/{os.getuid()}", str(plist))
            if result.returncode == 0:
                break
            if result.returncode != 5 or attempt == 11:
                raise ValueError(result.stderr.strip() or "launchctl bootstrap failed")
            time.sleep(0.5)
        loaded = True
    print(f"{label}: {'loaded' if loaded else 'stopped'}")
    if action in {"start", "restart"}:
        data = wait_for_health(60)
        if not data:
            raise ValueError("Service loaded but the API is not ready after 60 seconds; inspect paperclip/.local/logs/.")
        print(f"API: ok; version {data.get('version')}; mode {data.get('deploymentMode')}")
    if action == "status":
        data = health(5)
        if data:
            print(f"API: {data.get('status')}; version {data.get('version')}; mode {data.get('deploymentMode')} at {run.base_url()}")
        else:
            print(f"API: not reachable at {run.base_url()}")


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="Create the private instance with the ports selected in .env")
    sub.add_parser("run", help="Run the server in the foreground")
    p = sub.add_parser("secure", help="Switch to authenticated mode and allow browser hostnames")
    p.add_argument("--allow-host", action="append", default=[], metavar="HOST",
                   help="Hostname browsers will use, for example your Tailscale name")
    for name in ("start", "stop", "restart", "status"):
        sub.add_parser(name, help=f"{name} the macOS background service")
    args = parser.parse_args()
    if args.command == "init":
        init()
    elif args.command == "run":
        run_foreground()
    elif args.command == "secure":
        secure(args.allow_host)
    else:
        service(args.command)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        sys.exit(f"Stopped: {error}")
