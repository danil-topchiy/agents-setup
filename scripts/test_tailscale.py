import unittest

from tailscale import check_paperclip, check_routes, selected_services, socket_peers


class TailscaleTests(unittest.TestCase):
    def test_peer_addresses_filter_port_state_and_decode_both_families(self):
        text = """  sl  local_address rem_address st
0: 00000000:4965 010041AC:D001 01
1: 00000000:239F 020041AC:D002 01
2: 00000000:4965 030041AC:D003 06
3: 0000000000000000FFFF0000010041AC:4965 0000000000000000FFFF0000010041AC:D004 01
4: 00000000000000000000000001000000:4965 00000000000000000000000001000000:D005 01
"""
        self.assertEqual(socket_peers(text, 18789), {
            ("172.65.0.1", 53249), ("172.65.0.1", 53252), ("::1", 53253),
        })

    def test_existing_exact_routes_and_unrelated_ports_are_kept(self):
        config = {
            "TCP": {"8443": {"HTTPS": True}, "443": {"HTTPS": True}},
            "Web": {
                "demo.example.ts.net:8443": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:18789"}}},
                "demo.example.ts.net:443": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:3000"}}},
            },
        }
        check_routes(config, "demo.example.ts.net")
        config["Web"]["demo.example.ts.net:8443"]["Handlers"]["/other"] = {"Proxy": "http://127.0.0.1:4000"}
        with self.assertRaises(ValueError):
            check_routes(config, "demo.example.ts.net")

    def test_funnel_and_foreground_ownership_are_refused(self):
        with self.assertRaises(ValueError):
            check_routes({"AllowFunnel": {"demo.example.ts.net:8444": True}}, "demo.example.ts.net")
        with self.assertRaises(ValueError):
            check_routes({"Foreground": {"other": {"TCP": {"8443": {"HTTPS": True}}}}}, "demo.example.ts.net")

    def test_paperclip_is_served_only_in_authenticated_mode_with_a_known_hostname(self):
        health = {"status": "ok", "deploymentMode": "authenticated"}
        config = {"server": {"bind": "loopback", "allowedHostnames": ["demo.example.ts.net"]}}
        check_paperclip(health, config, "Demo.Example.ts.net")
        with self.assertRaises(ValueError):
            check_paperclip({**health, "deploymentMode": "local_trusted"}, config, "demo.example.ts.net")
        with self.assertRaises(ValueError):
            check_paperclip(health, {"server": {"allowedHostnames": []}}, "demo.example.ts.net")
        with self.assertRaises(ValueError):
            check_paperclip(health, {"server": {"bind": "lan", "allowedHostnames": ["demo.example.ts.net"]}}, "demo.example.ts.net")
        with self.assertRaises(ValueError):
            check_paperclip(None, config, "demo.example.ts.net")

    def test_paperclip_route_is_optional_and_uses_its_own_https_port(self):
        self.assertEqual([s[0] for s in selected_services("docker")], ["openclaw", "hermes"])
        services = selected_services("native", with_paperclip=True)
        self.assertEqual(services[-1][0], "paperclip")
        self.assertEqual(services[-1][2], 8445)
        self.assertEqual(len({https for _, _, https in services}), 3)
        config = {"TCP": {"8445": {"HTTPS": True}},
                  "Web": {"demo.example.ts.net:8445": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:4100"}}}}}
        with self.assertRaises(ValueError):
            check_routes(config, "demo.example.ts.net", services)
        check_routes(config, "demo.example.ts.net")


if __name__ == "__main__":
    unittest.main()
