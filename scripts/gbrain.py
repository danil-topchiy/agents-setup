#!/usr/bin/env python3
"""Repository-local GBrain: Markdown remains authoritative; MCP clients only read."""
import argparse
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import secrets
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent))
from native import project_values, service_label  # noqa: E402

PROJECT = Path(__file__).resolve().parent.parent
ROOT = PROJECT / ".local/gbrain"
VAULT = PROJECT / "openclaw/workspace/knowledge"
MIRROR = ROOT / "markdown-index-source"
VERSION = "0.60.37.0"
COMMIT = "109b992172e1f49107f9de9841758c1d043a2668"
ASSETS = {
    ("Darwin", "arm64"): ("gbrain-darwin-arm64", "48676e8785a243aec956e6af086f76737c8516a82d777be11a4665f72016cb5c"),
    ("Linux", "x86_64"): ("gbrain-linux-x64", "ea19e7521a00d3d01c156c645278343a9e152c69e1cd5c4b1c9faf10a124a915"),
}
TOOLS = ["search", "get_page", "list_pages", "get_links", "traverse_graph", "get_brain_identity"]
TEAM = ["main", "cto", "swe", "qa", "ui-ux", "content", "generalist", "infrastructure", "sales"]


def selected_port():
    value = project_values(PROJECT).get("GBRAIN_PORT", "").strip() or "3131"
    if not value.isdigit() or not 1024 <= int(value) <= 65535:
        raise ValueError("GBRAIN_PORT in .env must be a TCP port between 1024 and 65535.")
    return int(value)


PORT = selected_port()
URL = f"http://127.0.0.1:{PORT}/mcp"
LABEL = service_label("gbrain", PROJECT)


def private_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as out:
        out.write(content)
    path.chmod(0o600)


def environment():
    # Do not inherit provider keys, DATABASE_URL, another brain, or Bun dotenv.
    home = str(ROOT / "home")
    env = {"HOME": home, "GBRAIN_HOME": home, "PATH": "/usr/bin:/bin:/usr/local/bin",
           "GBRAIN_NO_AUTOPILOT_INSTALL": "1", "GBRAIN_NO_REEMBED": "1",
           "GBRAIN_NO_ONBOARD_NUDGE": "1", "GBRAIN_NO_UPDATE_CHECK": "1",
           "GBRAIN_NO_GITIGNORE": "1", "GBRAIN_SWEEP": "0"}
    return env


def cli(args, capture=False, timeout=180):
    return subprocess.run([str(ROOT / "bin/gbrain"), *args], cwd=MIRROR if MIRROR.exists() else ROOT,
                          env=environment(), text=True, capture_output=capture,
                          check=True, timeout=timeout)


def install():
    asset, expected = ASSETS.get((platform.system(), platform.machine()), (None, None))
    if not asset:
        raise ValueError("This release supplies macOS ARM64 and Linux x86_64 binaries; see README-gbrain.md.")
    binary = ROOT / "bin/gbrain"
    binary.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    ROOT.chmod(0o700)
    if binary.exists():
        if hashlib.sha256(binary.read_bytes()).hexdigest() != expected:
            raise ValueError("Existing local binary differs from the pin; preserve it and review before upgrading.")
    else:
        download = binary.with_suffix(".download")
        urllib.request.urlretrieve(f"https://github.com/garrytan/gbrain/releases/download/v{VERSION}/{asset}", download)
        if hashlib.sha256(download.read_bytes()).hexdigest() != expected:
            raise ValueError("GBrain download checksum mismatch; installation stopped.")
        download.chmod(0o755)
        download.replace(binary)
    private_write(ROOT / "installation.json", json.dumps({"version": VERSION, "commit": COMMIT,
                  "asset": asset, "sha256": expected}, indent=2) + "\n")
    print(f"Verified GBrain {VERSION}; no global installation or Bun required.")


def sync_args():
    return ["sync", "--repo", str(MIRROR), "--source", "default",
            "--no-pull", "--no-embed", "--yes", "--json"]


def snapshot():
    """Copy only Markdown into an owned, private Git source for reliable deletes."""
    marker = MIRROR / ".overlay-owner.json"
    ownership = {"owner": "agents-setup-gbrain-v1", "vault": str(VAULT)}
    if MIRROR.exists():
        if not marker.is_file() or json.loads(marker.read_text()) != ownership:
            raise ValueError("Index snapshot is not owned by this setup; refusing to overwrite it.")
    else:
        MIRROR.mkdir(mode=0o700)
        private_write(marker, json.dumps(ownership) + "\n")
    env = environment()
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    def git(*args, check=True):
        return subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-c", "user.name=GBrain Index",
                               "-c", "user.email=gbrain-index@localhost", *args], cwd=MIRROR,
                              env=env, check=check, capture_output=True, text=True)
    if not (MIRROR / ".git").exists():
        git("init", "--quiet", "--initial-branch=main")
    if git("remote").stdout.strip():
        raise ValueError("The private index snapshot must not have a Git remote.")
    fingerprint()  # Reject file symlinks before copying any content.
    files = {p.relative_to(VAULT): p for p in VAULT.rglob("*.md")
             if not any(part.startswith(".") for part in p.relative_to(VAULT).parts)}
    for relative, source in files.items():
        target = MIRROR / relative
        if target.is_symlink():
            raise ValueError("Symlink in generated snapshot; refusing to follow it.")
        payload = source.read_bytes()
        if not target.exists() or target.read_bytes() != payload:
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            target.write_bytes(payload)
    for target in MIRROR.rglob("*.md"):
        if target.relative_to(MIRROR) not in files and ".git" not in target.parts:
            target.unlink()
    git("add", "--all", "--", ".")
    dirty = git("diff", "--cached", "--quiet", check=False).returncode
    if dirty == 1:
        git("commit", "--quiet", "-m", "Update derived Markdown snapshot")
    elif dirty:
        raise ValueError("Cannot inspect the private snapshot's staged changes.")


def initialize():
    if listening():
        raise ValueError("Stop the GBrain service before initializing or changing credentials.")
    (ROOT / "home").mkdir(parents=True, exist_ok=True, mode=0o700)
    snapshot()
    config = ROOT / "home/.gbrain/config.json"
    if not config.exists():
        cli(["init", "--pglite", "--no-embedding", "--db-only", "--non-interactive"])
    # Do not turn this derived store into a canonical writer or skill publisher.
    data = json.loads(config.read_text())
    if data.get("engine") != "pglite" or not data.get("embedding_disabled"):
        raise ValueError("Unexpected existing engine/provider configuration; review it before continuing.")
    data.setdefault("mcp", {})["publish_skills"] = False
    private_write(config, json.dumps(data, indent=2) + "\n")
    cli(["sources", "set-path", "default", str(MIRROR)])
    cli(sync_args())
    cli(["extract", "links", "--source", "db"])
    token_file = ROOT / "reader-token"
    if not token_file.exists():
        result = cli(["auth", "create", "openclaw-knowledge-reader", "--scopes", "read"], capture=True)
        token = re.search(r"^\s+(gbrain_[A-Za-z0-9_-]+)\s*$", result.stdout, re.M)
        if not token:
            raise ValueError("Token creation did not produce the expected receipt; inspect privately before retrying.")
        private_write(token_file, token.group(1) + "\n")
    cli(["auth", "rescope", "--token", "openclaw-knowledge-reader", "--sources", "default",
         "--operations", ",".join(TOOLS), "--scopes", "read", "--json"])
    if not (ROOT / "admin-token").exists():
        private_write(ROOT / "admin-token", secrets.token_hex(32) + "\n")
    print("Initialized the shared vault index and a restricted local reader credential.")


def configure_data(original):
    """Add only GBrain access; preserve every unrelated setting."""
    data = copy.deepcopy(original)
    data.setdefault("mcp", {}).setdefault("servers", {})["gbrain"] = {
        "url": URL, "transport": "streamable-http",
        "headers": {"Authorization": "Bearer ${GBRAIN_READER_TOKEN}"},
        "connectionTimeoutMs": 30000, "requestTimeoutMs": 60000,
        "toolFilter": {"include": TOOLS},
        "codex": {"agents": TEAM, "defaultToolsApprovalMode": "auto"},
    }
    # A wildcard deny beats an allow. Replace it with denies for the other
    # currently configured servers; retain explicit positive tool allowlists.
    for agent in TEAM:
        entry = data["agents"]["entries"][agent]
        policy = entry.setdefault("tools", {})
        if "*__*" in policy.get("deny", []):
            policy["deny"].remove("*__*")
            for server in data["mcp"]["servers"]:
                if server != "gbrain" and not server.startswith("gbrain_history_") and f"{server}__*" not in policy["deny"]:
                    policy["deny"].append(f"{server}__*")
        # OpenClaw selects the agent list instead of the global list when
        # present. Materialize inherited permissions before extending it.
        allow = policy.setdefault("alsoAllow", list(data.get("tools", {}).get("alsoAllow", [])))
        for name in TOOLS:
            if f"gbrain__{name}" not in allow:
                allow.append(f"gbrain__{name}")
    allow = data.setdefault("tools", {}).setdefault("alsoAllow", [])
    for name in TOOLS:
        if f"gbrain__{name}" not in allow:
            allow.append(f"gbrain__{name}")
    return data


def configure():
    from native import runtime_env
    env = runtime_env("openclaw")
    config = Path(env["OPENCLAW_CONFIG_PATH"])
    if config != PROJECT / "config/openclaw.json":
        raise ValueError("Selected config is elsewhere; review that instance rather than editing the wrong profile.")
    original = config.read_text()
    data = configure_data(json.loads(original))
    backup = ROOT / "before/openclaw.json"
    if not backup.exists():
        private_write(backup, original)
    # Env references only in Git; preserve all unrelated private dotenv values.
    dotenv = PROJECT / ".local/openclaw.env"
    content = dotenv.read_text() if dotenv.exists() else ""
    lines = [line for line in content.splitlines() if not line.startswith("GBRAIN_READER_TOKEN=")]
    lines.append("GBRAIN_READER_TOKEN=" + (ROOT / "reader-token").read_text().strip())
    private_write(dotenv, "\n".join(lines) + "\n")
    config.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    result = subprocess.run([sys.executable, str(PROJECT / "scripts/native.py"),
                             "openclaw", "config", "validate"], cwd=PROJECT)
    if result.returncode:
        config.write_text(original)
        raise ValueError("OpenClaw validation failed; original configuration restored.")
    print("GBrain configured for the nine team agents. Restart the Gateway so it loads the reader token.")


def listening():
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", PORT)) == 0


def fingerprint():
    digest = hashlib.sha256()
    for path in sorted(VAULT.rglob("*.md")):
        if any(part.startswith(".") for part in path.relative_to(VAULT).parts):
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(VAULT.resolve()):
            raise ValueError("Symlink in the shared vault; inspect before indexing.")
        digest.update(str(path.relative_to(VAULT)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def sync():
    with (ROOT / "sync.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        before = fingerprint()
        snapshot()
        try:
            result = cli(sync_args(), capture=True)
        except subprocess.CalledProcessError as error:
            private_write(ROOT / "last-sync.log", (error.stdout or "") + (error.stderr or ""))
            raise
        private_write(ROOT / "last-sync.log", result.stdout + result.stderr)
        # HTTP serve does not run the stdio idle extraction pass. With no
        # provider keys or transcript corpus this updates local links/timeline.
        sweep = cli(["sweep", "--once", "--json"], capture=True)
        private_write(ROOT / "last-sweep.log", sweep.stdout + sweep.stderr)
        private_write(ROOT / "sync-status.json", json.dumps({"last_success_epoch": time.time(),
                      "fingerprint": before}, indent=2) + "\n")
        print("Shared Markdown synced into GBrain.", flush=True)


def run():
    """One DB owner plus a content watcher; sync delegates through owner IPC."""
    if listening():
        raise ValueError(f"Port {PORT} is already in use; no existing service was stopped.")
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    with (ROOT / "server.log").open("a") as log:
        child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "serve"],
                                 stdout=log, stderr=log)
        try:
            for _ in range(60):
                if child.poll() is not None:
                    raise ValueError("GBrain exited during startup; inspect .local/gbrain/server.log.")
                if listening() or stop.wait(1):
                    break
            if not listening():
                raise ValueError("GBrain listener did not start.")
            previous = None
            next_capture = 0
            while not stop.is_set():
                if child.poll() is not None:
                    raise ValueError("GBrain server exited; the supervisor will restart it.")
                current = fingerprint()
                if current != previous:
                    try:
                        sync()
                        previous = current
                    except (OSError, ValueError, subprocess.SubprocessError) as error:
                        print(f"Sync failed; retrying: {type(error).__name__}. Inspect last-sync.log.", flush=True)
                if time.monotonic() >= next_capture:
                    import gbrain_sessions
                    try:
                        gbrain_sessions.sync()
                    except (OSError, ValueError, subprocess.SubprocessError) as error:
                        private_write(gbrain_sessions.ROOT / "last-error.json", json.dumps({
                            "time": time.time(), "error_type": type(error).__name__}) + "\n")
                        print("Session capture failed; retrying. Inspect sessions/last-error.json.", flush=True)
                    next_capture = time.monotonic() + 30
                stop.wait(10)
        finally:
            child.terminate()
            try:
                child.wait(timeout=20)
            except subprocess.TimeoutExpired:
                # Do not delete a live database lock or conceal failed shutdown.
                raise ValueError("GBrain did not stop within 20 seconds; inspect the owning process.")


def service(action):
    if platform.system() != "Darwin":
        raise ValueError("Use the Linux systemd instructions in README-gbrain.md; supervise `gbrain.py run`.")
    target = f"gui/{os.getuid()}/{LABEL}"
    plist = Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist"
    if action == "install-service":
        expected = {"Label": LABEL,
                    "ProgramArguments": [sys.executable, str(Path(__file__).resolve()), "run"],
                    "WorkingDirectory": str(PROJECT), "RunAtLoad": True, "KeepAlive": True,
                    "ThrottleInterval": 10, "ExitTimeOut": 30,
                    "StandardOutPath": str(ROOT / "service.log"),
                    "StandardErrorPath": str(ROOT / "service.err.log")}
        if plist.exists() and plistlib.loads(plist.read_bytes()) != expected:
            raise ValueError("A different service definition has this name; preserve it and review.")
        plist.parent.mkdir(parents=True, exist_ok=True)
        plist.write_bytes(plistlib.dumps(expected)); plist.chmod(0o600)
        private = PROJECT / ".local/services" / plist.name
        private.parent.mkdir(parents=True, exist_ok=True)
        private.write_bytes(plist.read_bytes()); private.chmod(0o600)
        active = subprocess.run(["launchctl", "print", target], capture_output=True).returncode == 0
        if not active:
            if listening():
                raise ValueError(f"Port {PORT} is occupied; stop the foreground copy before loading the service.")
            subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(plist)], check=True)
        print("GBrain service installed and loaded.")
    elif action == "stop":
        subprocess.run(["launchctl", "bootout", target], check=True)
    elif action == "start":
        subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(plist)], check=True)
    elif action == "restart":
        service("stop")
        for _ in range(30):
            if not listening():
                break
            time.sleep(1)
        service("start")


def rpc(method, params=None, authenticated=True):
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if authenticated:
        headers["Authorization"] = "Bearer " + (ROOT / "reader-token").read_text().strip()
    request = urllib.request.Request(URL, json.dumps(payload).encode(), headers)
    with urllib.request.urlopen(request, timeout=60) as response:
        body = response.read().decode()
        if "text/event-stream" in response.headers.get("Content-Type", ""):
            events = [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")]
            return next(event for event in events if event.get("id") == 1)
        return json.loads(body)


def status():
    print(f"GBrain {VERSION}; shared vault: {VAULT}")
    print(f"Listener: {'up' if listening() else 'down'} at {URL}")
    if (ROOT / "sync-status.json").exists():
        data = json.loads((ROOT / "sync-status.json").read_text())
        print(f"Last successful sync: {int(time.time() - data['last_success_epoch'])} seconds ago")
        print(f"Markdown matches synced fingerprint: {data['fingerprint'] == fingerprint()}")
    if listening():
        result = rpc("tools/list")
        print("Reader tools:", ", ".join(tool["name"] for tool in result["result"]["tools"]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["install", "init", "configure", "cli", "sync", "serve",
                        "run", "install-service", "start", "stop", "restart", "status"])
    parser.add_argument("args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command == "install":
        install()
    elif args.command == "init":
        initialize()
    elif args.command == "sync":
        sync()
    elif args.command == "configure":
        configure()
    elif args.command == "run":
        run()
    elif args.command == "status":
        status()
    elif args.command in ("install-service", "start", "stop", "restart"):
        service(args.command)
    elif args.command == "serve":
        env = environment()
        env["GBRAIN_ADMIN_BOOTSTRAP_TOKEN"] = (ROOT / "admin-token").read_text().strip()
        os.execve(str(ROOT / "bin/gbrain"), [str(ROOT / "bin/gbrain"), "serve", "--http",
                  "--bind", "127.0.0.1", "--port", str(PORT), "--suppress-bootstrap-token"], env)
    else:
        cli(args.args)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        sys.exit(f"Stopped: {error}")
