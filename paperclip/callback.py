#!/usr/bin/env python3
"""Narrow credential-injecting callback for connected OpenClaw agents.

This is a repository helper, not a Paperclip feature or an OS sandbox.
The generated executable fixes the agent identity; arguments never contain keys.
"""
import json
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import run  # noqa: E402

BASE = run.base_url()
UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"


def request(role, method, path, body=None, run_id=None):
    secret = json.loads((ROOT / ".local/keys" / (role + ".json")).read_text())
    if method not in {"GET", "POST", "PATCH"}:
        raise ValueError("Only GET, POST and PATCH are supported")
    headers = {"Authorization": "Bearer " + secret["token"], "Content-Type": "application/json"}

    def send(verb, endpoint, payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(BASE + endpoint, data=data, headers=headers, method=verb)
        try:
            with urllib.request.urlopen(req, timeout=25) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            raise ValueError(f"Paperclip HTTP {error.code}: {error.read().decode()[:600]}") from None

    if path == "/api/agents/me" and method == "GET":
        agent = send(method, path)
        return {k: agent.get(k) for k in ("id", "companyId", "name", "role", "status", "reportsTo")}
    match = re.fullmatch(r"/api/issues/(" + UUID + r")(/comments|/checkout)?", path)
    if not match:
        raise ValueError("Only identity and issue read/checkout/comment/status endpoints are allowed")
    issue_id, suffix = match.group(1), match.group(2) or ""
    issue = send("GET", "/api/issues/" + issue_id)
    scope = secret.get("scope", "project")
    if scope not in {"project", "company"}:
        raise ValueError("Unknown callback scope")
    if issue["companyId"] != secret["companyId"]:
        raise ValueError("Issue is outside this agent's company")
    if scope == "project" and issue.get("projectId") != secret["projectId"]:
        raise ValueError("Issue is outside the configured project")
    if method == "GET":
        if suffix not in {"", "/comments"}:
            raise ValueError("Unsupported read")
        return issue if not suffix else send(method, path)
    if issue.get("assigneeAgentId") != secret["agentId"]:
        raise ValueError("Only this agent's assigned tasks may be changed; human reviews stay human")
    if not isinstance(run_id, str) or not re.fullmatch(UUID, run_id):
        raise ValueError("Supply the current PAPERCLIP_RUN_ID for every mutation")
    headers["X-Paperclip-Run-Id"] = run_id
    if not isinstance(body, dict):
        raise ValueError("Mutation body must be a JSON object")
    if method == "POST" and suffix == "/checkout":
        if set(body) - {"agentId", "expectedStatuses"} or body.get("agentId") != secret["agentId"]:
            raise ValueError("Checkout must use this agent's identity")
    elif method == "POST" and suffix == "/comments":
        if set(body) != {"body"} or not isinstance(body["body"], str):
            raise ValueError("Supply only a comment body")
    elif method == "PATCH" and suffix == "":
        if set(body) - {"status", "comment"} or body.get("status") not in {"in_progress", "blocked", "done"}:
            raise ValueError("Only progress, blocked, done and a comment may be set")
        if body["status"] == "blocked":
            action = body.get("comment")
            if not isinstance(action, str) or not action.strip() or len(action) > 2000:
                raise ValueError("Blocked needs a comment naming the blocker and this agent's next action (1-2000 characters)")
            body = {**body, "unblockDescriptor": {
                "owner": {"agentId": secret["agentId"]}, "action": action.strip(),
            }}
    else:
        raise ValueError("Operation outside callback scope")
    return send(method, path, body)


def main(role):
    try:
        if len(sys.argv) not in {3, 5}:
            raise ValueError("Usage: CALLBACK GET /api/agents/me | CALLBACK METHOD /api/issues/ID[/comments|/checkout] 'JSON_BODY' RUN_ID")
        method, path = sys.argv[1:3]
        body = json.loads(sys.argv[3]) if len(sys.argv) == 5 else None
        run_id = sys.argv[4] if len(sys.argv) == 5 else None
        result = request(role, method, path, body, run_id)
        print(json.dumps(result))
    except (ValueError, KeyError, OSError) as error:
        raise SystemExit(str(error))
