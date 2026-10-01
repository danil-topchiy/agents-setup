"""Check that privacy failures are detected without revealing their values."""
import json
from pathlib import Path
import tempfile
import unittest

from check_config_privacy import find_issues, private_values


class ConfigPrivacyTests(unittest.TestCase):
    def test_private_metadata_and_credentials_are_detected_without_echoing_them(self):
        private = {"synthetic-private-token", "synthetic-session-label", "openai:private-profile"}
        data = {"gateway": {"token": "synthetic-private-token"},
                "model": "openai/synthetic-session-label",
                "auth": {"profiles": {"openai:private-profile": {"email": "person@example.invalid"}}}}
        issues = find_issues(json.dumps(data), private)
        self.assertEqual(len(issues), 4)
        for value in (*private, "person@example.invalid"):
            self.assertNotIn(value, "\n".join(issues))

    def test_environment_references_and_private_include_are_accepted(self):
        data = {"model": "${OPENCLAW_PRIVATE_DEFAULT_MODEL}",
                "auth": {"$include": "./openclaw-auth.private.json"},
                "gateway": {"auth": {"token": {"source": "env", "provider": "default",
                                                "id": "OPENCLAW_GATEWAY_TOKEN"}}},
                "agents": {"entries": {"main": {"workspace": "${OPENCLAW_WORKSPACE_DIR}"}}}}
        self.assertEqual(find_issues(json.dumps(data), {"main", "synthetic-private-token"}), [])

    def test_private_values_include_integration_secrets_and_profile_identifiers(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / ".local").mkdir()
            (project / "config").mkdir()
            (project / ".env").write_text("OPENCLAW_PRIVATE_DEFAULT_MODEL='synthetic-session'\nDEMO_PROJECT='/public/path'\n")
            (project / ".local/openclaw.env").write_text("AGENTMAIL_API_KEY='synthetic-api-key'\n")
            hermes = project / ".local/native/hermes"
            hermes.mkdir(parents=True)
            (hermes / ".env").write_text("TELEGRAM_BOT_TOKEN='synthetic-hermes-token'\nTELEGRAM_ALLOWED_USERS='1122334455'\n")
            (hermes / "auth.json").write_text('{"provider":{"access_token":"synthetic-oauth-token"}}')
            (project / "config/openclaw-auth.private.json").write_text('{"profiles":{"openai:test":{}}}')
            self.assertEqual(private_values(project), {"synthetic-session", "synthetic-api-key", "openai:test",
                                                     "synthetic-hermes-token", "1122334455", "synthetic-oauth-token"})

    def test_new_owner_identifier_is_detected_without_a_previous_env_value(self):
        text = '{"commands":{"ownerAllowFrom":["telegram:998877665"]}}'
        issues = find_issues(text, set())
        self.assertEqual(issues, ["Owner identifiers belong in private environment references."])
        self.assertNotIn("998877665", "\n".join(issues))

    def test_unrecognized_inline_credential_is_rejected(self):
        issues = find_issues('{"channels":{"telegram":{"botToken":"synthetic-new-credential"}}}', set())
        self.assertEqual(issues, ["An inline credential belongs in a private secret reference."])
        self.assertNotIn("synthetic-new-credential", "\n".join(issues))
