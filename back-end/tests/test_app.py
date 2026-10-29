import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet
from sqlalchemy import select
from werkzeug.security import check_password_hash

from app import create_app
from database import User, VPSServer


class AccountIsolationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.directory.name) / "test.sqlite3"
        self.config = {
            "TESTING": True,
            "DATABASE_URL": "sqlite:///" + self.database_path.as_posix(),
            "SECRET_KEY": "test-session-key-with-at-least-32-characters",
            "VPS_ENCRYPTION_KEY": Fernet.generate_key().decode(),
            "SESSION_COOKIE_SECURE": False,
        }
        self.app = create_app(self.config)
        self.client = self.app.test_client()

    def tearDown(self):
        self.app.extensions["db_engine"].dispose()
        self.directory.cleanup()

    def post(self, client, path, data=None, method="POST", **kwargs):
        token = client.get("/api/auth/me").json["csrf_token"]
        return client.open(path, method=method, json=data, headers={"X-CSRF-Token": token}, **kwargs)

    def register(self, client=None, email="ana@example.com", **values):
        return self.post(client or self.client, "/api/auth/register", {
            "name": "Ana", "email": email, "password": "a secure password", **values,
        })

    def add_server(self, client=None, **values):
        return self.post(client or self.client, "/api/vps", {
            "name": "Produção", "ip": "8.8.8.8", "user": "root", "location": "Brasil",
            "password": "ssh-password-secret", **values,
        })

    def test_all_monitoring_routes_require_login(self):
        for path, method in (("/api/vps", "GET"), ("/api/vps/debug-ssh", "GET"),
                             ("/api/vps", "POST"), ("/api/vps/unknown", "DELETE")):
            with self.subTest(path=path, method=method):
                self.assertEqual(self.client.open(path, method=method).status_code, 401)

    def test_registration_session_and_password_hash(self):
        response = self.register(email="  ANA@Example.com  ")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json["user"]["email"], "ana@example.com")
        self.assertEqual(self.client.get("/api/auth/me").json["user"]["id"], response.json["user"]["id"])
        with self.app.extensions["db_session"]() as db:
            user = db.scalar(select(User))
            self.assertNotEqual(user.password_hash, "a secure password")
            self.assertTrue(check_password_hash(user.password_hash, "a secure password"))
        self.assertNotIn("password", response.get_data(as_text=True))
        cookie = self.client.get_cookie("vps_monitor_session")
        self.assertTrue(cookie.http_only)
        self.assertEqual(cookie.same_site, "Lax")

    def test_duplicate_email_is_case_insensitive(self):
        self.assertEqual(self.register().status_code, 201)
        other = self.app.test_client()
        self.assertEqual(self.register(other, "ANA@example.com").status_code, 409)
        self.assertIsNone(other.get("/api/auth/me").json["user"])

    def test_invalid_accounts_are_rejected(self):
        for values in ({"email": "not-an-email"}, {"password": "short"}, {"name": " "},
                       {"name": []}, {"password": "x" * 129}):
            with self.subTest(values=values):
                self.assertEqual(self.register(**values).status_code, 400)

    def test_login_logout_and_invalid_credentials(self):
        self.register()
        self.assertEqual(self.post(self.client, "/api/auth/logout").status_code, 200)
        self.assertEqual(self.client.get("/api/vps").status_code, 401)
        for email, password in (("ana@example.com", "wrong"), ("missing@example.com", "wrong")):
            response = self.post(self.client, "/api/auth/login", {"email": email, "password": password})
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.json["error"], "E-mail ou senha incorretos.")
        response = self.post(self.client, "/api/auth/login", {
            "email": "ANA@example.com", "password": "a secure password",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/vps").json, [])

    def test_mutations_require_csrf_and_login_rotates_token(self):
        previous = self.client.get("/api/auth/me").json["csrf_token"]
        self.assertEqual(self.client.post("/api/auth/register", json={}).status_code, 403)
        registered = self.register()
        self.assertNotEqual(previous, registered.json["csrf_token"])
        for path, method in (("/api/vps", "POST"), ("/api/vps/x", "DELETE"), ("/api/auth/logout", "POST")):
            self.assertEqual(self.client.open(path, method=method, json={}).status_code, 403)
        self.assertEqual(self.client.post("/api/vps", json={}, headers={"X-CSRF-Token": previous}).status_code, 403)

    def test_users_see_and_monitor_only_their_own_servers(self):
        owner = self.register().json["user"]
        first = self.add_server(user_id="someone-else").json
        other = self.app.test_client()
        other_user = self.register(other, "bruno@example.com").json["user"]
        second = self.add_server(other, name="Servidor Bruno", ip="1.1.1.1", user_id=owner["id"]).json
        with patch("app.fetch_vps_metrics", side_effect=lambda server: {"id": server["id"]}) as metrics:
            first_response = self.client.get("/api/vps?user_id=" + other_user["id"])
            self.assertEqual(first_response.json, [{"id": first["id"]}])
            self.assertEqual(metrics.call_args.args[0]["password"], "ssh-password-secret")
            self.assertEqual(other.get("/api/vps").json, [{"id": second["id"]}])
        with self.app.extensions["db_session"]() as db:
            self.assertEqual(db.get(VPSServer, first["id"]).user_id, owner["id"])
            self.assertEqual(db.get(VPSServer, second["id"]).user_id, other_user["id"])

    def test_delete_cannot_remove_or_reveal_another_users_server(self):
        self.register()
        server_id = self.add_server().json["id"]
        other = self.app.test_client()
        self.register(other, "bruno@example.com")
        self.assertEqual(self.post(other, "/api/vps/" + server_id, method="DELETE").status_code, 404)
        self.assertEqual(self.post(other, "/api/vps/missing", method="DELETE").status_code, 404)
        self.assertEqual(self.post(self.client, "/api/vps/" + server_id, method="DELETE").status_code, 200)
        self.assertEqual(self.client.get("/api/vps").json, [])

    def test_diagnostics_are_scoped_to_the_current_user(self):
        self.register()
        first = self.add_server().json
        other = self.app.test_client()
        self.register(other, "bruno@example.com")
        self.add_server(other, name="Bruno")
        with patch("app.debug_vps_ssh", side_effect=lambda server: {"id": server["id"]}) as debug:
            self.assertEqual(self.client.get("/api/vps/debug-ssh").json, [{"id": first["id"]}])
            self.assertEqual(debug.call_count, 1)

    def test_credentials_are_encrypted_and_omitted_from_api(self):
        self.register()
        response = self.add_server(passphrase="private-key-passphrase")
        self.assertEqual(response.status_code, 201)
        for field in ("password", "ssh_key", "passphrase", "encrypted_credentials", "user_id"):
            self.assertNotIn(field, response.json)
        with self.app.extensions["db_session"]() as db:
            server = db.get(VPSServer, response.json["id"])
            self.assertNotIn("ssh-password-secret", server.encrypted_credentials)
            self.assertEqual(server.connection_data(self.app.extensions["vps_cipher"])["password"], "ssh-password-secret")
        self.assertNotIn(b"ssh-password-secret", self.database_path.read_bytes())

    def test_accounts_servers_and_sessions_survive_app_restart(self):
        self.register()
        saved = self.add_server().json
        cookie = self.client.get_cookie("vps_monitor_session")
        self.app.extensions["db_engine"].dispose()
        restarted = create_app(self.config)
        try:
            client = restarted.test_client()
            client.set_cookie("vps_monitor_session", cookie.value)
            self.assertEqual(client.get("/api/auth/me").json["user"]["email"], "ana@example.com")
            with patch("app.fetch_vps_metrics", side_effect=lambda server: {"id": server["id"]}):
                self.assertEqual(client.get("/api/vps").json, [{"id": saved["id"]}])
        finally:
            restarted.extensions["db_engine"].dispose()

    def test_invalid_vps_data_is_rejected(self):
        self.register()
        for values in ({"name": ""}, {"ip": "example.com"}, {"ip": "127.0.0.1"},
                       {"ip": "10.0.0.1"}, {"ip": "::1"}, {"ip": "::ffff:127.0.0.1"},
                       {"port": 0}, {"port": 65536}, {"port": True}, {"password": ""},
                       {"ssh_key": "C:\\Users\\someone\\.ssh\\id_rsa"}):
            with self.subTest(values=values):
                self.assertEqual(self.add_server(**values).status_code, 400)
        self.assertEqual(self.client.get("/api/vps").json, [])

    def test_missing_null_or_array_json_is_rejected(self):
        self.register()
        token = self.client.get("/api/auth/me").json["csrf_token"]
        for body in ("null", "[]", "{broken", '"text"'):
            response = self.client.post("/api/vps", data=body, content_type="application/json", headers={"X-CSRF-Token": token})
            self.assertEqual(response.status_code, 400)

    def test_server_ids_are_unique_after_deletion(self):
        self.register()
        first = self.add_server().json["id"]
        second = self.add_server().json["id"]
        self.post(self.client, "/api/vps/" + first, method="DELETE")
        third = self.add_server().json["id"]
        self.assertEqual(len({first, second, third}), 3)

    def test_api_responses_are_not_cached(self):
        self.register()
        for path in ("/api/auth/me", "/api/vps", "/api/vps/debug-ssh"):
            self.assertEqual(self.client.get(path).headers["Cache-Control"], "no-store")

    def test_tampered_cookie_is_not_authenticated(self):
        self.register()
        cookie = self.client.get_cookie("vps_monitor_session")
        self.client.set_cookie("vps_monitor_session", cookie.value + "tampered")
        self.assertEqual(self.client.get("/api/vps").status_code, 401)

    def test_wrong_encryption_key_returns_safe_error(self):
        self.register()
        self.add_server()
        self.app.extensions["vps_cipher"] = Fernet(Fernet.generate_key())
        response = self.client.get("/api/vps")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("ssh-password-secret", response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
