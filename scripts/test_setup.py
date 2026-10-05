"""Check state preservation, credential handling and native isolation."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from native import PROJECT, gateway_port, initialize, runtime_env, service_label, starter_config
from init import docker_config, env_values, host_only_mcp_servers, prepare_env, prepare_hermes, without_host_only_mcp
from tailscale import check_native_settings, gateway_patch


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.project = Path(self.scratch.name).resolve() / "agent's demo $files"
        self.project.mkdir()
        for name in ("scripts", "hermes", "config"):
            shutil.copytree(PROJECT / name, self.project / name,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "openclaw.json", "*.private.json*"))
        shutil.copy2(PROJECT / "docker-compose.yml", self.project / "docker-compose.yml")
        (self.project / "docker").mkdir()
        target = self.project / "openclaw/workspace"
        target.mkdir(parents=True)
        (target / "AGENTS.md").write_text("Synthetic assistant working rules.\n")

    def test_credentials_and_literal_project_path_survive_repeat_setup(self):
        prepare_env(self.project)
        before = (self.project / ".env").read_bytes()
        prepare_env(self.project)
        self.assertEqual(before, (self.project / ".env").read_bytes())
        self.assertEqual(env_values(self.project / ".env")["DEMO_PROJECT"], str(self.project))
        self.assertEqual((self.project / ".env").stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.project / ".local/openclaw.env").stat().st_mode & 0o777, 0o600)

    def test_unrelated_env_is_never_overwritten(self):
        path = self.project / ".env"
        path.write_text("SOME_OTHER_APP=preserve-me\n")
        with self.assertRaises(ValueError):
            prepare_env(self.project)
        self.assertEqual(path.read_text(), "SOME_OTHER_APP=preserve-me\n")

    def test_published_uid_names_survive_native_initialization(self):
        initialize(self.project)
        path = self.project / ".env"
        path.write_text(path.read_text().replace("HOST_UID=", "WORKSHOP_UID=")
                        .replace("HOST_GID=", "WORKSHOP_GID="))
        preserved = [path, self.project / "config/openclaw.json",
                     self.project / ".local/native/hermes/config.yaml",
                     self.project / ".local/native/hermes/memories/MEMORY.md"]
        before = {p: p.read_bytes() for p in preserved}
        initialize(self.project)
        self.assertEqual(before, {p: p.read_bytes() for p in preserved})
        env = runtime_env("openclaw", self.project)
        self.assertTrue(env["OPENCLAW_GATEWAY_TOKEN"])
        for key in ("HOST_UID", "HOST_GID", "WORKSHOP_UID", "WORKSHOP_GID"):
            self.assertNotIn(key, env)

    @unittest.skipUnless(shutil.which("docker"), "Docker CLI is not installed")
    def test_compose_preserves_published_and_current_uid_values(self):
        prepare_env(self.project)
        path = self.project / ".env"
        base = "\n".join(line for line in path.read_text().splitlines()
                         if not line.startswith(("HOST_UID=", "HOST_GID="))) + "\n"
        legacy = "WORKSHOP_UID='1234'\nWORKSHOP_GID='2345'\n"
        current = "HOST_UID='3456'\nHOST_GID='4567'\n"
        cases = [(legacy, "1234", "2345"), (current, "3456", "4567"),
                 (legacy + current, "3456", "4567"),
                 (legacy + "HOST_UID=''\nHOST_GID=''\n", "1234", "2345")]
        for settings, uid, gid in cases:
            with self.subTest(settings=settings):
                path.write_text(base + settings)
                before = path.read_bytes()
                prepare_env(self.project)
                self.assertEqual(path.read_bytes(), before)
                result = subprocess.run(["docker", "compose", "config", "--format", "json"],
                                        cwd=self.project, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                services = json.loads(result.stdout)["services"]
                self.assertEqual(services["openclaw"]["user"], f"{uid}:{gid}")
                self.assertEqual(services["openclaw"]["environment"]["HOST_UID"], uid)
                self.assertEqual(services["openclaw"]["environment"]["HOST_GID"], gid)
                self.assertEqual(services["hermes"]["environment"]["HERMES_UID"], uid)
                self.assertEqual(services["hermes"]["environment"]["HERMES_GID"], gid)

    @unittest.skipUnless(shutil.which("docker"), "Docker CLI is not installed")
    def test_compose_keeps_special_characters_in_the_project_mount(self):
        prepare_env(self.project)
        result = subprocess.run(["docker", "compose", "config", "--format", "json"],
                                cwd=self.project, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        mounts = data["services"]["openclaw"]["volumes"]
        # Compose's config serializer escapes literal dollars for re-reading.
        source = next(v["source"] for v in mounts if v["type"] == "bind")
        self.assertEqual(source.replace("$$", "$"), str(self.project))

    def test_moved_checkout_requires_path_review_without_rotating_secrets(self):
        prepare_env(self.project)
        path = self.project / ".env"
        before = path.read_text().replace(str(self.project).replace("'", "\\'"), "/old/location")
        path.write_text(before)
        with self.assertRaises(ValueError):
            prepare_env(self.project)
        self.assertEqual(path.read_text(), before)

    def test_repeat_native_initialization_preserves_model_settings_and_memory(self):
        initialize(self.project)
        oc = self.project / "config/openclaw.json"
        data = json.loads(oc.read_text())
        data["agents"]["defaults"]["model"] = {"primary": "synthetic/test-model"}
        oc.write_text(json.dumps(data))
        memory = self.project / ".local/native/hermes/memories/MEMORY.md"
        memory.write_text("A learned test preference.\n")
        initialize(self.project)
        self.assertEqual(json.loads(oc.read_text())["agents"]["defaults"]["model"]["primary"], "synthetic/test-model")
        self.assertEqual(memory.read_text(), "A learned test preference.\n")
        self.assertEqual(data["agents"]["entries"]["main"]["workspace"], "${OPENCLAW_WORKSPACE_DIR}")

    def test_native_launcher_overrides_inherited_host_selectors(self):
        initialize(self.project)
        with patch.dict(os.environ, {"OPENCLAW_STATE_DIR": "/wrong/state", "OPENCLAW_CONFIG_PATH": "/wrong/config", "OPENCLAW_LOG_FILE": "/wrong/log", "OPENCLAW_PROFILE": "personal", "HERMES_HOME": "/wrong/hermes"}):
            oc = runtime_env("openclaw", self.project)
            hermes = runtime_env("hermes", self.project)
        self.assertEqual(oc["OPENCLAW_STATE_DIR"], str(self.project / ".local/native/openclaw"))
        self.assertEqual(oc["OPENCLAW_CONFIG_PATH"], str(self.project / "config/openclaw.json"))
        self.assertEqual(oc["OPENCLAW_WORKSPACE_DIR"], str(self.project / "openclaw/workspace"))
        self.assertEqual(oc["OPENCLAW_LOG_FILE"], str(self.project / ".local/logs/openclaw.log"))
        self.assertEqual(json.loads((self.project / "config/openclaw.json").read_text())["logging"]["file"], "${OPENCLAW_LOG_FILE}")
        self.assertNotIn("OPENCLAW_PROFILE", oc)
        self.assertEqual(hermes["HERMES_HOME"], str(self.project / ".local/native/hermes"))
        self.assertEqual(hermes["HERMES_DASHBOARD_BASIC_AUTH_USERNAME"], "learner")
        self.assertTrue(hermes["HERMES_DASHBOARD_BASIC_AUTH_PASSWORD"])

    def test_native_config_references_credentials_without_storing_them(self):
        initialize(self.project)
        text = (self.project / "config/openclaw.json").read_text()
        data = json.loads(text)
        values = env_values(self.project / ".env")
        self.assertEqual(data["gateway"]["auth"]["token"],
                         {"source": "env", "provider": "default", "id": "OPENCLAW_GATEWAY_TOKEN"})
        for key in ("OPENCLAW_GATEWAY_TOKEN", "HERMES_DASHBOARD_PASSWORD", "HERMES_DASHBOARD_SECRET"):
            self.assertNotIn(values[key], text)

    def test_public_starter_initializes_with_no_private_account_include(self):
        config = self.project / "config/openclaw.json"
        config.write_text(json.dumps(starter_config(self.project)))
        before = config.read_bytes()
        initialize(self.project)
        self.assertEqual(before, config.read_bytes())
        data = json.loads(config.read_text())
        self.assertNotIn("auth", data)
        self.assertNotIn("model", data["agents"]["defaults"])
        self.assertNotIn("channels", data)
        self.assertNotIn("commands", data)
        self.assertFalse(data["gateway"]["auth"]["allowTailscale"])
        self.assertTrue(runtime_env("openclaw", self.project)["OPENCLAW_GATEWAY_TOKEN"])

    def test_starter_config_keeps_the_team_and_drops_instance_settings(self):
        tracked = json.loads((PROJECT / "config/openclaw.json").read_text())
        tracked["auth"] = {"$include": "./openclaw-auth.private.json"}
        tracked["approvals"] = {"$include": "./openclaw-maintainer.private.json"}
        tracked["cron"] = {"enabled": True}
        tracked["channels"] = {"discord": {"$include": "./openclaw-discord.private.json"}}
        tracked["bindings"] = [{"agentId": "cto", "match": {"channel": "discord", "accountId": "cto"}}]
        tracked["plugins"]["entries"]["discord"] = {"enabled": True}
        tracked["agents"]["defaults"]["model"] = "openai/${OPENCLAW_PRIVATE_DEFAULT_MODEL}"
        tracked["gateway"]["trustedProxies"] = ["127.0.0.1"]
        config = self.project / "config/openclaw.json"
        config.write_text(json.dumps(tracked))
        data = starter_config(self.project)
        self.assertEqual(set(data["agents"]["entries"]), set(tracked["agents"]["entries"]))
        self.assertEqual(data["agents"]["entries"]["cto"]["workspace"], "${OPENCLAW_WORKSPACE_DIR}/agents/cto")
        for key in ("auth", "channels", "bindings", "approvals"):
            self.assertNotIn(key, data)
        self.assertFalse(data["cron"]["enabled"])
        self.assertNotIn("discord", data["plugins"]["entries"])
        self.assertNotIn("model", data["agents"]["defaults"])
        self.assertNotIn("trustedProxies", data["gateway"])
        self.assertIn("sessions_spawn", data["tools"]["alsoAllow"])
        self.assertEqual(data["gateway"]["auth"]["token"]["id"], "OPENCLAW_GATEWAY_TOKEN")
        tracked["agents"]["entries"]["cto"]["workspace"] = "/home/someone/private/path"
        config.write_text(json.dumps(tracked))
        with self.assertRaises(ValueError):
            starter_config(self.project)

    def test_docker_config_registers_the_team_with_container_paths(self):
        (self.project / "config/openclaw.json").write_text(json.dumps(starter_config(PROJECT)))
        tracked = json.loads((PROJECT / "config/openclaw.json").read_text())
        data = docker_config(self.project, Path("/opt/chromium/chrome"))
        self.assertEqual(set(data["agents"]["entries"]), set(tracked["agents"]["entries"]))
        self.assertEqual(data["agents"]["entries"]["main"]["workspace"], "/project/openclaw/workspace")
        self.assertEqual(data["agents"]["entries"]["cto"]["workspace"], "/project/openclaw/workspace/agents/cto")
        self.assertNotIn("agentDir", data["agents"]["entries"]["cto"])
        self.assertNotIn("${", json.dumps(data))
        self.assertNotIn("logging", data)
        self.assertEqual(data["gateway"]["bind"], "lan")
        self.assertEqual(data["browser"]["executablePath"], "/opt/chromium/chrome")
        self.assertIn("sessions_spawn", data["tools"]["alsoAllow"])
        initialize(self.project)
        env = runtime_env("openclaw", self.project)
        binary = shutil.which("openclaw", path=env["PATH"])
        if binary:
            candidate = self.project / "docker-candidate.json"
            candidate.write_text(json.dumps(data))
            result = subprocess.run([binary, "config", "validate"], cwd=self.project, text=True,
                                    capture_output=True, env=dict(env, OPENCLAW_CONFIG_PATH=str(candidate)))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_native_environment_keeps_credentials_and_tool_overrides_scoped(self):
        initialize(self.project)
        keys = {"OPENAI_API_KEY": "unrelated-provider-key", "TELEGRAM_BOT_TOKEN": "unrelated-bot",
                "HERMES_YOLO_MODE": "1", "HERMES_TUI_TOOLSETS": "all",
                "HERMES_DASHBOARD_PUBLIC_URL": "https://unrelated.invalid",
                "OPENCLAW_CONFIG_PATH": "/unrelated/config"}
        (self.project / ".local/native/hermes/.env").write_text(
            "OPENAI_API_KEY='synthetic-hermes-key'\nTELEGRAM_BOT_TOKEN='synthetic-hermes-bot'\n")
        with patch.dict(os.environ, keys):
            oc = runtime_env("openclaw", self.project)
            hermes = runtime_env("hermes", self.project)
        self.assertNotIn("OPENAI_API_KEY", oc)
        self.assertNotIn("TELEGRAM_BOT_TOKEN", oc)
        self.assertNotIn("HERMES_YOLO_MODE", hermes)
        self.assertNotIn("HERMES_TUI_TOOLSETS", hermes)
        self.assertNotIn("HERMES_DASHBOARD_PUBLIC_URL", hermes)
        self.assertNotIn("OPENCLAW_CONFIG_PATH", hermes)
        self.assertEqual(hermes["OPENAI_API_KEY"], "synthetic-hermes-key")
        self.assertEqual(hermes["TELEGRAM_BOT_TOKEN"], "synthetic-hermes-bot")

    def test_both_native_apps_select_the_pinned_node(self):
        initialize(self.project)
        (self.project / ".nvmrc").write_text("26.10.0\n")
        nvm = self.project / "fake-nvm"
        node_bin = nvm / "versions/node/v26.10.0/bin"
        node_bin.mkdir(parents=True)
        (node_bin / "node").touch()
        with patch.dict(os.environ, {"NVM_DIR": str(nvm), "PATH": "/unrelated/bin"}):
            for service in ("openclaw", "hermes"):
                paths = runtime_env(service, self.project)["PATH"].split(os.pathsep)
                self.assertLess(paths.index(str(node_bin)), paths.index("/unrelated/bin"))

    def test_migrated_native_state_and_tokens_come_from_this_checkout(self):
        initialize(self.project)
        state = Path(self.scratch.name).resolve() / "existing-agent-state"
        state.mkdir(mode=0o750)
        marker = state / "preserved-account-state"
        marker.write_text("Synthetic existing account state.\n")
        env_path = self.project / ".env"
        with env_path.open("a") as out:
            out.write(f"OPENCLAW_STATE_DIR='{state}'\n")
            out.write(f"OPENCLAW_HOME='{state.parent}'\n")
            out.write("TELEGRAM_BOT_TOKEN='synthetic-existing-telegram-token'\n")
        with patch.dict(os.environ, {"OPENCLAW_STATE_DIR": "/wrong/state", "TELEGRAM_BOT_TOKEN": "wrong-token"}):
            env = runtime_env("openclaw", self.project)
        self.assertEqual(env["OPENCLAW_STATE_DIR"], str(state))
        self.assertEqual(env["OPENCLAW_AGENT_DIR"], str(state / "agents/main/agent"))
        self.assertEqual(env["TELEGRAM_BOT_TOKEN"], "synthetic-existing-telegram-token")
        self.assertNotIn("HERMES_DASHBOARD_PASSWORD", env)
        initialize(self.project)
        self.assertEqual(marker.read_text(), "Synthetic existing account state.\n")
        self.assertEqual(state.stat().st_mode & 0o777, 0o750)

    def test_native_initialization_refuses_to_replace_existing_account_state(self):
        prepare_env(self.project)
        state = self.project / ".local/native/openclaw"
        state.mkdir(parents=True)
        (state / "agents").mkdir()
        marker = state / "agents/existing-account"
        marker.write_text("Preserve this account.\n")
        with self.assertRaises(ValueError):
            initialize(self.project)
        self.assertEqual(marker.read_text(), "Preserve this account.\n")
        self.assertFalse((self.project / "config/openclaw.json").exists())

    def test_hermes_bootstrap_refuses_existing_provider_credentials(self):
        state = self.project / "private-hermes"
        state.mkdir()
        (state / "auth.json").write_text('{"synthetic": true}')
        with self.assertRaises(ValueError):
            prepare_hermes(state, self.project / "hermes", self.project / "no-defaults")
        self.assertFalse((state / "config.yaml").exists())

    def test_tailscale_keeps_authentication_and_precise_native_proxy_addresses(self):
        gateway = {"auth": {"mode": "token"}, "controlUi": {"allowedOrigins": ["http://127.0.0.1:18789"]}}
        native = gateway_patch(gateway, "host.example.ts.net", ["127.0.0.1", "::1"], "native")["gateway"]
        docker = gateway_patch(gateway, "host.example.ts.net", ["172.18.0.1"], "docker")["gateway"]
        self.assertEqual(native["bind"], "loopback")
        self.assertEqual(native["trustedProxies"], ["127.0.0.1", "::1"])
        self.assertFalse(native["auth"]["allowTailscale"])
        self.assertEqual(docker["bind"], "lan")
        self.assertIn("http://127.0.0.1:18789", native["controlUi"]["allowedOrigins"])
        self.assertIn("https://host.example.ts.net:8443", native["controlUi"]["allowedOrigins"])

    def test_tailscale_refuses_a_device_authentication_bypass(self):
        with self.assertRaises(ValueError):
            gateway_patch({"controlUi": {"dangerouslyDisableDeviceAuth": True}}, "host.example.ts.net", ["127.0.0.1"], "native")

    def test_native_serve_refuses_settings_for_an_old_hostname(self):
        host = "host.example.ts.net"
        gateway = gateway_patch({}, host, ["127.0.0.1", "::1"], "native")["gateway"]
        dashboard = {"public_url": f"https://{host}:8444", "trusted_proxies": ["127.0.0.1", "::1"]}
        check_native_settings(gateway, dashboard, host)
        with self.assertRaises(ValueError):
            check_native_settings(gateway, dashboard, "renamed.example.ts.net")
        with self.assertRaises(ValueError):
            check_native_settings(gateway, {}, host)

    def test_gateway_port_and_service_names_come_from_this_checkout(self):
        initialize(self.project)
        self.assertEqual(gateway_port(self.project), 18789)
        self.assertEqual(runtime_env("openclaw", self.project)["OPENCLAW_GATEWAY_PORT"], "18789")
        project_name = env_values(self.project / ".env")["COMPOSE_PROJECT_NAME"]
        self.assertEqual(service_label("gbrain", self.project), f"dev.{project_name}.gbrain")
        self.assertNotEqual(service_label("gbrain", self.project), service_label("paperclip", self.project))
        with (self.project / ".env").open("a") as out:
            out.write("OPENCLAW_GATEWAY_PORT='18799'\n")
        self.assertEqual(gateway_port(self.project), 18799)
        self.assertEqual(runtime_env("openclaw", self.project)["OPENCLAW_GATEWAY_PORT"], "18799")
        with (self.project / ".env").open("a") as out:
            out.write("OPENCLAW_GATEWAY_PORT='80'\n")
        with self.assertRaises(ValueError):
            gateway_port(self.project)

    def test_native_launcher_appends_local_bin_after_the_pinned_node(self):
        initialize(self.project)
        with patch.dict(os.environ, {"PATH": "/unrelated/bin"}):
            paths = runtime_env("openclaw", self.project)["PATH"].split(os.pathsep)
        self.assertEqual(paths[-1], str(Path.home() / ".local/bin"))
        self.assertIn("/unrelated/bin", paths)

    def test_docker_config_drops_host_only_mcp_servers_and_their_tool_entries(self):
        data = starter_config(PROJECT)
        data["mcp"] = {"servers": {
            "gbrain": {"url": "http://127.0.0.1:3131/mcp", "headers": {"Authorization": "Bearer ${GBRAIN_READER_TOKEN}"}},
            "gbrain_history_qa": {"url": "http://127.0.0.1:3131/mcp"},
            "local_tool": {"command": "python3", "args": ["tool.py"]},
            "hosted": {"url": "https://mcp.example.com/mcp", "auth": "oauth"}}}
        data["tools"]["alsoAllow"] += ["gbrain__search", "hosted__search"]
        data["agents"]["entries"]["qa"]["tools"] = {"deny": ["gbrain_history_main__*", "local_tool__*"],
                                                    "alsoAllow": ["read", "gbrain_history_qa__search"]}
        self.assertEqual(sorted(host_only_mcp_servers(data)), ["gbrain", "gbrain_history_qa", "local_tool"])
        rendered = without_host_only_mcp(json.loads(json.dumps(data)))
        self.assertEqual(list(rendered["mcp"]["servers"]), ["hosted"])
        self.assertNotIn("gbrain__search", rendered["tools"]["alsoAllow"])
        self.assertIn("hosted__search", rendered["tools"]["alsoAllow"])
        self.assertEqual(rendered["agents"]["entries"]["qa"]["tools"], {"deny": [], "alsoAllow": ["read"]})
        (self.project / "config/openclaw.json").write_text(json.dumps(data))
        docker = docker_config(self.project, Path("/opt/chromium/chrome"))
        self.assertNotIn("GBRAIN_READER_TOKEN", json.dumps(docker))
        self.assertFalse(docker["cron"]["enabled"])
        for entry in docker["agents"]["entries"].values():
            self.assertEqual(entry["memory"]["search"]["extraPaths"], ["/project/openclaw/workspace/knowledge"])


if __name__ == "__main__":
    unittest.main()
