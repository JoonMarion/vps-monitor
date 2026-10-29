import contextlib
import http.client
import io
import ssl
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlencode, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import freemyip

DOMAIN = "vps-monitor.freemyip.com"
IP = "89.117.75.166"
SECRET = "private-test-token&with=special+characters"


def update_url(**extra):
    return "https://freemyip.com/update?" + urlencode({"token": SECRET, "domain": DOMAIN, **extra})


class FreeMyIPTests(unittest.TestCase):
    def test_token_is_decoded_without_returning_other_actions(self):
        self.assertEqual(freemyip.extract_token(update_url(delete="yes", txt="unsafe"), DOMAIN), SECRET)

    def test_wrong_origin_domain_and_ambiguous_tokens_are_rejected(self):
        urls = (
            update_url().replace("https://", "http://"),
            update_url().replace("freemyip.com/update", "attacker.example/update"),
            update_url().replace("freemyip.com/update", "freemyip.com.evil.example/update"),
            update_url().replace("/update?", "/other?"),
            update_url(domain="meu-ponto.freemyip.com"),
            update_url(token=""),
            update_url() + "&token=another-secret",
            update_url() + "#fragment",
            update_url() + "&broken-query-field",
        )
        for url in urls:
            with self.subTest(url=url.split("?", 1)[0]):
                with self.assertRaises(freemyip.UpdateError) as caught:
                    freemyip.extract_token(url, DOMAIN)
                self.assertNotIn(SECRET, str(caught.exception))

    def test_only_safe_update_parameters_are_sent_over_verified_https(self):
        with patch("freemyip.http.client.HTTPSConnection") as factory:
            connection = factory.return_value
            connection.getresponse.return_value = Mock(status=200, read=Mock(return_value=b"OK\n"))
            token = freemyip.extract_token(update_url(delete="yes", txt="x", myip="1.1.1.1"), DOMAIN)
            freemyip.update_dns(DOMAIN, IP, token)
            self.assertEqual(factory.call_args.args[0], "freemyip.com")
            context = factory.call_args.kwargs["context"]
            self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
            self.assertTrue(context.check_hostname)
            method, target = connection.request.call_args.args
            self.assertEqual(method, "GET")
            self.assertEqual(urlsplit(target).path, "/update")
            self.assertEqual(parse_qs(urlsplit(target).query), {"token": [SECRET], "domain": [DOMAIN], "myip": [IP]})
            connection.close.assert_called_once()

    def test_redirects_and_error_bodies_do_not_leak_secrets(self):
        for status, body in ((302, b"https://attacker.example"), (200, SECRET.encode()), (403, b"ERROR")):
            with self.subTest(status=status), patch("freemyip.http.client.HTTPSConnection") as factory:
                connection = factory.return_value
                connection.getresponse.return_value = Mock(status=status, read=Mock(return_value=body))
                with self.assertRaises(freemyip.UpdateError) as caught:
                    freemyip.update_dns(DOMAIN, IP, SECRET)
                self.assertNotIn(SECRET, str(caught.exception))
                connection.request.assert_called_once()
                connection.close.assert_called_once()

    def test_network_errors_are_sanitized(self):
        with patch("freemyip.http.client.HTTPSConnection") as factory:
            factory.return_value.request.side_effect = http.client.HTTPException(SECRET)
            with self.assertRaises(freemyip.UpdateError) as caught:
                freemyip.update_dns(DOMAIN, IP, SECRET)
            self.assertNotIn(SECRET, str(caught.exception))
            factory.return_value.close.assert_called_once()

    def test_noninteractive_input_is_rejected_before_reading_credentials(self):
        with patch("freemyip.sys.stdin.isatty", return_value=False), patch("freemyip.getpass.getpass") as prompt, \
                patch("freemyip.update_dns") as update, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(freemyip.main(["--domain", DOMAIN, "--ip", IP]), 1)
            prompt.assert_not_called()
            update.assert_not_called()

    def test_cli_uses_hidden_prompt_and_prints_only_public_result(self):
        output = io.StringIO()
        with patch("freemyip.sys.stdin.isatty", return_value=True), \
                patch("freemyip.getpass.getpass", return_value=update_url()) as prompt, \
                patch("freemyip.update_dns") as update, contextlib.redirect_stdout(output):
            self.assertEqual(freemyip.main(["--domain", DOMAIN, "--ip", IP]), 0)
            prompt.assert_called_once()
            update.assert_called_once_with(DOMAIN, IP, SECRET)
        self.assertIn(DOMAIN, output.getvalue())
        self.assertIn(IP, output.getvalue())
        self.assertNotIn(SECRET, output.getvalue())

    def test_invalid_target_never_triggers_the_prompt_or_an_update(self):
        for domain, ip in ((DOMAIN, "127.0.0.1"), ("example.com", IP), (DOMAIN, "::1")):
            with self.subTest(domain=domain, ip=ip), patch("freemyip.getpass.getpass") as prompt, \
                    patch("freemyip.update_dns") as update, contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(freemyip.main(["--domain", domain, "--ip", ip]), 1)
                prompt.assert_not_called()
                update.assert_not_called()


if __name__ == "__main__":
    unittest.main()
