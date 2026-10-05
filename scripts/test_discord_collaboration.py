"""Exercise the Discord team helper with synthetic identifiers and tokens."""
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import configure_discord_collaboration as helper


def snowflake(number):
    return str(100000000000000000 + number)


def synthetic_env(roles, project):
    env = {"OPENCLAW_WORKSPACE_DIR": str(project / "openclaw/workspace"),
           "OPENCLAW_STATE_DIR": str(project / ".local/native/openclaw"),
           "OPENCLAW_PRIVATE_DISCORD_GUILD_ID": snowflake(1),
           "OPENCLAW_PRIVATE_DISCORD_USER_ID": snowflake(2),
           "OPENCLAW_PRIVATE_DISCORD_TEAM_CHANNEL_ID": snowflake(3)}
    for index, role in enumerate(roles, start=1):
        env[helper.token_key(role)] = f"synthetic-token-{role}"
        env[helper.id_key(role, "APPLICATION_ID")] = snowflake(100 + index)
        env[helper.id_key(role, "BOT_USER_ID")] = snowflake(200 + index)
        env[helper.id_key(role, "CHANNEL_ID")] = snowflake(300 + index)
    return env


class DiscordCollaborationTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.project = Path(scratch.name).resolve()
        self.config = helper.native.starter_config(helper.native.PROJECT)
        self.template = (helper.native.PROJECT / "config/discord-team-instructions.md").read_text()
        for role in helper.ROLES:
            workspace = self.project / "openclaw/workspace" / ("" if role == "main" else f"agents/{role}")
            workspace.mkdir(parents=True, exist_ok=True)
            (workspace / "AGENTS.md").write_text(
                f"# {role} rules\n\nRole text.\n\n## Team delegation\n\n- Delegate carefully.\n")

    def test_full_team_plan_binds_every_bot_and_keeps_unrelated_settings(self):
        env = synthetic_env(list(helper.ROLES), self.project)
        config = copy.deepcopy(self.config)
        telegram = {"agentId": "main", "match": {"channel": "telegram", "accountId": "*"}}
        config["bindings"] = [telegram]
        updated, discord, bots = helper.build_plan(config, env)
        self.assertEqual(len(bots), 9)
        self.assertEqual(set(discord["accounts"]), {"default", *(role for role in helper.ROLES if role != "main")})
        self.assertEqual(updated["channels"]["discord"], {"$include": helper.INCLUDE})
        self.assertTrue(updated["plugins"]["entries"]["discord"]["enabled"])
        self.assertEqual(updated["bindings"][0], telegram)
        self.assertEqual(len([b for b in updated["bindings"] if b["match"]["channel"] == "discord"]), 9)
        cto = discord["accounts"]["cto"]
        self.assertEqual(cto["token"], {"source": "env", "provider": "default", "id": "DISCORD_CTO_BOT_TOKEN"})
        self.assertEqual(cto["allowFrom"], [env["OPENCLAW_PRIVATE_DISCORD_USER_ID"]])
        guild = cto["guilds"][env["OPENCLAW_PRIVATE_DISCORD_GUILD_ID"]]
        self.assertEqual(len(guild["channels"]), 10)
        self.assertEqual(len(guild["users"]), 10)
        self.assertFalse(guild["channels"][env[helper.id_key("cto", "CHANNEL_ID")]]["requireMention"])
        self.assertTrue(guild["channels"][env["OPENCLAW_PRIVATE_DISCORD_TEAM_CHANNEL_ID"]]["requireMention"])
        self.assertEqual(cto["mentionAliases"]["Infra"], env[helper.id_key("infrastructure", "BOT_USER_ID")])
        self.assertEqual(cto["mentionAliases"]["CoS"], env[helper.id_key("main", "BOT_USER_ID")])
        self.assertTrue(cto["botLoopProtection"]["enabled"])
        self.assertEqual(updated["tools"]["sessions"]["visibility"], "tree")
        for name in helper.DELEGATION_TOOLS:
            self.assertIn(name, updated["tools"]["alsoAllow"])
            self.assertNotIn(name, updated["tools"]["deny"])
        self.assertEqual(updated["agents"]["defaults"]["subagents"]["maxSpawnDepth"], 2)
        self.assertNotIn("synthetic-token", json.dumps(updated) + json.dumps(discord))
        self.assertEqual(config["bindings"], [telegram])
        self.assertNotIn("channels", config)
        again, _, _ = helper.build_plan(updated, env, discord)
        self.assertEqual(again, updated)

    def test_partial_team_configures_only_bots_with_tokens(self):
        env = synthetic_env(["main", "cto", "swe"], self.project)
        del env[helper.id_key("swe", "CHANNEL_ID")]
        updated, discord, bots = helper.build_plan(self.config, env)
        self.assertEqual(list(bots), ["main", "cto", "swe"])
        self.assertEqual(set(discord["accounts"]), {"default", "cto", "swe"})
        swe = discord["accounts"]["swe"]
        self.assertEqual(set(swe["mentionAliases"]), {"ChiefOfStaff", "CoS", "CTO", "SWE"})
        rooms = swe["guilds"][env["OPENCLAW_PRIVATE_DISCORD_GUILD_ID"]]["channels"]
        self.assertEqual(len(rooms), 3)
        self.assertTrue(all(room["requireMention"] for room in rooms.values()))
        self.assertEqual(len([b for b in updated["bindings"] if b["match"]["channel"] == "discord"]), 3)
        changes = helper.prepare_instructions(updated, env, bots, self.template, self.project)
        self.assertEqual([role for role, *_ in changes], ["main", "cto", "swe"])
        text = changes[1][3].decode()
        self.assertIn("for the CTO\nrole. Your handoff handle is @CTO.", text)
        self.assertIn("@ChiefOfStaff, @CTO, @SWE.", text)
        self.assertNotIn("@QA", text)
        self.assertLess(text.index("## Team delegation"), text.index(helper.MARKER))
        self.assertNotIn("${", text)

    def test_missing_main_token_or_bad_identifiers_are_rejected_without_echoing_values(self):
        with self.assertRaises(ValueError) as caught:
            helper.build_plan(self.config, synthetic_env(["cto"], self.project))
        self.assertIn("DISCORD_BOT_TOKEN", str(caught.exception))
        env = synthetic_env(["main", "cto"], self.project)
        env[helper.id_key("cto", "BOT_USER_ID")] = "not-a-snowflake"
        with self.assertRaises(ValueError) as caught:
            helper.build_plan(self.config, env)
        self.assertNotIn("not-a-snowflake", str(caught.exception))
        env = synthetic_env(["main", "cto"], self.project)
        env[helper.token_key("cto")] = env[helper.token_key("main")]
        with self.assertRaises(ValueError) as caught:
            helper.build_plan(self.config, env)
        self.assertNotIn("synthetic-token", str(caught.exception))

    def test_foreign_discord_settings_and_bindings_are_not_overwritten(self):
        env = synthetic_env(["main", "cto"], self.project)
        with self.assertRaises(ValueError):
            helper.build_plan(self.config, env, {"accounts": {"other-bot": {}}})
        with self.assertRaises(ValueError):
            helper.build_plan(self.config, env, {"accounts": {"default": {"guilds": {snowflake(999): {}}}}})
        with self.assertRaises(ValueError):
            helper.build_plan(self.config, env, {"guilds": {snowflake(1): {"channels": {snowflake(998): {}}}}})
        config = copy.deepcopy(self.config)
        config["bindings"] = [{"agentId": "someone-else", "match": {"channel": "discord", "accountId": "default"}}]
        with self.assertRaises(ValueError):
            helper.build_plan(config, env)
        config = copy.deepcopy(self.config)
        config["agents"]["entries"].pop("cto")
        with self.assertRaises(ValueError):
            helper.build_plan(config, env)

    def test_instructions_replace_only_the_discord_section(self):
        env = synthetic_env(["main", "cto"], self.project)
        updated, _, bots = helper.build_plan(self.config, env)
        path = self.project / "openclaw/workspace/agents/cto/AGENTS.md"
        path.write_text("# CTO\n\nRole text.\n\n## Discord team conversations\n\nOld section.\n\n"
                        "### Old sub\n\nMore old text.\n\n## Local notes\n\nKeep me.\n")
        first = dict((role, after) for role, _, _, after in
                     helper.prepare_instructions(updated, env, bots, self.template, self.project))["cto"]
        text = first.decode()
        self.assertNotIn("Old section", text)
        self.assertNotIn("Old sub", text)
        self.assertTrue(text.endswith("## Local notes\n\nKeep me.\n"))
        self.assertEqual(text.count(helper.MARKER), 1)
        path.write_bytes(first)
        again = dict((role, after) for role, _, _, after in
                     helper.prepare_instructions(updated, env, bots, self.template, self.project))["cto"]
        self.assertEqual(again, first)
        path.write_text(f"# CTO\n\n{helper.MARKER}\n\nA\n\n{helper.MARKER}\n\nB\n")
        with self.assertRaises(ValueError):
            helper.prepare_instructions(updated, env, bots, self.template, self.project)
        path.write_text("# CTO\n")
        with self.assertRaises(ValueError):
            helper.prepare_instructions(updated, env, bots, self.template, self.project / "elsewhere")

    def test_credential_check_requires_the_configured_bot_identity(self):
        env = synthetic_env(["main", "cto"], self.project)
        _, _, bots = helper.build_plan(self.config, env)
        identities = {"synthetic-token-main": {"bot": True, "id": env[helper.id_key("main", "BOT_USER_ID")]},
                      "synthetic-token-cto": {"bot": True, "id": snowflake(999)}}

        def fake_urlopen(request, timeout):
            token = request.get_header("Authorization").removeprefix("Bot ")
            return io.BytesIO(json.dumps(identities[token]).encode())

        with patch.object(helper.urllib.request, "urlopen", fake_urlopen):
            with self.assertRaises(ValueError) as caught:
                helper.check_credentials(env, bots)
        self.assertIn("cto", str(caught.exception))
        self.assertNotIn("synthetic-token", str(caught.exception))
        identities["synthetic-token-cto"]["id"] = env[helper.id_key("cto", "BOT_USER_ID")]
        with patch.object(helper.urllib.request, "urlopen", fake_urlopen):
            helper.check_credentials(env, bots)


if __name__ == "__main__":
    unittest.main()
