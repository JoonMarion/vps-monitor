import io
import base64
import hashlib
import unittest
from unittest.mock import Mock, patch

import paramiko

from monitoring import PinnedHostKeyPolicy, UntrustedHostKey, connect_ssh, debug_vps_ssh, fetch_vps_metrics


class SSHConnectionTests(unittest.TestCase):
    def setUp(self):
        self.server = {"id": "vps-id", "name": "Test", "ip": "8.8.8.8", "port": 2222,
                       "user": "monitor", "location": "Brasil", "password": "ssh-secret", "ssh_key": ""}

    def test_empty_key_uses_password_and_custom_port(self):
        ssh = Mock()
        connect_ssh(ssh, self.server)
        self.assertEqual(ssh.connect.call_args.kwargs["password"], "ssh-secret")
        self.assertEqual(ssh.connect.call_args.kwargs["port"], 2222)
        self.assertFalse(ssh.connect.call_args.kwargs["look_for_keys"])
        self.assertFalse(ssh.connect.call_args.kwargs["allow_agent"])

    def test_rsa_key_content_is_loaded_from_memory(self):
        key = paramiko.RSAKey.generate(2048)
        output = io.StringIO()
        key.write_private_key(output, password="key-password")
        self.server.update(ssh_key=output.getvalue(), passphrase="key-password")
        ssh = Mock()
        connect_ssh(ssh, self.server)
        self.assertIsInstance(ssh.connect.call_args.kwargs["pkey"], paramiko.RSAKey)
        self.assertNotIn("key_filename", ssh.connect.call_args.kwargs)
        self.assertNotIn("password", ssh.connect.call_args.kwargs)

    def test_ssh_failure_does_not_expose_credentials(self):
        with patch("monitoring.paramiko.SSHClient") as client:
            client.return_value.connect.side_effect = RuntimeError("secret ssh-secret")
            result = fetch_vps_metrics(self.server)
            self.assertEqual(result["status"], "offline")
            self.assertNotIn("ssh-secret", str(result))
            client.return_value.close.assert_called_once()

    def test_diagnostics_do_not_expose_raw_errors(self):
        with patch("monitoring.paramiko.SSHClient") as client:
            client.return_value.connect.side_effect = paramiko.AuthenticationException("ssh-secret")
            result = debug_vps_ssh(self.server)
            self.assertEqual(result["status"], "failed")
            self.assertNotIn("ssh-secret", str(result))
            client.return_value.close.assert_called_once()

    def test_host_key_pin_accepts_only_the_expected_identity(self):
        key = Mock()
        key.asbytes.return_value = b"verified-server-public-key"
        fingerprint = "SHA256:" + base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip("=")
        PinnedHostKeyPolicy(fingerprint).missing_host_key(Mock(), "8.8.8.8", key)
        for expected in ("", "SHA256:" + "A" * 43):
            with self.subTest(expected=expected):
                with self.assertRaises(UntrustedHostKey):
                    PinnedHostKeyPolicy(expected).missing_host_key(Mock(), "8.8.8.8", key)

    def test_production_and_explicit_pins_never_auto_accept_host_keys(self):
        for settings in ({"_require_host_fingerprint": True}, {"host_key_fingerprint": "SHA256:" + "A" * 43}):
            ssh = Mock()
            connect_ssh(ssh, {**self.server, **settings})
            self.assertIsInstance(ssh.set_missing_host_key_policy.call_args.args[0], PinnedHostKeyPolicy)

    def test_untrusted_host_does_not_reach_authentication(self):
        ssh = paramiko.SSHClient()
        self.server.update(_require_host_fingerprint=True)
        with patch.object(ssh, "connect") as connect:
            def handshake(**kwargs):
                key = Mock()
                key.asbytes.return_value = b"untrusted-key"
                ssh._policy.missing_host_key(ssh, kwargs["hostname"], key)
                self.fail("Authentication must not proceed after host identity verification fails")
            connect.side_effect = handshake
            with self.assertRaises(UntrustedHostKey):
                connect_ssh(ssh, self.server)


if __name__ == "__main__":
    unittest.main()
