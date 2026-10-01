"""Exercise publication boundaries with synthetic Git repositories."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from check_publication import inspect_text, history_findings
from export_public import export


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.project = Path(self.scratch.name) / "source"
        self.project.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Template Author")
        self.git("config", "user.email", "template@example.invalid")

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.project), *args], stderr=subprocess.DEVNULL)

    def test_removed_private_text_is_detected_in_history(self):
        path = self.project / "notes.md"
        path.write_text("A synthetic-private-account value.\n")
        self.git("add", "notes.md")
        self.git("commit", "-qm", "Initial fixture")
        path.write_text("Generic instructions.\n")
        self.git("add", "notes.md")
        self.git("commit", "-qm", "Generic fixture")
        findings = history_findings(self.project, {"synthetic-private-account"})
        self.assertTrue(any("notes.md" in location for location, _ in findings))
        self.assertNotIn("synthetic-private-account", repr(findings))

    def test_export_uses_fresh_config_and_excludes_ignored_state(self):
        (self.project / "config").mkdir()
        policy = {"gateway": {"auth": {"mode": "token"}}, "agents": {"defaults": {}}}
        (self.project / "config/openclaw-policy.patch.json").write_text(json.dumps(policy))
        active = self.project / "config/openclaw.json"
        active.write_text('{"auth":{"$include":"./absent.private.json"}}')
        (self.project / ".gitignore").write_text(".env\n.local/\n")
        (self.project / ".env").write_text("OPENAI_API_KEY='synthetic-private-provider-key'\n")
        (self.project / ".local").mkdir()
        (self.project / ".local/state").write_text("Private test state.")
        self.git("add", ".gitignore", "config")
        before = active.read_bytes()
        destination = Path(self.scratch.name) / "public"
        export(destination, self.project)
        data = json.loads((destination / "config/openclaw.json").read_text())
        self.assertNotIn("auth", data)
        self.assertEqual(data["gateway"]["auth"]["token"]["source"], "env")
        self.assertFalse((destination / ".git").exists())
        self.assertFalse((destination / ".env").exists())
        self.assertFalse((destination / ".local").exists())
        self.assertEqual(active.read_bytes(), before)
        with self.assertRaises(ValueError):
            export(destination, self.project)

    def test_private_paths_and_new_credentials_fail_without_echoing_values(self):
        self.assertIn("private runtime file", inspect_text(".local/state.json", "{}", set()))
        value = "ghp_" + "x" * 36
        issues = inspect_text("notes.md", value, set())
        self.assertIn("credential-shaped value", issues)
        self.assertNotIn(value, repr(issues))


if __name__ == "__main__":
    unittest.main()
