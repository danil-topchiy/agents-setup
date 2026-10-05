"""Verify callback boundaries without a live server or real credentials."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import callback

AGENT = "11111111-1111-4111-8111-111111111111"
ISSUE = "22222222-2222-4222-8222-222222222222"
RUN = "33333333-3333-4333-8333-333333333333"


class CallbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        keys = root / ".local/keys"
        keys.mkdir(parents=True)
        (keys / "cto.json").write_text(json.dumps({"token": "test-only", "agentId": AGENT, "companyId": "company", "projectId": "project"}))
        self.root = patch.object(callback, "ROOT", root)
        self.root.start()
        self.addCleanup(self.root.stop)
        self.issue = {"id": ISSUE, "companyId": "company", "projectId": "project", "assigneeAgentId": AGENT}

    def test_privileged_and_arbitrary_endpoints_rejected_before_network(self):
        with patch.object(callback.urllib.request, "urlopen") as http:
            for path in ("/api/companies/company/budgets", "https://example.com", "/api/agents/me?extra=1", "/api/issues/../agents"):
                with self.assertRaises(ValueError):
                    callback.request("cto", "PATCH", path, {"status": "done"}, RUN)
            http.assert_not_called()

    def test_cross_project_and_other_owner_are_rejected(self):
        for changes in ({"projectId": "elsewhere"}, {"assigneeAgentId": "another-agent"}):
            issue = {**self.issue, **changes}
            with patch.object(callback.urllib.request, "urlopen", return_value=io.BytesIO(json.dumps(issue).encode())) as http:
                with self.assertRaises(ValueError):
                    callback.request("cto", "PATCH", f"/api/issues/{ISSUE}", {"status": "done"}, RUN)
                self.assertEqual(http.call_count, 1)  # Only the read, no mutation.

    def test_mutations_require_run_and_inject_bearer_and_run_headers(self):
        with patch.object(callback.urllib.request, "urlopen", return_value=io.BytesIO(json.dumps(self.issue).encode())) as http:
            with self.assertRaises(ValueError):
                callback.request("cto", "PATCH", f"/api/issues/{ISSUE}", {"status": "done"})
            self.assertEqual(http.call_count, 1)
        responses = [io.BytesIO(json.dumps(self.issue).encode()), io.BytesIO(b'{"status":"done"}')]
        with patch.object(callback.urllib.request, "urlopen", side_effect=responses) as http:
            callback.request("cto", "PATCH", f"/api/issues/{ISSUE}", {"status": "done", "comment": "checked"}, RUN)
            req = http.call_args.args[0]
            self.assertEqual(req.get_header("Authorization"), "Bearer test-only")
            self.assertEqual(req.get_header("X-paperclip-run-id"), RUN)
            self.assertEqual(req.full_url, callback.BASE + f"/api/issues/{ISSUE}")

    def test_identity_does_not_disclose_adapter_secrets(self):
        response = {"id": AGENT, "name": "CTO", "adapterConfig": {"secret": "do-not-return"}}
        with patch.object(callback.urllib.request, "urlopen", return_value=io.BytesIO(json.dumps(response).encode())):
            result = callback.request("cto", "GET", "/api/agents/me")
        self.assertNotIn("adapterConfig", result)

    def test_company_scope_keeps_company_and_assignee_boundaries(self):
        key_path = callback.ROOT / ".local/keys/cto.json"
        key = json.loads(key_path.read_text())
        key.pop("projectId")
        key["scope"] = "company"
        key_path.write_text(json.dumps(key))
        for changes in ({"companyId": "elsewhere"}, {"assigneeAgentId": "another-agent"}):
            issue = {**self.issue, **changes}
            with patch.object(callback.urllib.request, "urlopen", return_value=io.BytesIO(json.dumps(issue).encode())) as http:
                with self.assertRaises(ValueError):
                    callback.request("cto", "PATCH", f"/api/issues/{ISSUE}", {"status": "done"}, RUN)
                self.assertEqual(http.call_count, 1)
        for project in (None, "another-project"):
            issue = {**self.issue, "projectId": project}
            responses = [io.BytesIO(json.dumps(issue).encode()), io.BytesIO(b'{"status":"done"}')]
            with patch.object(callback.urllib.request, "urlopen", side_effect=responses) as http:
                callback.request("cto", "PATCH", f"/api/issues/{ISSUE}", {"status": "done"}, RUN)
                self.assertEqual(http.call_count, 2)

    def test_blocked_records_self_owned_unblock_action(self):
        action = "Wait for the accepted CTO run, then resume implementation."
        responses = [io.BytesIO(json.dumps(self.issue).encode()), io.BytesIO(b'{"status":"blocked"}')]
        with patch.object(callback.urllib.request, "urlopen", side_effect=responses) as http:
            callback.request("cto", "PATCH", f"/api/issues/{ISSUE}", {"status": "blocked", "comment": action}, RUN)
            body = json.loads(http.call_args.args[0].data)
            self.assertEqual(body["unblockDescriptor"], {"owner": {"agentId": AGENT}, "action": action})
        with patch.object(callback.urllib.request, "urlopen", return_value=io.BytesIO(json.dumps(self.issue).encode())) as http:
            with self.assertRaises(ValueError):
                callback.request("cto", "PATCH", f"/api/issues/{ISSUE}", {"status": "blocked"}, RUN)
            self.assertEqual(http.call_count, 1)


if __name__ == "__main__":
    unittest.main()
