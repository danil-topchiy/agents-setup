#!/usr/bin/env python3
"""Future-only OpenClaw session capture, with per-agent GBrain read grants."""
import argparse
import copy
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import urllib.request

import gbrain
from native import runtime_env

ROOT = gbrain.ROOT / "sessions"
TOOLS = ["search", "get_page", "list_pages"]
SETTINGS = ROOT / "settings.json"


def agent_ids():
    config = json.loads(Path(runtime_env("openclaw")["OPENCLAW_CONFIG_PATH"]).read_text())
    agents = list(config["agents"]["entries"])
    if any(not re.fullmatch(r"[a-z0-9][a-z0-9-]*", agent) for agent in agents):
        raise ValueError("Unsupported agent ID; review source names before capture.")
    return agents


def source_id(agent):
    return "sessions-" + agent


def server_id(agent):
    return "gbrain_history_" + agent.replace("-", "_")


def token_env(agent):
    return "GBRAIN_SESSION_" + agent.upper().replace("-", "_") + "_TOKEN"


def export(action="export"):
    env = runtime_env("openclaw")
    executable = shutil.which("openclaw", path=env["PATH"])
    node = shutil.which("node", path=env["PATH"])
    if not executable or not node:
        raise ValueError("Pinned native OpenClaw and Node are required.")
    package = Path(executable).resolve().parent
    request = {"action": action, "packageRoot": str(package), "root": str(ROOT),
               "stores": {agent: str(Path(env["OPENCLAW_STATE_DIR"]) / "agents" / agent / "agent/openclaw-agent.sqlite")
                          for agent in agent_ids()}}
    result = subprocess.run([node, str(gbrain.PROJECT / "scripts/gbrain_sessions_export.mjs")],
                            input=json.dumps(request), env=env, cwd=gbrain.PROJECT,
                            capture_output=True, text=True, timeout=120)
    if result.returncode:
        # The adapter deliberately never prints transcript bodies or secrets.
        gbrain.private_write(ROOT / "export-error.log", result.stderr)
        raise ValueError("Session export failed; inspect the private export-error.log.")
    return json.loads(result.stdout)


def git(agent, *args):
    env = gbrain.environment()
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    return subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-c", "user.name=GBrain Archive",
                           "-c", "user.email=gbrain-archive@localhost", *args],
                          cwd=ROOT / "sources" / agent, env=env, capture_output=True, text=True, check=True)


def commit_source(agent):
    directory = ROOT / "sources" / agent
    marker = directory / ".capture-owner.json"
    ownership = {"owner": "agents-setup-session-capture-v1", "agent": agent}
    if directory.is_symlink():
        raise ValueError("Archive source is a symlink.")
    if not directory.exists():
        directory.mkdir(parents=True, mode=0o700)
        gbrain.private_write(marker, json.dumps(ownership) + "\n")
    if not marker.is_file() or json.loads(marker.read_text()) != ownership:
        raise ValueError("Unowned session source; preserve it for review.")
    if not (directory / ".git").exists():
        git(agent, "init", "--quiet", "--initial-branch=main")
    if git(agent, "remote").stdout.strip():
        raise ValueError("Session archives must not have Git remotes.")
    git(agent, "add", "--all", "--", ".")
    if git(agent, "diff", "--cached", "--name-only").stdout.strip():
        git(agent, "commit", "--quiet", "-m", "Update private session archive")
    return git(agent, "rev-parse", "HEAD").stdout.strip()


def provision():
    if gbrain.listening():
        raise ValueError("Stop the GBrain service before provisioning source grants, then start it again.")
    existing = json.loads(gbrain.cli(["sources", "list", "--json"], capture=True).stdout)["sources"]
    by_id = {row["id"]: row for row in existing}
    for agent in agent_ids():
        commit_source(agent)
        source = source_id(agent)
        directory = ROOT / "sources" / agent
        if source not in by_id:
            gbrain.cli(["sources", "add", source, "--path", str(directory), "--no-federated"], capture=True)
        elif by_id[source]["local_path"] != str(directory) or by_id[source]["federated"]:
            raise ValueError("An existing session source has unexpected ownership or federation.")
        name = "openclaw-history-" + agent
        token_file = ROOT / "tokens" / agent
        if not token_file.exists():
            receipt = gbrain.cli(["auth", "create", name, "--scopes", "read"], capture=True)
            token = re.search(r"^\s+(gbrain_[A-Za-z0-9_-]+)\s*$", receipt.stdout, re.M)
            if not token:
                raise ValueError("Could not read the new token receipt; inspect privately before retrying.")
            gbrain.private_write(token_file, token.group(1) + "\n")
        gbrain.cli(["auth", "rescope", "--token", name, "--sources", source,
                    "--operations", ",".join(TOOLS), "--scopes", "read", "--json"], capture=True)
    print("Provisioned private session sources and read-only, per-agent credentials.")


def configure_data(original):
    data = copy.deepcopy(original)
    servers = data.setdefault("mcp", {}).setdefault("servers", {})
    eligible = [agent for agent in gbrain.TEAM if agent in data["agents"]["entries"]]
    for agent in eligible:
        servers[server_id(agent)] = {
            "url": gbrain.URL, "transport": "streamable-http",
            "headers": {"Authorization": "Bearer ${" + token_env(agent) + "}"},
            "connectionTimeoutMs": 30000, "requestTimeoutMs": 60000,
            "toolFilter": {"include": TOOLS},
            "codex": {"agents": [agent], "defaultToolsApprovalMode": "auto"},
        }
    for agent, entry in data["agents"]["entries"].items():
        policy = entry.setdefault("tools", {})
        deny = policy.setdefault("deny", [])
        if agent in eligible:
            own = server_id(agent)
            policy["deny"] = deny = [item for item in deny if item != own + "__*"]
            allow = policy.setdefault("alsoAllow", list(data.get("tools", {}).get("alsoAllow", [])))
            allow[:] = [name for name in allow if not name.startswith("gbrain_history_")]
            allow.extend(own + "__" + name for name in TOOLS)
        for other in eligible:
            if other != agent and server_id(other) + "__*" not in deny:
                deny.append(server_id(other) + "__*")
    return data


def configure():
    config = Path(runtime_env("openclaw")["OPENCLAW_CONFIG_PATH"])
    if config != gbrain.PROJECT / "config/openclaw.json":
        raise ValueError("Selected config is elsewhere; refusing to change another profile.")
    before = config.read_text()
    backup = ROOT / "before-openclaw.json"
    if not backup.exists():
        gbrain.private_write(backup, before)
    data = configure_data(json.loads(before))
    dotenv = gbrain.PROJECT / ".local/openclaw.env"
    lines = [line for line in dotenv.read_text().splitlines() if not line.startswith("GBRAIN_SESSION_")]
    for agent in gbrain.TEAM:
        lines.append(token_env(agent) + "=" + (ROOT / "tokens" / agent).read_text().strip())
    gbrain.private_write(dotenv, "\n".join(lines) + "\n")
    config.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    result = subprocess.run([sys.executable, str(gbrain.PROJECT / "scripts/native.py"),
                             "openclaw", "config", "validate"], cwd=gbrain.PROJECT,
                            capture_output=True, text=True)
    if result.returncode:
        config.write_text(before)
        gbrain.private_write(ROOT / "config-error.log", result.stdout + result.stderr)
        raise ValueError("Validation failed; original config restored.")
    print("Configured nine scoped readers; restart the Gateway so it loads their credentials.")


def enabled():
    return SETTINGS.exists() and json.loads(SETTINGS.read_text()).get("enabled") is True


def enable():
    if not (ROOT / "checkpoint.json").exists():
        export("checkpoint")
    for agent in agent_ids():
        if not (ROOT / "tokens" / agent).exists():
            raise ValueError("Provision session sources before enabling capture.")
    gbrain.private_write(SETTINGS, json.dumps({"enabled": True, "access": "per-agent", "poll_seconds": 30}) + "\n")
    print("Enabled future-only capture. Existing checkpoint preserved; no history backfill.")


def sync():
    if not enabled():
        return
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Same lock as shared-vault synchronization; only one import at a time.
    with (gbrain.ROOT / "sync.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        result = export()
        state_file = ROOT / "sync-status.json"
        state = json.loads(state_file.read_text()) if state_file.exists() else {"revisions": {}}
        for agent in result["agents"]:
            revision = commit_source(agent)
            if state["revisions"].get(agent) == revision:
                continue
            receipt = gbrain.cli(["sync", "--repo", str(ROOT / "sources" / agent),
                                  "--source", source_id(agent), "--no-pull", "--no-embed", "--yes", "--json"],
                                 capture=True)
            gbrain.private_write(ROOT / "last-sync.log", receipt.stdout + receipt.stderr)
            state["revisions"][agent] = revision
            gbrain.private_write(state_file, json.dumps(state, indent=2) + "\n")
        state.update({"last_success_epoch": time.time(), "agents": result["agents"], "startedAt": result["startedAt"]})
        gbrain.private_write(state_file, json.dumps(state, indent=2) + "\n")
        (ROOT / "last-error.json").unlink(missing_ok=True)


def rpc(agent, name, arguments):
    token = (ROOT / "tokens" / agent).read_text().strip()
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
    request = urllib.request.Request(gbrain.URL, json.dumps(payload).encode(),
              {"Content-Type": "application/json", "Accept": "application/json, text/event-stream", "Authorization": "Bearer " + token})
    with urllib.request.urlopen(request, timeout=60) as response:
        body = response.read().decode()
        if "text/event-stream" in response.headers.get("Content-Type", ""):
            return next(json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ") and json.loads(line[6:]).get("id") == 1)
        return json.loads(body)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["provision", "configure", "enable", "disable", "sync", "status", "search"])
    parser.add_argument("--agent", help="A configured OpenClaw agent ID")
    parser.add_argument("--query")
    args = parser.parse_args()
    if args.command == "status":
        print("Capture enabled:", enabled())
        if (ROOT / "checkpoint.json").exists():
            print("Future-only checkpoint (epoch ms):", json.loads((ROOT / "checkpoint.json").read_text())["startedAt"])
        if (ROOT / "sync-status.json").exists():
            state = json.loads((ROOT / "sync-status.json").read_text())
            print("Last successful sync age (seconds):", int(time.time()-state.get("last_success_epoch", 0)))
            print("Captured events:", sum(v["events"] for v in state.get("agents", {}).values()))
            print("Indexed pages:", sum(v["pages"] for v in state.get("agents", {}).values()))
        print("Pending error:", (ROOT / "last-error.json").exists())
    elif args.command == "disable":
        gbrain.private_write(SETTINGS, json.dumps({"enabled": False, "access": "per-agent", "poll_seconds": 30}) + "\n")
        print("Capture paused; archive and checkpoint preserved. Re-enabling catches up from the original checkpoint.")
    elif args.command == "search":
        if not args.agent or not args.query:
            parser.error("search requires --agent and --query")
        if args.agent not in agent_ids():
            parser.error("--agent must be an agent configured in config/openclaw.json")
        print(json.dumps(rpc(args.agent, "search", {"query": args.query}), indent=2))
    else:
        globals()[args.command]()


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        sys.exit(f"Session capture stopped: {type(error).__name__}. Check private receipts; no transcript content printed.")
