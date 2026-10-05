#!/usr/bin/env python3
"""Run the pinned Paperclip CLI with this folder's private state and a clean environment."""
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
sys.path.insert(0, str(PROJECT / "scripts"))
from native import base_environment, project_values  # noqa: E402

INSTANCE = "team"
PRIVATE = ROOT / ".local"
CONFIG = PRIVATE / "instances" / INSTANCE / "config.json"


def selected_port(name, default):
    value = project_values(PROJECT).get(name, "").strip() or str(default)
    if not value.isdigit() or not 1024 <= int(value) <= 65535:
        raise ValueError(f"{name} in .env must be a TCP port between 1024 and 65535.")
    return int(value)


def port():
    return selected_port("PAPERCLIP_PORT", 3100)


def db_port():
    return selected_port("PAPERCLIP_DB_PORT", 54329)


def base_url():
    return f"http://127.0.0.1:{port()}"


def environment():
    """OS and proxy settings only: no provider keys, no Gateway token, no default ~/.paperclip."""
    env = base_environment()
    version_file = PROJECT / ".nvmrc"
    if version_file.is_file():
        node_bin = (Path(env.get("NVM_DIR", str(Path.home() / ".nvm"))) / "versions/node"
                    / ("v" + version_file.read_text().strip()) / "bin")
        if (node_bin / "node").is_file():
            env["PATH"] = str(node_bin) + os.pathsep + env.get("PATH", "")
    env.update({"PAPERCLIP_HOME": str(PRIVATE), "PAPERCLIP_INSTANCE_ID": INSTANCE,
                "PAPERCLIP_NO_BROWSER": "1", "PAPERCLIP_OPEN_ON_LISTEN": "false",
                "PAPERCLIP_UPDATE_CHECK": "false", "PAPERCLIP_TELEMETRY_DISABLED": "1"})
    return env


def command(env=None):
    env = env or environment()
    node = shutil.which("node", path=env["PATH"])
    cli = ROOT / "node_modules/paperclipai/dist/index.js"
    if not node or not cli.is_file():
        raise ValueError("Install the project's Node version, then run `npm ci --no-audit --no-fund` in paperclip/.")
    return [node, str(cli)]


def main():
    os.umask(0o077)
    PRIVATE.mkdir(mode=0o700, exist_ok=True)
    env = environment()
    os.chdir(ROOT)
    os.execve(command(env)[0], [*command(env), *sys.argv[1:]], env)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as error:
        sys.exit(f"Stopped: {error}")
