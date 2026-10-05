#!/usr/bin/env python3
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import gbrain
import gbrain_sessions as sessions


class SessionPolicyTests(unittest.TestCase):
    def fixture(self):
        return {"mcp": {"servers": {"gbrain": {"url": gbrain.URL}}},
                "tools": {"alsoAllow": ["read", "group:memory", "sessions_spawn"]},
                "agents": {"entries": {**{a: {"tools": {"deny": ["runway__*"]}} for a in gbrain.TEAM},
                    "restricted-agent": {"tools": {"allow": ["read"], "deny": ["group:plugins"]}},
                    "maintenance-agent": {"tools": {"alsoAllow": ["exec"]}}}}}

    def test_history_is_agent_scoped_without_losing_native_permissions(self):
        before=self.fixture()
        copy_before=copy.deepcopy(before)
        data=sessions.configure_data(before)
        self.assertEqual(before,copy_before)
        for agent in gbrain.TEAM:
            policy=data['agents']['entries'][agent]['tools']
            own=sessions.server_id(agent)
            self.assertIn(own+'__search',policy['alsoAllow'])
            self.assertNotIn(own+'__*',policy['deny'])
            for tool in before['tools']['alsoAllow']:
                self.assertIn(tool,policy['alsoAllow'])
            for other in gbrain.TEAM:
                if other!=agent:
                    self.assertIn(sessions.server_id(other)+'__*',policy['deny'])
            self.assertEqual(data['mcp']['servers'][own]['codex']['agents'],[agent])
        self.assertEqual(data['agents']['entries']['restricted-agent']['tools']['allow'],['read'])
        self.assertEqual(data['agents']['entries']['maintenance-agent']['tools']['alsoAllow'],['exec'])
        self.assertEqual(data['tools'],before['tools'])
        self.assertEqual(sessions.configure_data(data),data)

    def test_docker_omits_native_history_servers_and_credentials(self):
        from init import docker_config
        data=sessions.configure_data(self.fixture())
        data['gateway']={}
        with patch('init.portable_config',return_value=data):
            rendered=docker_config(gbrain.PROJECT,Path('/opt/chromium/chrome'))
        self.assertNotIn('gbrain_history_',json.dumps(rendered))
        self.assertNotIn('GBRAIN_SESSION_',json.dumps(rendered))


if __name__=='__main__':
    unittest.main()
