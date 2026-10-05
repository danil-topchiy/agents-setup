#!/usr/bin/env python3
"""Operator commands that put the OpenClaw agent team on a Paperclip board."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(PROJECT / "scripts"))
import run  # noqa: E402
from native import gateway_port, project_values  # noqa: E402

PRIVATE = ROOT / ".local"
STATE = PRIVATE / "team.json"
BOARD_TOKEN = PRIVATE / "board-token"
BASE = run.base_url()
# OpenClaw agent ID -> (display name, Paperclip role)
ROLES = {"main": ("Chief of Staff", "general"), "cto": ("CTO", "cto"), "swe": ("SWE", "engineer"),
         "qa": ("QA", "qa"), "ui-ux": ("UI/UX", "designer"), "content": ("Content", "general"),
         "generalist": ("Generalist", "researcher"), "infrastructure": ("Infrastructure", "devops"),
         "sales": ("Sales", "general")}
TRUE = shutil.which("true") or "/usr/bin/true"
COMPANY_NAME = "Agent team"
GOAL = "Deliver reviewed, verifiable work"
PROJECT_NAME = "Team operations"


def save(path, value):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2) + "\n")
    temp.chmod(0o600)
    temp.replace(path)


def api(method, path, body=None):
    headers = {"Content-Type": "application/json"}
    if BOARD_TOKEN.is_file():
        headers["Authorization"] = "Bearer " + BOARD_TOKEN.read_text().strip()
    req = urllib.request.Request(BASE + path, method=method, headers=headers,
                                 data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode()[:800]
        if error.code in (401, 403) and not BOARD_TOKEN.is_file():
            detail += " | Paperclip requires login; save a board API key in paperclip/.local/board-token (mode 0600)."
        raise RuntimeError(f"{method} {path}: HTTP {error.code}: {detail}") from None
    except OSError as error:
        raise RuntimeError(f"Paperclip is not reachable at {BASE}: {error}") from None


def state():
    if not STATE.exists():
        raise SystemExit("Run `python3 paperclip/team.py seed` first.")
    return json.loads(STATE.read_text())


def find(items, key, value):
    matches = [item for item in items if item.get(key) == value]
    return matches[0] if matches else None


def seed(company_name):
    s = json.loads(STATE.read_text()) if STATE.exists() else {}
    if "company" not in s:
        company = find(api("GET", "/api/companies"), "name", company_name) or api("POST", "/api/companies", {
            "name": company_name,
            "description": "The OpenClaw agent team: task ownership, dependencies, human review and reported-cost budgets."})
        s["company"] = company["id"]
        save(STATE, s)
    company = s["company"]
    api("PATCH", f"/api/companies/{company}/budgets", {"budgetMonthlyCents": 2000})
    if "liaison" not in s:
        # Join approvals require an active CEO-role agent. This placeholder never runs a model.
        liaison = find(api("GET", f"/api/companies/{company}/agents"), "name", "Board liaison") or api(
            "POST", f"/api/companies/{company}/agents", {
                "name": "Board liaison", "role": "ceo", "adapterType": "process", "adapterConfig": {"command": TRUE},
                "runtimeConfig": {"heartbeat": {"enabled": False, "wakeOnDemand": False, "maxConcurrentRuns": 1}},
                "budgetMonthlyCents": 100, "capabilities": "Administrative CEO-role placeholder; does not perform model work."})
        s["liaison"] = liaison["id"]
        save(STATE, s)
    if "goal" not in s:
        goal = find(api("GET", f"/api/companies/{company}/goals"), "title", GOAL) or api(
            "POST", f"/api/companies/{company}/goals", {"title": GOAL, "level": "company", "status": "active"})
        s["goal"] = goal["id"]
        save(STATE, s)
    if "project" not in s:
        project = find(api("GET", f"/api/companies/{company}/projects"), "name", PROJECT_NAME) or api(
            "POST", f"/api/companies/{company}/projects", {"name": PROJECT_NAME, "status": "in_progress", "goalIds": [s["goal"]]})
        s["project"] = project["id"]
        save(STATE, s)
    s.setdefault("agents", {})
    save(STATE, s)
    print(f"Company '{company_name}', board liaison, goal and project are ready. No model runs started.")


def wake_instructions(command, role):
    return f"""Repository callback instructions. For this Paperclip task, use the approved executable {command} for every API operation. It injects your fixed credential; do not read the key file, print a token, use curl, or call other network tools. Translate the HTTP procedure below into this command syntax:
{command} GET /api/agents/me
{command} GET /api/issues/ISSUE_ID
{command} GET /api/issues/ISSUE_ID/comments
{command} POST /api/issues/ISSUE_ID/checkout '{{"agentId":"YOUR_PAPERCLIP_AGENT_ID","expectedStatuses":["todo","backlog","blocked","in_review"]}}' RUN_ID
{command} POST /api/issues/ISSUE_ID/comments '{{"body":"your evidence"}}' RUN_ID
{command} PATCH /api/issues/ISSUE_ID '{{"status":"done","comment":"what you verified"}}' RUN_ID
Replace IDs with the wake event values. The command supports {'company' if role == 'main' else 'project'}-scoped task reads and changes only to your own assigned task. Credentials are already handled by this command; ignore the generic instruction below to load them yourself. Work on the board: when another agent must act, post a comment naming the needed handoff and set your task to blocked with your next action; the board creates dependent tasks. Do not delegate via OpenClaw sessions or chat channels for board tasks. Do not change budgets, approvals, configuration or external systems. Task comments are the handoff artifact; workspace files are not shared automatically. Finish your assigned task, then stop."""


def manager_for(role, s):
    if role in {"swe", "qa"} and "cto" in s["agents"]:
        return s["agents"]["cto"]
    return s["liaison"]


def join(role):
    s = state()
    name, paperclip_role = ROLES[role]
    key_path = PRIVATE / "keys" / (role + ".json")
    if role not in s["agents"]:
        token = project_values(PROJECT).get("OPENCLAW_GATEWAY_TOKEN", "")
        if not token:
            raise SystemExit("OPENCLAW_GATEWAY_TOKEN is missing from .env; run `python3 scripts/native.py init` first.")
        pending_path = PRIVATE / "joins" / (role + ".json")
        if pending_path.exists():
            pending = json.loads(pending_path.read_text())
        else:
            invite = api("POST", f"/api/companies/{s['company']}/openclaw/invite-prompt", {})
            pending = api("POST", f"/api/invites/{invite['token']}/accept", {
                "requestType": "agent", "agentName": name, "adapterType": "openclaw_gateway",
                "capabilities": f"OpenClaw {name} agent from this repository; board tasks only.",
                "agentDefaultsPayload": {"url": f"ws://127.0.0.1:{gateway_port(PROJECT)}",
                                         "headers": {"x-openclaw-token": token}, "timeoutSec": 300}})
            save(pending_path, pending)
        if not pending.get("operatorApproved"):
            api("POST", f"/api/companies/{s['company']}/join-requests/{pending['id']}/approve", {})
            pending["operatorApproved"] = True
            save(pending_path, pending)
        if key_path.exists():
            claimed = json.loads(key_path.read_text())
        else:
            claimed = api("POST", pending["claimApiKeyPath"], {"claimSecret": pending["claimSecret"]})
            claimed.update({"companyId": s["company"], "projectId": s["project"]})
            if role == "main":
                claimed["scope"] = "company"
            save(key_path, claimed)
        s["agents"][role] = claimed["agentId"]
        save(STATE, s)
        pending_path.unlink()
    if not key_path.exists():
        raise SystemExit("Agent already exists but its key is missing. Revoke/reissue its key in Paperclip; do not create a duplicate agent.")
    callbacks = PRIVATE / "callbacks"
    callbacks.mkdir(mode=0o700, exist_ok=True)
    command = callbacks / role
    command.write_text(f"#!{sys.executable}\nimport sys\nsys.path.insert(0, {str(ROOT)!r})\nfrom callback import main\nmain({role!r})\n")
    command.chmod(0o700)
    api("PATCH", f"/api/agents/{s['agents'][role]}", {
        "reportsTo": manager_for(role, s), "role": paperclip_role,
        "adapterConfig": {"agentId": role, "sessionKeyStrategy": "issue", "paperclipApiUrl": BASE,
                          "claimedApiKeyPath": str(key_path), "timeoutSec": 300,
                          "payloadTemplate": {"message": wake_instructions(command, role)}},
        "runtimeConfig": {"heartbeat": {"enabled": False, "wakeOnDemand": True, "cooldownSec": 10,
                                        "maxConcurrentRuns": 1, "maxDailyRuns": 15}}})
    api("PATCH", f"/api/agents/{s['agents'][role]}/budgets", {"budgetMonthlyCents": 300})
    result = subprocess.run([sys.executable, str(PROJECT / "scripts/native.py"), "openclaw", "approvals", "allowlist",
                             "add", "--agent", role, str(command), "--json"], cwd=PROJECT, capture_output=True, text=True)
    if result.returncode:
        raise SystemExit("Agent joined, but the callback allowlist entry failed. Is the Gateway running? "
                         "Inspect `python3 scripts/native.py openclaw approvals get` locally; no broad exec policy was changed.")
    agent = api("GET", f"/api/agents/{s['agents'][role]}")
    config = agent["adapterConfig"]
    expected = f"ws://127.0.0.1:{gateway_port(PROJECT)}"
    if config.get("agentId") != role or str(config.get("url", "")).rstrip("/") != expected:
        raise SystemExit("Adapter settings did not persist as expected; inspect the agent in Paperclip before using it.")
    print(f"{name} joined: named-agent routing, callback allowlist entry, on-demand wakes and a $3 monthly budget.")


def issue(s, title, description, role, **extra):
    return api("POST", f"/api/companies/{s['company']}/issues", {
        "title": title, "description": description, "projectId": s["project"], "goalId": s["goal"],
        "assigneeAgentId": s["agents"][role], "status": "todo", **extra})


def smoke(role):
    s = state()
    if role not in s["agents"]:
        raise SystemExit(f"Join {role} first.")
    item = issue(s, f"Smoke test {ROLES[role][0]}", "Post a comment containing OK and your OpenClaw role. Mark this task done "
                 "with a short verification comment. Do not do other work or contact anyone.", role)
    s.setdefault("smoke", {})[role] = item["id"]
    save(STATE, s)
    print(f"Created {item['identifier']}; verify done plus an actual agent comment in Paperclip.")


def workflow():
    s = state()
    if not all(role in s["agents"] for role in ("cto", "swe", "qa")):
        raise SystemExit("Join cto, swe and qa first.")
    parent = issue(s, "Plan a greeting function change", "Example teaching task. Specify acceptance criteria for greet(name): "
                   "trim surrounding whitespace; an empty/whitespace-only name returns 'Hello, world!'; otherwise return "
                   "'Hello, NAME!'. Add three examples in a task comment, mark done. The board has already created the dependent "
                   "SWE and QA tasks. Do not create or delegate anything else.", "cto")
    implementation = issue(s, "Implement the greeting function in a task comment",
                           f"Read the task and comments for {parent['id']}. Write a small Python greet(name) implementation and three "
                           "assertions as a fenced code block in a task comment. Do not run shell commands except the Paperclip "
                           "callback. State that this is an unexecuted code draft, then mark done. The QA task depends on this one.",
                           "swe", parentId=parent["id"], blockedByIssueIds=[parent["id"]])
    review = issue(s, "Review the greeting change and submit for human approval",
                   f"Read issue {implementation['id']} and its comments. Manually inspect the Python draft against trim, blank-name "
                   "fallback, and greeting formatting. Walk through three cases; clearly label this manual review, not executed "
                   "tests. Post a PASS or FAIL verdict with evidence, then mark done. A human approval stage must decide acceptance. "
                   "Do not execute code or approve your own work.",
                   "qa", parentId=parent["id"], blockedByIssueIds=[implementation["id"]],
                   executionPolicy={"stages": [{"type": "approval", "participants": [{"type": "user", "userId": "local-board"}]}]})
    s["workflow"] = {"plan": parent["id"], "implementation": implementation["id"], "review": review["id"]}
    save(STATE, s)
    print("Created dependency chain:", parent["identifier"], "->", implementation["identifier"], "->", review["identifier"])


def review(decision):
    s = state()
    if "workflow" not in s:
        raise SystemExit("Run workflow first.")
    current = api("GET", f"/api/issues/{s['workflow']['review']}")
    if current["status"] != "in_review":
        raise SystemExit("Wait for the task to reach in_review and inspect its evidence before deciding.")
    if decision == "approve":
        note = "Acceptance criteria and manual-review evidence checked; accepted."
    else:
        note = ("Please add a manual walkthrough for input '  Ada  Lovelace  ', showing that the two internal spaces and "
                "letter case are preserved. Keep the distinction between manual review and executed tests explicit.")
    # A board PATCH to todo clears the stage without restoring the worker; in_progress plus a comment requests changes.
    item = api("PATCH", f"/api/issues/{s['workflow']['review']}",
               {"status": "done" if decision == "approve" else "in_progress", "comment": note})
    print("Review decision recorded:", item["status"])


def budget(action):
    s = state()
    if action == "new":
        fixture = api("POST", f"/api/companies/{s['company']}/agents", {
            "name": "Synthetic budget fixture " + datetime.now().strftime("%H%M%S"), "role": "general",
            "reportsTo": s["liaison"], "adapterType": "process", "adapterConfig": {"command": TRUE},
            "runtimeConfig": {"heartbeat": {"enabled": False, "wakeOnDemand": True, "maxConcurrentRuns": 1}},
            "budgetMonthlyCents": 100})
        s["budgetFixture"] = fixture["id"]
        s["budgetPosted"] = []
        save(STATE, s)
        print("Fresh $1 fixture created. It makes no model calls.")
        return
    agent_id = s.get("budgetFixture")
    if not agent_id:
        raise SystemExit("Run budget new first.")
    if action in {"80", "100"}:
        if action in s.get("budgetPosted", []):
            raise SystemExit("That fixture event is already posted. Use budget new for another demonstration.")
        if action == "100" and "80" not in s.get("budgetPosted", []):
            raise SystemExit("Post budget 80 first.")
        api("POST", f"/api/companies/{s['company']}/cost-events", {
            "agentId": agent_id, "provider": "simulated", "model": "no-model-call",
            "billingCode": "SYNTHETIC-BUDGET-TEST", "costCents": 80 if action == "80" else 20,
            "occurredAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")})
        s.setdefault("budgetPosted", []).append(action)
        save(STATE, s)
        print("Synthetic reported total:", action, "cents; actual provider spend: $0.")
    elif action == "wake":
        try:
            api("POST", f"/api/agents/{agent_id}/wakeup", {"source": "on_demand", "triggerDetail": "manual",
                                                           "reason": "Budget gate verification"})
            print("Wake accepted.")
        except RuntimeError as error:
            if "HTTP 409" not in str(error):
                raise
            print("Expected 409: the budget-paused fixture cannot wake.")
    elif action == "recover":
        overview = api("GET", f"/api/companies/{s['company']}/budgets/overview")
        matches = [i for i in overview.get("activeIncidents", [])
                   if i.get("scopeId") == agent_id and i.get("status") == "open" and i.get("thresholdType") == "hard"]
        if not matches:
            raise SystemExit("No open hard incident found. Inspect Budgets in the UI.")
        for incident in matches:
            api("POST", f"/api/companies/{s['company']}/budget-incidents/{incident['id']}/resolve", {
                "action": "raise_budget_and_resume", "amount": 200,
                "decisionNote": "Operator decision: synthetic costs only; raise the fixture to $2 and resume."})
        print("Recorded budget decision; fixture raised to $2 and resumed.")


def routine(action):
    s = state()
    if "cto" not in s["agents"]:
        raise SystemExit("Join CTO first.")
    if "routine" not in s:
        r = api("POST", f"/api/companies/{s['company']}/routines", {
            "title": "Weekly status briefing example", "projectId": s["project"], "goalId": s["goal"],
            "assigneeAgentId": s["agents"]["cto"], "status": "paused",
            "description": "Example notes: implementation draft complete; QA review pending; no release date approved. "
                           "Write a three-bullet status comment preserving these qualifications. Do not access mail, send "
                           "messages or invent a release commitment. Mark the task done.",
            "concurrencyPolicy": "coalesce_if_active", "catchUpPolicy": "skip_missed"})
        s["routine"] = r["id"]
        save(STATE, s)
    if action == "run":
        api("PATCH", f"/api/routines/{s['routine']}", {"status": "active"})
        try:
            result = api("POST", f"/api/routines/{s['routine']}/run", {})
            save(PRIVATE / "routine-run.json", result)
        finally:
            api("PATCH", f"/api/routines/{s['routine']}", {"status": "paused"})
        print("Manual routine fired; routine paused again. Inspect its generated task.")
    else:
        print("Paused routine prepared. No schedule or webhook is enabled.")


def redact(text, secrets, project_dir):
    for secret in secrets:
        if secret:
            text = text.replace(secret, "RECONNECT_REQUIRED")
    text = re.sub(r"-----BEGIN[^-]*PRIVATE KEY-----.*?-----END[^-]*PRIVATE KEY-----", "REGENERATE_DEVICE_KEY", text, flags=re.S)
    text = re.sub(r"^.*devicePrivateKeyPem:.*\n?", "", text, flags=re.M)
    return text.replace(project_dir, "PROJECT_DIR")


def export_company():
    s = state()
    destination = PRIVATE / "exports" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    result = subprocess.run([sys.executable, str(ROOT / "run.py"), "company", "export", s["company"],
                             "--out", str(destination), "--include", "company,agents,projects", "--json"],
                            cwd=ROOT, capture_output=True, text=True)
    save(PRIVATE / "export-result.json", {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
    if result.returncode:
        raise SystemExit("Export failed; inspect paperclip/.local/export-result.json privately.")
    # This release keeps Gateway headers and the device private key in YAML. Keep raw
    # exports private; create a separate copy with those removed for review and sharing.
    secrets = [project_values(PROJECT).get("OPENCLAW_GATEWAY_TOKEN", "")]
    secrets += [json.loads(p.read_text())["token"] for p in (PRIVATE / "keys").glob("*.json")]
    safe = PRIVATE / "exports-redacted" / destination.name
    shutil.copytree(destination, safe)
    for path in safe.rglob("*"):
        if path.is_file() and path.suffix in {".md", ".yaml", ".yml", ".json", ".txt"}:
            path.write_text(redact(path.read_text(), secrets, str(PROJECT)))
    print("Redacted export:", safe)
    print("Gateway credentials and device keys require fresh setup on import. The raw export stays private. "
          "This is not a database backup.")


def status():
    s = state()
    health = api("GET", "/api/health")
    # Authenticated mode answers the public health probe without version details.
    print(f"Paperclip {health.get('version', '')}: {health.get('status')} ({health.get('deploymentMode')}) at {BASE}")
    for a in api("GET", f"/api/companies/{s['company']}/agents"):
        print(f"{a['name']}: {a['status']} ({a['adapterType']})")
    for item in api("GET", f"/api/companies/{s['company']}/issues"):
        print(f"{item['identifier']}: {item['status']} - {item['title']}")


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("seed", help="Create the company, board liaison, goal and project")
    p.add_argument("--company", default=COMPANY_NAME)
    for name in ("workflow", "status", "export"):
        sub.add_parser(name)
    for name in ("join", "smoke"):
        p = sub.add_parser(name)
        p.add_argument("role", choices=list(ROLES))
    p = sub.add_parser("review")
    p.add_argument("decision", choices=["return", "approve"])
    p = sub.add_parser("budget")
    p.add_argument("action", choices=["new", "80", "100", "wake", "recover"])
    p = sub.add_parser("routine")
    p.add_argument("action", choices=["prepare", "run"])
    args = parser.parse_args()
    try:
        if args.command == "seed":
            seed(args.company)
        elif args.command == "join":
            join(args.role)
        elif args.command == "smoke":
            smoke(args.role)
        elif args.command == "workflow":
            workflow()
        elif args.command == "review":
            review(args.decision)
        elif args.command == "budget":
            budget(args.action)
        elif args.command == "routine":
            routine(args.action)
        elif args.command == "export":
            export_company()
        else:
            status()
    except (RuntimeError, OSError, ValueError) as error:
        raise SystemExit(str(error))


if __name__ == "__main__":
    main()
