#!/usr/bin/env python3
"""Check the versionable OpenClaw JSON without printing private values."""
import json
from pathlib import Path
import re
import sys

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "docker"))
from init import env_values

EMAIL = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def private_values(project):
    values = {}
    for path in (project / ".env", project / ".local/openclaw.env",
                 project / ".local/native/hermes/.env"):
        values.update(env_values(path))
    private = {value for key, value in values.items() if value and (
        key.startswith("OPENCLAW_PRIVATE_") or
        key.endswith(("_TOKEN", "_PASSWORD", "_SECRET", "_KEY", "_EMAIL", "_USERS", "_CHATS", "_ID", "_IDS")))}
    path = project / "config/openclaw-auth.private.json"
    if path.is_file():
        private.update(json.loads(path.read_text()).get("profiles", {}))
    hermes_auth = project / ".local/native/hermes/auth.json"
    if hermes_auth.is_file():
        def visit(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    if isinstance(child, str) and child and re.search(r"(?:key|token|password|secret|email|account_id|user_id|profile_id)$", key, re.I):
                        private.add(child)
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)
        visit(json.loads(hermes_auth.read_text()))
    return private


def find_issues(text, private):
    data = json.loads(text)
    strings = []
    inline_credentials = []

    def visit(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key.lower() in {"token", "bottoken", "apikey", "password", "secret"} and isinstance(child, str) and child and not re.fullmatch(r"\$\{[A-Z_][A-Z0-9_]*\}", child):
                    inline_credentials.append(key)
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
        elif isinstance(value, str):
            strings.append(value)

    visit(data)
    issues = []
    if EMAIL.search(text):
        issues.append("An email address is present in the versionable config.")
    if any(value in text if len(value) >= 8 else value in strings for value in private):
        issues.append("A known private value is present in the versionable config.")
    if inline_credentials:
        issues.append("An inline credential belongs in a private secret reference.")
    if isinstance(data.get("auth"), dict) and data["auth"].get("profiles"):
        issues.append("Account profiles belong in the ignored private auth include.")
    owners = data.get("commands", {}).get("ownerAllowFrom", [])
    if any(isinstance(value, str) and value != "*" and not re.search(r"\$\{[A-Z_][A-Z0-9_]*\}", value)
           for value in owners):
        issues.append("Owner identifiers belong in private environment references.")
    return issues


def main():
    try:
        issues = find_issues((PROJECT / "config/openclaw.json").read_text(), private_values(PROJECT))
    except (OSError, ValueError):
        sys.exit("Privacy check stopped: review the config and private files locally.")
    if issues:
        for issue in issues:
            print(issue, file=sys.stderr)
        sys.exit("Do not commit this config; replace personal values with private references.")
    print("OpenClaw config privacy check passed. Review new UI changes before committing.")


if __name__ == "__main__":
    main()
