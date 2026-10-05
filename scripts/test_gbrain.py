#!/usr/bin/env python3
"""Policy regression checks; --live also verifies the running shared server and watcher."""
import concurrent.futures
import copy
import json
import os
from pathlib import Path
import sys
import time
import tempfile
import unittest
import urllib.error
import uuid
from unittest.mock import patch

import gbrain


class GbrainPolicyTests(unittest.TestCase):
    def fixture(self):
        return {"agents": {"entries": {
            **{agent: {"tools": {"deny": ["*__*", "group:web"], "alsoAllow": ["read"]}}
               for agent in gbrain.TEAM},
            "restricted-agent": {"tools": {"allow": ["session_status"], "deny": ["group:plugins"]}},
            "maintenance-agent": {"memory": {"search": {"enabled": False}}},
        }}, "mcp": {"servers": {"example": {"url": "https://example.com/mcp"}}},
                "tools": {"alsoAllow": ["group:memory"]}, "memory": {"search": {"enabled": True}}}

    def test_preserves_private_agents_and_unrelated_configuration(self):
        original = self.fixture()
        before = copy.deepcopy(original)
        updated = gbrain.configure_data(original)
        self.assertEqual(original, before)
        for key in ["restricted-agent", "maintenance-agent"]:
            self.assertEqual(updated["agents"]["entries"][key], original["agents"]["entries"][key])
        self.assertEqual(updated["memory"], original["memory"])
        self.assertEqual(updated["mcp"]["servers"]["example"], original["mcp"]["servers"]["example"])
        for agent in gbrain.TEAM:
            policy = updated["agents"]["entries"][agent]["tools"]
            self.assertNotIn("*__*", policy["deny"])
            self.assertIn("example__*", policy["deny"])
            self.assertIn("group:web", policy["deny"])
            self.assertIn("gbrain__get_page", policy["alsoAllow"])
            self.assertNotIn("gbrain__put_page", policy["alsoAllow"])
        self.assertEqual(gbrain.configure_data(updated), updated)

    def test_environment_cannot_inherit_provider_keys_or_another_brain(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "not-a-real-key", "DATABASE_URL": "wrong-db",
                                    "GBRAIN_HOME": "/wrong-brain", "GBRAIN_SOURCE": "private"}):
            env = gbrain.environment()
            for key in ["OPENAI_API_KEY", "DATABASE_URL", "GBRAIN_SOURCE"]:
                self.assertNotIn(key, env)
            self.assertEqual(env["GBRAIN_HOME"], str(gbrain.ROOT / "home"))

    def test_adding_agent_permissions_preserves_inherited_native_tools(self):
        original = self.fixture()
        original["agents"]["entries"]["qa"]["tools"].pop("alsoAllow")
        original["tools"]["alsoAllow"] = ["read", "write", "exec", "group:memory", "sessions_spawn"]
        result = gbrain.configure_data(original)
        permissions = result["agents"]["entries"]["qa"]["tools"]["alsoAllow"]
        for name in original["tools"]["alsoAllow"]:
            self.assertIn(name, permissions)
        self.assertIn("gbrain__get_page", permissions)

    def test_docker_does_not_inherit_native_gbrain_connection(self):
        import native
        from init import docker_config
        config = gbrain.configure_data(self.fixture())
        config["gateway"] = {}
        config["agents"]["entries"]["main"]["workspace"] = "${OPENCLAW_WORKSPACE_DIR}"
        with patch("init.portable_config", return_value=config):
            result = docker_config(gbrain.PROJECT, Path("/opt/chromium/chrome"))
        self.assertNotIn("gbrain", result["mcp"]["servers"])
        self.assertNotIn("GBRAIN_READER_TOKEN", json.dumps(result))

    def test_private_snapshot_records_deletions_without_changing_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            vault = root / "vault"
            vault.mkdir()
            (vault / "projects").mkdir()
            note = vault / "projects/example.md"
            note.write_text("# Example\nOne.\n")
            (vault / ".obsidian").mkdir()
            (vault / ".obsidian/private.md").write_text("must not copy")
            with patch.multiple(gbrain, ROOT=root, VAULT=vault, MIRROR=root / "mirror"):
                gbrain.snapshot()
                self.assertEqual((gbrain.MIRROR / "projects/example.md").read_bytes(), note.read_bytes())
                self.assertFalse((gbrain.MIRROR / ".obsidian").exists())
                note.unlink()
                gbrain.snapshot()
                self.assertFalse((gbrain.MIRROR / "projects/example.md").exists())
                self.assertFalse((vault / ".git").exists())


def call(name, arguments):
    response = gbrain.rpc("tools/call", {"name": name, "arguments": arguments})
    if response.get("error"):
        raise AssertionError(response["error"])
    return response["result"]


def tool_text(result):
    return "\n".join(block.get("text", "") for block in result.get("content", []))


def wait_for(predicate, message, timeout=50):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(2)
    raise AssertionError(message)


def live():
    tools = gbrain.rpc("tools/list")["result"]["tools"]
    assert {t["name"] for t in tools} == set(gbrain.TOOLS)
    try:
        gbrain.rpc("tools/list", authenticated=False)
        raise AssertionError("Unauthenticated access unexpectedly worked")
    except urllib.error.HTTPError as error:
        assert error.code == 401
    denied = call("put_page", {"slug": "probe-denied", "content": "must never be stored"})
    assert denied.get("isError"), denied
    assert call("get_page", {"slug": "probe-denied"}).get("isError")
    assert call("get_page", {"slug": "private-note-not-imported"}).get("isError")
    # Two temporary synthetic notes prove import, concurrent reads, link extraction,
    # edits and deletion through the actual watcher. Real notes are never touched.
    marker = uuid.uuid4().hex
    person = "people/gbrain-sync-verification-" + marker
    slug = "projects/gbrain-sync-verification-" + marker
    person_path = gbrain.VAULT / (person + ".md")
    path = gbrain.VAULT / (slug + ".md")
    original_hashes = {str(p): p.read_bytes() for p in gbrain.VAULT.rglob("*.md")}
    def body(value):
        return ("---\ntype: project\nscope: verification\nsource_date: 2026-10-03\n---\n"
                "# Temporary sync verification\nSynthetic test marker: " + value + ".\n"
                "Owner: [[" + person + "]].\n")
    try:
        person_path.parent.mkdir(parents=True, exist_ok=True)
        person_path.write_text("---\ntype: person\nscope: verification\nsource_date: 2026-10-03\n---\n"
                               "# Temporary owner\nSynthetic test person.\n")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body("amber-orbit"))
        wait_for(lambda: "amber-orbit" in tool_text(call("get_page", {"slug": slug})), "New note did not sync")
        with concurrent.futures.ThreadPoolExecutor(max_workers=9) as pool:
            responses = list(pool.map(lambda _: call("get_page", {"slug": slug}), range(9)))
        for response in responses:
            assert not response.get("isError"), response
            assert "amber-orbit" in tool_text(response)
        path.write_text(body("cobalt-orbit"))
        wait_for(lambda: "cobalt-orbit" in tool_text(call("get_page", {"slug": slug})), "Edited note did not sync")
        wait_for(lambda: person in tool_text(call("get_links", {"slug": slug})), "New wikilink did not sync")
    finally:
        path.unlink(missing_ok=True)
        person_path.unlink(missing_ok=True)
    wait_for(lambda: call("get_page", {"slug": slug}).get("isError"), "Deleted note remains active")
    for path, before in original_hashes.items():
        assert Path(path).read_bytes() == before, f"Original Markdown changed: {path}"
    print("PASS: six read tools; unauthorized and write requests denied; nine concurrent readers; "
          "automatic create/edit/link/delete sync verified; existing notes unchanged.")


if __name__ == "__main__":
    if "--live" in sys.argv:
        live()
    else:
        unittest.main()
