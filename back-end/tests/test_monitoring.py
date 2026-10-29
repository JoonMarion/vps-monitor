import io
import unittest
from unittest.mock import Mock, patch

import paramiko

from monitoring import connect_ssh, debug_vps_ssh, fetch_vps_metrics


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


if __name__ == "__main__":
    unittest.main()
