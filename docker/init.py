#!/usr/bin/env python3
"""Create private dashboard settings and initialize fresh Docker volumes."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import sys


def prepare_env(kit=None):
    kit = (Path(kit) if kit is not None else Path(__file__).resolve().parent.parent).resolve()
    project = kit
    if not (project / "scripts/env.sh").is_file() or not (project / "openclaw/workspace/AGENTS.md").is_file():
        raise ValueError("Run this from a demo-agents checkout containing scripts/env.sh and openclaw/workspace/AGENTS.md.")
    path = kit / ".env"
    values = {
        "COMPOSE_PROJECT_NAME": "demo-agents-" + hashlib.sha256(str(project).encode()).hexdigest()[:10],
        "DEMO_PROJECT": str(project),
        "WORKSHOP_UID": str(os.getuid()),
        "WORKSHOP_GID": str(os.getgid()),
        "OPENCLAW_CONFIG_PATH": str(project / "config/openclaw.json"),
        "OPENCLAW_STATE_DIR": str(project / ".local/native/openclaw"),
        "OPENCLAW_HOME": str(project / ".local/native/openclaw-home"),
        "OPENCLAW_GATEWAY_TOKEN": secrets.token_hex(32),
        "HERMES_DASHBOARD_PASSWORD": secrets.token_urlsafe(24),
        "HERMES_DASHBOARD_SECRET": secrets.token_hex(32),
    }
    # Compose single-quoted values are literal, including dollar signs in paths.
    lines = [key + "='" + value.replace("'", "\\'") + "'" for key, value in values.items()]
    if path.exists():
        current = env_values(path)
        # Older checkouts have no explicit native selectors; keep their files intact.
        optional = {"OPENCLAW_CONFIG_PATH", "OPENCLAW_STATE_DIR", "OPENCLAW_HOME"}
        missing = [key for key in values if key not in optional and not current.get(key)]
        if missing:
            raise ValueError("Existing .env is missing required settings: " + ", ".join(missing) + ". Preserve it and review locally.")
        if current["DEMO_PROJECT"] != str(project):
            raise ValueError("This checkout moved. Update only DEMO_PROJECT in .env to this checkout's absolute path.")
        path.chmod(0o600)
    else:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as output:
            output.write("\n".join(lines) + "\n")
    private = kit / ".local"
    private.mkdir(mode=0o700, exist_ok=True)
    private.chmod(0o700)
    integrations = private / "openclaw.env"
    if not integrations.exists():
        fd = os.open(integrations, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
    print(f"Dashboard settings ready in {path}. Existing credentials were preserved.")


def prepare_openclaw():
    state = Path("/home/node/.openclaw")
    config = state / "openclaw.json"
    if config.exists():
        raise ValueError("OpenClaw configuration already exists; skip initialization.")
    uid, gid = int(os.environ["WORKSHOP_UID"]), int(os.environ["WORKSHOP_GID"])
    for directory in (state, Path("/home/node/.config/openclaw")):
        directory.mkdir(parents=True, exist_ok=True)
        os.chown(directory, uid, gid)
        directory.chmod(0o700)
    data = json.loads(Path("/project/config/openclaw-policy.patch.json").read_text())
    data["gateway"].update({
        "bind": "lan", "port": 18789,
        "auth": {"mode": "token", "allowTailscale": False},
        "controlUi": {"allowedOrigins": ["http://127.0.0.1:18789", "http://localhost:18789"]},
    })
    workspace = "/project/openclaw/workspace"
    data["agents"]["defaults"]["workspace"] = workspace
    data["agents"]["entries"] = {"main": {"workspace": workspace}}
    browsers = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/home/node/.cache/ms-playwright"))
    chromium = sorted(browsers.glob("chromium-*/chrome-linux*/chrome"))
    if len(chromium) != 1:
        raise ValueError("Expected one bundled Chromium binary; use the pinned browser image.")
    data["browser"].update({"headless": True, "executablePath": str(chromium[0])})
    with config.open("x") as output:
        json.dump(data, output, indent=2)
        output.write("\n")
    os.chown(config, uid, gid)
    config.chmod(0o600)
    print("Initialized the file-only OpenClaw policy. Provider login remains to be done.")


def env_values(path):
    if not path.is_file():
        return {}
    result = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.removeprefix("export ").split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] == "'":
            value = value[1:-1].replace("\\'", "'")
        elif len(value) >= 2 and value[0] == value[-1] == '"':
            value = value[1:-1]
        result[key.strip()] = value
    return result


def prepare_hermes(state=Path("/opt/data"), source=Path("/project/hermes"),
                   defaults=Path("/opt/hermes/.env.example"), cwd="/project/hermes/project"):
    marker = state / ".workshop-initialized"
    if marker.exists():
        raise ValueError("Hermes workshop settings already exist; skip initialization.")
    if any((state / name).exists() for name in ("auth.json", "state.db")):
        raise ValueError("Hermes account/session state exists; preserve it and review manually.")
    original = env_values(defaults)
    for key, value in env_values(state / ".env").items():
        if value and key != "API_SERVER_KEY" and value != original.get(key):
            raise ValueError("Hermes has customized environment values; preserve them and review manually.")
    # The official entrypoint seeds defaults before this command. Replace those
    # defaults once, before provider login, with the reviewed teaching policy.
    text = (source / "config.yaml").read_text().replace('cwd: "."', 'cwd: ' + json.dumps(str(cwd)))
    (state / "config.yaml").write_text(text)
    (state / "config.yaml").chmod(0o600)
    (state / "memories").mkdir(exist_ok=True)
    for name in ("SOUL.md", "USER.md", "MEMORY.md"):
        destination = state / name if name == "SOUL.md" else state / "memories" / name
        shutil.copy2(source / "context" / name, destination)
        destination.chmod(0o600)
    marker.write_text("Workshop templates copied before model login.\n")
    print("Initialized Hermes. Provider login remains to be done.")


if __name__ == "__main__":
    actions = {"env": prepare_env, "openclaw": prepare_openclaw, "hermes": prepare_hermes}
    try:
        if len(sys.argv) != 2 or sys.argv[1] not in actions:
            raise ValueError("Usage: python3 docker/init.py env|openclaw|hermes")
        actions[sys.argv[1]]()
    except (OSError, ValueError, KeyError) as error:
        sys.exit(f"Stopped: {error}")
