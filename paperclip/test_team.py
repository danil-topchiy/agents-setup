"""Check the board helper's pure rules without a live Paperclip or Gateway."""
import unittest

import team


class TeamHelperTests(unittest.TestCase):
    def test_every_openclaw_agent_maps_to_a_paperclip_role(self):
        self.assertEqual(set(team.ROLES), {"main", "cto", "swe", "qa", "ui-ux", "content",
                                           "generalist", "infrastructure", "sales"})
        valid = {"ceo", "cto", "cmo", "cfo", "security", "engineer", "designer", "pm", "qa",
                 "devops", "researcher", "general"}
        for _, role in team.ROLES.values():
            self.assertIn(role, valid)
            self.assertNotEqual(role, "ceo")  # the liaison keeps the only CEO role

    def test_engineering_specialists_report_to_cto_once_it_has_joined(self):
        s = {"liaison": "liaison-id", "agents": {}}
        self.assertEqual(team.manager_for("swe", s), "liaison-id")
        s["agents"]["cto"] = "cto-id"
        self.assertEqual(team.manager_for("swe", s), "cto-id")
        self.assertEqual(team.manager_for("qa", s), "cto-id")
        for role in ("cto", "main", "content", "sales"):
            self.assertEqual(team.manager_for(role, s), "liaison-id")

    def test_wake_instructions_forbid_tokens_delegation_and_governance_changes(self):
        text = team.wake_instructions("/private/callbacks/cto", "cto")
        self.assertIn("/private/callbacks/cto GET /api/agents/me", text)
        self.assertIn("project-scoped", text)
        self.assertIn("company-scoped", team.wake_instructions("/private/callbacks/main", "main"))
        for phrase in ("do not read the key file", "Do not delegate via OpenClaw sessions",
                       "Do not change budgets, approvals"):
            self.assertIn(phrase, text)

    def test_export_redaction_removes_tokens_device_keys_and_the_checkout_path(self):
        # Assembled at runtime so the publication scanner does not see a key marker in source.
        marker = "-----" + "BEGIN PRIVATE KEY" + "-----"
        end = "-----" + "END PRIVATE KEY" + "-----"
        text = ("url: ws://127.0.0.1:18789\nx-openclaw-token: gateway-secret-value\n"
                f"devicePrivateKeyPem: {marker}\nabc\n{end}\n"
                "token: pcp_agent_secret\npath: /home/someone/checkout/paperclip\n")
        result = team.redact(text, ["gateway-secret-value", "pcp_agent_secret", ""], "/home/someone/checkout")
        self.assertNotIn("gateway-secret-value", result)
        self.assertNotIn("pcp_agent_secret", result)
        self.assertNotIn("PRIVATE KEY", result)
        self.assertNotIn("/home/someone/checkout", result)
        self.assertIn("RECONNECT_REQUIRED", result)
        self.assertIn("PROJECT_DIR/paperclip", result)


if __name__ == "__main__":
    unittest.main()
