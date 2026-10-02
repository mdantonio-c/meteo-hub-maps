import unittest
from unittest.mock import Mock, patch

from flask import Flask
from maps.auth.authz import check_ip_access
from restapi.env import Env
from restapi.exceptions import Forbidden


class TestIPAccess(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.action = Mock(return_value="accepted")
        self.guarded = check_ip_access(self.action)

    def call(self, address, allowlist, headers=None):
        with patch.object(Env, "get", return_value=allowlist) as get_env:
            with self.app.test_request_context(
                "/api/data/monitoring",
                environ_base={"REMOTE_ADDR": address},
                headers=headers,
            ):
                result = self.guarded("resource", task="monitoring")
                get_env.assert_called_once_with("MAINTENANCE_ALLOWLIST", "")
                return result

    def test_allowlisted_ips_and_cidrs_preserve_arguments(self):
        allowlist = "192.0.2.10, 198.51.100.0/24\n2001:db8::/32"
        for address in ("192.0.2.10", "198.51.100.42", "2001:db8::42"):
            with self.subTest(address=address):
                self.assertEqual(self.call(address, allowlist), "accepted")
                self.action.assert_called_with("resource", task="monitoring")

    def test_denied_requests_never_execute_action(self):
        for address, allowlist in (
            ("192.0.2.11", "192.0.2.10"),
            ("198.51.101.1", "198.51.100.0/24"),
            ("2001:db9::1", "2001:db8::/32"),
            ("192.0.2.10", ""),
            ("192.0.2.10", "192.0.2.10, invalid"),
            ("invalid", "192.0.2.0/24"),
        ):
            with self.subTest(address=address, allowlist=allowlist):
                with self.assertRaises(Forbidden):
                    self.call(address, allowlist)
        self.action.assert_not_called()

    def test_forwarded_headers_cannot_override_client_address(self):
        with self.assertRaises(Forbidden):
            self.call(
                "198.51.100.1",
                "192.0.2.10",
                headers={"X-Forwarded-For": "192.0.2.10", "X-Real-IP": "192.0.2.10"},
            )
        self.action.assert_not_called()
