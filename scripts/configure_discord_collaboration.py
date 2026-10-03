#!/usr/bin/env python3
"""Give each team agent its own Discord bot account on one OpenClaw Gateway.

By default this validates a candidate configuration and writes ignored review
files under .local/discord-collaboration/. --apply verifies each bot token with
Discord, backs up the active config and agent instructions, and activates the
candidate. It never creates Discord applications, prints secrets, or restarts
the Gateway.

Private values come from root .env or .local/openclaw.env:
  OPENCLAW_PRIVATE_DISCORD_GUILD_ID         your server
  OPENCLAW_PRIVATE_DISCORD_USER_ID          the one human the bots answer
  OPENCLAW_PRIVATE_DISCORD_TEAM_CHANNEL_ID  the shared team channel
  DISCORD_BOT_TOKEN with OPENCLAW_PRIVATE_DISCORD_MAIN_APPLICATION_ID and
  OPENCLAW_PRIVATE_DISCORD_MAIN_BOT_USER_ID  the Chief of Staff bot (required)
Each further agent is configured when DISCORD_<ROLE>_BOT_TOKEN is set together
with OPENCLAW_PRIVATE_DISCORD_<ROLE>_APPLICATION_ID and _BOT_USER_ID. An
optional OPENCLAW_PRIVATE_DISCORD_<ROLE>_CHANNEL_ID gives that agent a
dedicated room where it answers the owner without a mention.
"""
import argparse
from collections import namedtuple
import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import stat
from string import Template
import subprocess
import sys
import urllib.error
import urllib.request

import native

Role = namedtuple("Role", "name handle suffix aliases")
ROLES = {
    "main": Role("Chief of Staff", "ChiefOfStaff", "MAIN", ("CoS",)),
    "cto": Role("CTO", "CTO", "CTO", ()),
    "swe": Role("SWE", "SWE", "SWE", ()),
    "qa": Role("QA", "QA", "QA", ()),
    "ui-ux": Role("UI/UX", "UIUX", "UI_UX", ("UI-UX",)),
    "content": Role("Content", "Content", "CONTENT", ()),
    "generalist": Role("Generalist", "Generalist", "GENERALIST", ()),
    "infrastructure": Role("Infrastructure", "Infrastructure", "INFRASTRUCTURE", ("Infra",)),
    "sales": Role("Sales", "Sales", "SALES", ()),
}
INCLUDE = "./openclaw-discord.private.json"
MARKER = "## Discord team conversations"
TEMPLATE = native.PROJECT / "config/discord-team-instructions.md"
DELEGATION_TOOLS = ("sessions_spawn", "sessions_yield", "subagents")
SUBAGENTS = {"allowAgents": list(ROLES), "requireAgentId": True, "maxSpawnDepth": 2,
             "maxChildrenPerAgent": 2, "maxConcurrent": 4, "runTimeoutSeconds": 600,
             "delegationMode": "suggest"}


def account_id(role):
    return "default" if role == "main" else role


def token_key(role):
    return "DISCORD_BOT_TOKEN" if role == "main" else f"DISCORD_{ROLES[role].suffix}_BOT_TOKEN"


def id_key(role, kind):
    return f"OPENCLAW_PRIVATE_DISCORD_{ROLES[role].suffix}_{kind}"


def require_id(env, key):
    value = env.get(key, "").strip()
    if not value.isdigit() or not 17 <= len(value) <= 20:
        raise ValueError(f"Missing or invalid private Discord ID: {key}")
    return value


def read_credentials(env):
    """Select the bots that have private credentials; the Chief of Staff bot is required."""
    roles = [role for role in ROLES if env.get(token_key(role), "").strip()]
    if "main" not in roles:
        raise ValueError("DISCORD_BOT_TOKEN for the Chief of Staff bot is required.")
    shared = {key: require_id(env, f"OPENCLAW_PRIVATE_DISCORD_{key}")
              for key in ("GUILD_ID", "USER_ID", "TEAM_CHANNEL_ID")}
    bots = {}
    for role in roles:
        channel_key = id_key(role, "CHANNEL_ID")
        bots[role] = {
            "application": require_id(env, id_key(role, "APPLICATION_ID")),
            "user": require_id(env, id_key(role, "BOT_USER_ID")),
            "channel": require_id(env, channel_key) if env.get(channel_key, "").strip() else None,
        }
    if len({env[token_key(role)].strip() for role in roles}) != len(roles):
        raise ValueError("Each configured bot needs a distinct private token.")
    for kind in ("application", "user"):
        if len({bot[kind] for bot in bots.values()}) != len(roles):
            raise ValueError(f"Each configured bot needs a distinct {kind} ID.")
    return shared, bots


def build_discord(shared, bots):
    """Owner-only DMs, mention-gated rooms, native handoff aliases, and loop limits."""
    guild, owner, team = shared["GUILD_ID"], shared["USER_ID"], shared["TEAM_CHANNEL_ID"]
    aliases = {}
    for role, bot in bots.items():
        aliases[ROLES[role].handle] = bot["user"]
        aliases.update({alias: bot["user"] for alias in ROLES[role].aliases})
    rooms = {team, *(bot["channel"] for bot in bots.values() if bot["channel"])}
    result = {"enabled": True, "defaultAccount": "default", "dmPolicy": "allowlist",
              "allowFrom": [owner], "groupPolicy": "allowlist", "allowBots": "mentions",
              "joinIntro": False, "accounts": {}}
    for role, bot in bots.items():
        result["accounts"][account_id(role)] = {
            "enabled": True, "name": ROLES[role].handle, "applicationId": bot["application"],
            "token": {"source": "env", "provider": "default", "id": token_key(role)},
            "dmPolicy": "allowlist", "allowFrom": [owner],
            "groupPolicy": "allowlist", "allowBots": "mentions",
            "joinIntro": False, "replyToMode": "off", "streaming": {"mode": "off"},
            "mentionAliases": dict(aliases),
            "botLoopProtection": {"enabled": True, "maxEventsPerWindow": 8,
                                  "windowSeconds": 60, "cooldownSeconds": 120},
            "guilds": {guild: {
                "users": [owner, *(other["user"] for other in bots.values())],
                "requireMention": True, "ignoreOtherMentions": True,
                "channels": {room: {"enabled": True, "requireMention": room != bot["channel"],
                                    "ignoreOtherMentions": True}
                             for room in sorted(rooms)},
            }},
        }
    return result


def check_existing(discord, shared, bots):
    """Refuse to overwrite Discord settings this helper did not generate."""
    if not discord:
        return
    expected = {account_id(role) for role in ROLES}
    accounts = discord.get("accounts", {"default": discord})
    if set(accounts) - expected:
        raise ValueError("Unexpected Discord accounts exist; merge them manually.")
    rooms = {shared["TEAM_CHANNEL_ID"], *(bot["channel"] for bot in bots.values() if bot["channel"])}
    for account in accounts.values():
        guilds = account.get("guilds", {})
        if set(guilds) - {shared["GUILD_ID"]}:
            raise ValueError("Unexpected Discord guild exists; merge it manually.")
        for guild in guilds.values():
            if set(guild.get("channels", {})) - rooms:
                raise ValueError("Unexpected Discord channel exists; merge it manually.")


def build_config(config, bots):
    """Bind each account to its agent and keep bounded delegation available."""
    roster = config.get("agents", {}).get("entries", {})
    missing = [role for role in bots if role not in roster]
    if missing:
        raise ValueError("Agents missing from the active config: " + ", ".join(missing))
    if config.get("broadcast"):
        raise ValueError("Unexpected broadcast configuration exists; review it manually.")
    updated = copy.deepcopy(config)
    expected = {account_id(role) for role in ROLES}
    bindings = []
    for binding in updated.get("bindings", []):
        match = binding.get("match", {})
        if match.get("channel") != "discord":
            bindings.append(binding)
        elif binding.get("agentId") not in ROLES or match.get("accountId", "default") not in expected:
            raise ValueError("Unexpected Discord binding exists; merge it manually.")
    # Account bindings cover DMs, which have no guild ID, as well as server
    # messages. The guild and channel allowlists still gate server access.
    bindings.extend({"agentId": role, "match": {"channel": "discord", "accountId": account_id(role)}}
                    for role in bots)
    updated["bindings"] = bindings
    updated.setdefault("channels", {})["discord"] = {"$include": INCLUDE}
    updated.setdefault("plugins", {}).setdefault("entries", {}).setdefault("discord", {})["enabled"] = True
    # Child tasks return to the requesting conversation without exposing peers'
    # sessions or enabling outbound message tools.
    tools = updated.setdefault("tools", {})
    allowed = tools.setdefault("alsoAllow", [])
    allowed.extend(name for name in DELEGATION_TOOLS if name not in allowed)
    tools["deny"] = [name for name in tools.get("deny", []) if name not in DELEGATION_TOOLS]
    tools.setdefault("sessions", {})["visibility"] = "tree"
    updated["agents"].setdefault("defaults", {}).setdefault("subagents", {}).update(SUBAGENTS)
    return updated


def build_plan(config, env, existing=None):
    shared, bots = read_credentials(env)
    check_existing(existing, shared, bots)
    return build_config(config, bots), build_discord(shared, bots), bots


def render_instructions(template, role, bots):
    teammates = ", ".join("@" + ROLES[other].handle for other in bots)
    return Template(template).substitute(role_name=ROLES[role].name, handle=ROLES[role].handle,
                                         teammates=teammates).strip()


def prepare_instructions(config, env, bots, template=None, project=None):
    """Replace only our section; retain each agent's other workspace rules."""
    project = Path(project or native.PROJECT).resolve()
    template = TEMPLATE.read_text() if template is None else template
    changes = []
    for role in bots:
        workspace = Template(config["agents"]["entries"][role]["workspace"]).substitute(env)
        path = (Path(workspace) / "AGENTS.md").resolve()
        if not path.is_relative_to(project):
            raise ValueError(f"The {role} workspace is outside this checkout; review it manually.")
        before = path.read_bytes()
        text = before.decode("utf-8")
        lines = text.splitlines(keepends=True)
        starts = [i for i, line in enumerate(lines) if line.rstrip("\r\n") == MARKER]
        if len(starts) > 1:
            raise ValueError(f"The {role} workspace has duplicate collaboration sections.")
        section = render_instructions(template, role, bots)
        if starts:
            start = starts[0]
            end = next((i for i in range(start + 1, len(lines))
                        if lines[i].startswith(("# ", "## "))), len(lines))
            prefix, suffix = "".join(lines[:start]), "".join(lines[end:])
        else:
            prefix, suffix = text, ""
        after = prefix.rstrip() + "\n\n" + section + "\n"
        if suffix:
            after += "\n" + suffix
        changes.append((role, path, before, after.encode("utf-8")))
    return changes


def expand_includes(value, base, root=None, seen=frozenset()):
    root = root or base.resolve()
    if isinstance(value, list):
        return [expand_includes(item, base, root, seen) for item in value]
    if not isinstance(value, dict):
        return value
    if "$include" in value:
        if len(value) != 1 or not isinstance(value["$include"], str):
            raise ValueError("Unsupported include layout; review it manually.")
        path = (base / value["$include"]).resolve()
        if not path.is_relative_to(root) or path in seen:
            raise ValueError("Config include escapes its directory or contains a cycle.")
        return expand_includes(json.loads(path.read_text()), path.parent, root, seen | {path})
    return {key: expand_includes(item, base, root, seen) for key, item in value.items()}


def save_json(path, data):
    with path.open("x") as output:
        os.chmod(path, 0o600)
        json.dump(data, output, indent=2)
        output.write("\n")


def check_credentials(env, bots):
    for role, bot in bots.items():
        request = urllib.request.Request("https://discord.com/api/v10/users/@me", headers={
            "Authorization": "Bot " + env[token_key(role)].strip(),
            "User-Agent": "openclaw-team-starter discord configuration",
        })
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                identity = json.load(response)
        except urllib.error.HTTPError as error:
            raise ValueError(f"Discord credential check failed for {role}: HTTP {error.code}") from None
        except (urllib.error.URLError, TimeoutError):
            raise ValueError(f"Discord credential check could not reach Discord for {role}.") from None
        if not identity.get("bot") or str(identity.get("id")) != bot["user"]:
            raise ValueError(f"Discord token identity does not match the configured {role} bot.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true",
                        help="Verify credentials and activate configuration and agent instructions")
    args = parser.parse_args()
    env = native.runtime_env("openclaw")
    source = Path(env["OPENCLAW_CONFIG_PATH"])
    before = source.read_bytes()
    config = json.loads(before)
    private = source.parent / INCLUDE
    current = config.get("channels", {}).get("discord")
    private_before = private.read_bytes() if private.is_file() else None
    if current == {"$include": INCLUDE}:
        existing = json.loads(private_before) if private_before else {}
    elif isinstance(current, dict):
        existing = current
    else:
        existing = {}
    updated, discord, bots = build_plan(config, env, existing)
    instructions = prepare_instructions(updated, env, bots)
    binary = shutil.which("openclaw", path=env.get("PATH"))
    if not binary:
        raise ValueError("OpenClaw is unavailable through the native wrapper.")
    output = native.PROJECT / ".local/discord-collaboration" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output.mkdir(parents=True, mode=0o700)
    candidate = copy.deepcopy(updated)
    candidate["channels"]["discord"] = discord
    candidate = expand_includes(candidate, source.parent)
    save_json(output / "openclaw.private.json", updated)
    save_json(output / "discord.private.json", discord)
    save_json(output / "candidate.private.json", candidate)
    (output / "agents").mkdir(mode=0o700)
    for role, _, _, after in instructions:
        staged = output / "agents" / f"{role}.AGENTS.md"
        staged.write_bytes(after)
        staged.chmod(0o600)
    checked = subprocess.run([binary, "config", "validate"],
                             env=dict(env, OPENCLAW_CONFIG_PATH=str(output / "candidate.private.json")),
                             cwd=native.PROJECT, text=True, capture_output=True)
    log = output / "validation.private.txt"
    log.write_text(checked.stdout + checked.stderr)
    log.chmod(0o600)
    if checked.returncode:
        raise ValueError(f"Candidate validation failed; inspect {log} privately.")
    report = checked.stdout + checked.stderr
    if "plugin not installed: discord" in report:
        raise ValueError("The Discord channel plugin is not installed. Run "
                         "python3 scripts/native.py openclaw plugins install @openclaw/discord@2026.9.6 and rerun.")
    for line in report.splitlines():
        if line.lstrip().startswith("!"):
            print("Validation warning:", line.strip())
    configured = ", ".join(ROLES[role].name for role in bots)
    skipped = ", ".join(ROLES[role].name for role in ROLES if role not in bots)
    print(f"Discord bots: {configured}.")
    if skipped:
        print(f"No token, not on Discord: {skipped}. They stay reachable through delegation.")
    if args.apply:
        check_credentials(env, bots)
        current_private = private.read_bytes() if private.is_file() else None
        if (source.read_bytes() != before or current_private != private_before
                or any(path.read_bytes() != original for _, path, original, _ in instructions)):
            raise ValueError("Live configuration changed during validation; generate a fresh plan.")
        backups = [(source, before)] + ([(private, private_before)] if private_before else [])
        for path, data in backups:
            backup = output / (path.name + ".before")
            backup.write_bytes(data)
            backup.chmod(0o600)
        for role, _, original, _ in instructions:
            backup = output / "agents" / f"{role}.AGENTS.md.before"
            backup.write_bytes(original)
            backup.chmod(0o600)
        # Each replace is atomic. The operator restarts only after all finish.
        for path, name in ((private, "discord.private.json"), (source, "openclaw.private.json")):
            temporary = path.with_name(path.name + ".discord-team.tmp")
            shutil.copyfile(output / name, temporary)
            temporary.chmod(0o600)
            temporary.replace(path)
        for _, path, _, after in instructions:
            temporary = path.with_name(path.name + ".discord-team.tmp")
            temporary.write_bytes(after)
            temporary.chmod(stat.S_IMODE(path.stat().st_mode))
            temporary.replace(path)
        print("Verified the bot identities and activated their configuration and instructions.")
        print("Restart the Gateway, then probe the Discord accounts and send a test mention.")
    else:
        print("Candidate validated. Active configuration and services are unchanged.")
    print(f"Private review files: {output}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError) as error:
        sys.exit(f"Stopped: {error}")
