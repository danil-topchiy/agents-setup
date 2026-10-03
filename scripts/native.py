#!/usr/bin/env python3
"""Run native assistants with repository config and explicitly selected private state."""
import json
import os
from pathlib import Path
import shutil
import sys

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "docker"))
from init import env_values, portable_config, prepare_env, prepare_hermes

starter_config = portable_config


def base_environment():
    """Keep OS/terminal settings; load credentials and runtime options per instance."""
    allowed = {"PATH", "HOME", "USER", "LOGNAME", "SHELL", "LANG", "TERM", "COLORTERM",
               "TMPDIR", "TMP", "TEMP", "NVM_DIR", "USERPROFILE", "APPDATA", "LOCALAPPDATA",
               "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "HTTP_PROXY", "HTTPS_PROXY",
               "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "all_proxy", "no_proxy",
               "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"}
    return {key: value for key, value in os.environ.items()
            if key in allowed or key.startswith("LC_")}


def openclaw_paths(project, values):
    private = project / ".local/native"
    defaults = {"OPENCLAW_CONFIG_PATH": project / "config/openclaw.json",
                "OPENCLAW_STATE_DIR": private / "openclaw",
                "OPENCLAW_HOME": private / "openclaw-home"}
    legacy = private / "openclaw/openclaw.json"
    if not values.get("OPENCLAW_CONFIG_PATH") and not defaults["OPENCLAW_CONFIG_PATH"].exists() and legacy.is_file():
        defaults["OPENCLAW_CONFIG_PATH"] = legacy
    paths = {}
    for key, default in defaults.items():
        path = Path(values[key]).expanduser() if values.get(key) else default
        paths[key] = (project / path).resolve() if not path.is_absolute() else path.resolve()
    return paths


def initialize(project=PROJECT):
    project = Path(project).resolve()
    prepare_env(project)
    private = project / ".local/native"
    paths = openclaw_paths(project, env_values(project / ".env"))
    for folder in (paths["OPENCLAW_STATE_DIR"], paths["OPENCLAW_HOME"], private / "hermes"):
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    (project / ".local/logs").mkdir(mode=0o700, parents=True, exist_ok=True)
    config = paths["OPENCLAW_CONFIG_PATH"]
    if not config.exists():
        state = paths["OPENCLAW_STATE_DIR"]
        if (state / "openclaw.json").exists() or any((state / name).exists() for name in ("state", "agents", "credentials")):
            raise ValueError("Native OpenClaw already has runtime data; preserve it and review locally.")
        data = starter_config(project)
        config.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(config, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as out:
            json.dump(data, out, indent=2)
            out.write("\n")
        print("Initialized native OpenClaw with the repository's starting policy.")
    else:
        print("Kept existing native OpenClaw configuration.")
    state = private / "hermes"
    if any((state / name).is_file() for name in (".starter-initialized", ".workshop-initialized")):
        print("Kept existing native Hermes configuration and memory.")
    elif (state / "config.yaml").exists():
        raise ValueError("Native Hermes config already exists; preserve it and review locally.")
    else:
        prepare_hermes(state=state, source=project / "hermes",
                       defaults=private / "no-default-env", cwd=project / "hermes/project")


def runtime_env(service, project=PROJECT):
    project = Path(project).resolve()
    values = env_values(project / ".env")
    required = ("DEMO_PROJECT", "OPENCLAW_GATEWAY_TOKEN", "HERMES_DASHBOARD_PASSWORD", "HERMES_DASHBOARD_SECRET")
    if any(not values.get(key) for key in required):
        raise ValueError("Run python3 scripts/native.py init first.")
    if values["DEMO_PROJECT"] != str(project):
        raise ValueError("DEMO_PROJECT in .env names a different checkout; update that path locally.")
    env = base_environment()
    private = project / ".local/native"
    version_file = project / ".nvmrc"
    if version_file.is_file():
        node_bin = Path(env.get("NVM_DIR", str(Path.home() / ".nvm"))) / "versions/node" / ("v" + version_file.read_text().strip()) / "bin"
        if (node_bin / "node").is_file():
            env["PATH"] = str(node_bin) + os.pathsep + env.get("PATH", "")
    if service == "openclaw":
        paths = openclaw_paths(project, values)
        if not paths["OPENCLAW_CONFIG_PATH"].is_file():
            raise ValueError("Run python3 scripts/native.py init first.")
        # Load this checkout's private dotenv explicitly, before OpenClaw applies
        # its lower-trust workspace-dotenv filtering. Hermes secrets stay scoped.
        env.update({key: value for key, value in values.items()
                    if not key.startswith("HERMES_") and key not in
                    {"COMPOSE_PROJECT_NAME", "DEMO_PROJECT", "HOST_UID", "HOST_GID",
                     "WORKSHOP_UID", "WORKSHOP_GID"}})
        env.update(env_values(project / ".local/openclaw.env"))
        # Selectors come from this checkout's .env, never an inherited host profile.
        env.update({key: str(value) for key, value in paths.items()})
        env.update({"OPENCLAW_WORKSPACE_DIR": str(project / "openclaw/workspace"),
                    "OPENCLAW_AGENT_DIR": str(paths["OPENCLAW_STATE_DIR"] / "agents/main/agent"),
                    "OPENCLAW_LOG_FILE": str(project / ".local/logs/openclaw.log"),
                    "OPENCLAW_GATEWAY_PORT": "18789",
                    "OPENCLAW_GATEWAY_TOKEN": values["OPENCLAW_GATEWAY_TOKEN"]})
        env.pop("OPENCLAW_PROFILE", None)
    elif service == "hermes":
        if not (private / "hermes/config.yaml").is_file():
            raise ValueError("Run python3 scripts/native.py init first.")
        env.update(env_values(private / "hermes/.env"))
        env.update({"HERMES_HOME": str(private / "hermes"),
                    "HERMES_DASHBOARD_BASIC_AUTH_USERNAME": "learner",
                    "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD": values["HERMES_DASHBOARD_PASSWORD"],
                    "HERMES_DASHBOARD_BASIC_AUTH_SECRET": values["HERMES_DASHBOARD_SECRET"]})
        env["PATH"] = str(Path.home() / ".local/bin") + os.pathsep + env.get("PATH", "")
    else:
        raise ValueError("Expected openclaw or hermes.")
    return env


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "init":
        initialize()
        return
    if len(sys.argv) < 3 or sys.argv[1] not in ("openclaw", "hermes"):
        raise ValueError("Usage: python3 scripts/native.py init | openclaw COMMAND... | hermes COMMAND...")
    service, args = sys.argv[1], sys.argv[2:]
    if "--profile" in args or "-p" in args or any(a.startswith("--profile=") for a in args):
        raise ValueError("This wrapper selects configuration and state from .env; omit profile flags.")
    env = runtime_env(service)
    binary = shutil.which(service, path=env.get("PATH"))
    if not binary:
        raise ValueError(f"{service} is not installed; follow README-native.md.")
    os.chdir(PROJECT if service == "openclaw" else PROJECT / "hermes/project")
    command = [binary, "--profile", "default", *args] if service == "hermes" else [binary, *args]
    os.execvpe(binary, command, env)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError) as error:
        sys.exit(f"Stopped: {error}")
