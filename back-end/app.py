import datetime
import ipaddress
import json
import os
import re
import secrets
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv
from flask import Flask, current_app, g, jsonify, send_from_directory
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import BadRequest, HTTPException
from werkzeug.security import generate_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix

from auth import init_auth, json_object, login_required, text_field
from database import Base, User, VPSServer, create_database
from monitoring import debug_vps_ssh, fetch_vps_metrics

BACKEND_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BACKEND_DIR.parent / "front-end" / "dist"


def owned_servers():
    # Filter ownership before decrypting credentials or opening SSH connections.
    with current_app.extensions["db_session"]() as db:
        servers = db.scalars(
            select(VPSServer).where(VPSServer.user_id == g.user.id)
            .order_by(VPSServer.created_at, VPSServer.id)
        ).all()
    return [
        {**server.connection_data(current_app.extensions["vps_cipher"]),
         "_require_host_fingerprint": current_app.config["APP_ENV"] == "production"}
        for server in servers
    ]


def create_app(test_config=None):
    load_dotenv(BACKEND_DIR / ".env")
    app = Flask(__name__, static_folder=None)
    app.config.from_mapping(
        APP_ENV=os.getenv("APP_ENV", "development"),
        DEBUG=os.getenv("FLASK_DEBUG", "false").lower() == "true",
        BEHIND_PROXY=os.getenv("BEHIND_PROXY", "false").lower() == "true",
        TRUSTED_HOSTS=[host.strip() for host in os.getenv("TRUSTED_HOSTS", "").split(",") if host.strip()] or None,
        AUTO_CREATE_TABLES=None if "AUTO_CREATE_TABLES" not in os.environ else os.environ["AUTO_CREATE_TABLES"].lower() == "true",
        MAX_VPS_PER_USER=int(os.getenv("MAX_VPS_PER_USER", "10")),
        SSH_ALLOWED_PORTS=os.getenv("SSH_ALLOWED_PORTS", ""),
        DATABASE_URL=os.getenv("DATABASE_URL"),
        SECRET_KEY=os.getenv("SECRET_KEY"),
        VPS_ENCRYPTION_KEY=os.getenv("VPS_ENCRYPTION_KEY"),
        SESSION_COOKIE_NAME="vps_monitor_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true",
        PERMANENT_SESSION_LIFETIME=datetime.timedelta(days=7),
        SESSION_REFRESH_EACH_REQUEST=False,
        MAX_CONTENT_LENGTH=64 * 1024,
    )
    if test_config:
        app.config.update(test_config)
    if app.config["APP_ENV"] not in {"development", "testing", "production"}:
        raise RuntimeError("APP_ENV deve ser development, testing ou production.")
    production = app.config["APP_ENV"] == "production"
    if production:
        if app.config["DEBUG"]:
            raise RuntimeError("FLASK_DEBUG deve ser false em produção.")
        if not app.config["SESSION_COOKIE_SECURE"]:
            raise RuntimeError("SESSION_COOKIE_SECURE deve ser true em produção; use HTTPS.")
        if not app.config["TRUSTED_HOSTS"]:
            raise RuntimeError("Configure TRUSTED_HOSTS com o domínio público em produção.")
        app.config["SESSION_COOKIE_NAME"] = "__Host-vps_monitor_session"
    if app.config["AUTO_CREATE_TABLES"] is None:
        app.config["AUTO_CREATE_TABLES"] = not production
    if not 1 <= app.config["MAX_VPS_PER_USER"] <= 100:
        raise RuntimeError("MAX_VPS_PER_USER deve estar entre 1 e 100.")
    try:
        allowed_ports = {int(port.strip()) for port in app.config["SSH_ALLOWED_PORTS"].split(",") if port.strip()}
    except ValueError:
        raise RuntimeError("SSH_ALLOWED_PORTS deve conter portas separadas por vírgula.") from None
    if any(not 1 <= port <= 65535 for port in allowed_ports):
        raise RuntimeError("SSH_ALLOWED_PORTS contém uma porta inválida.")
    if production and not allowed_ports:
        allowed_ports = {22}
    if app.config["BEHIND_PROXY"]:
        # Exactly one trusted reverse proxy, connected through a protected socket.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=0, x_port=0, x_prefix=0)
    if not app.config["DATABASE_URL"]:
        raise RuntimeError("Configure DATABASE_URL em back-end/.env.")
    if not app.config["SECRET_KEY"] or len(app.config["SECRET_KEY"]) < 32:
        raise RuntimeError("Configure uma SECRET_KEY aleatória de pelo menos 32 caracteres em back-end/.env.")
    try:
        app.extensions["vps_cipher"] = Fernet(app.config["VPS_ENCRYPTION_KEY"])
    except (ValueError, TypeError) as error:
        raise RuntimeError("Configure uma VPS_ENCRYPTION_KEY Fernet válida em back-end/.env.") from error
    engine, db_session = create_database(app.config["DATABASE_URL"], initialize=app.config["AUTO_CREATE_TABLES"])
    app.extensions["db_engine"] = engine
    app.extensions["db_session"] = db_session
    app.extensions["dummy_password_hash"] = generate_password_hash(secrets.token_urlsafe(32))
    init_auth(app)

    @app.cli.command("init-db")
    def init_db():
        """Create tables explicitly using a database migration/owner account."""
        Base.metadata.create_all(engine)
        print("Tabelas do VPS Monitor verificadas/criadas.")

    @app.after_request
    def private_response(response):
        if g.get("user") is not None or response.content_type.startswith("application/json"):
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error=error.description), error.code

    @app.errorhandler(SQLAlchemyError)
    def database_error(error):
        app.logger.error("Falha ao acessar o banco de dados (%s).", type(error).__name__)
        return jsonify(error="Banco de dados indisponível. Tente novamente em instantes."), 503

    @app.errorhandler(InvalidToken)
    def encryption_error(error):
        app.logger.error("Não foi possível descriptografar credenciais SSH.")
        return jsonify(error="Não foi possível abrir as credenciais. Confira a chave de criptografia do servidor."), 503

    @app.get("/api/vps")
    @login_required
    def get_vps_data():
        servers = owned_servers()
        if not servers:
            return jsonify([])
        with ThreadPoolExecutor(max_workers=min(8, len(servers))) as executor:
            results = list(executor.map(fetch_vps_metrics, servers))
        return jsonify(results)

    @app.post("/api/vps")
    @login_required
    def add_vps():
        data = json_object()
        name = text_field(data, "name", "Nome do servidor", 100)
        host = text_field(data, "ip", "IP do servidor", 45)
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            raise BadRequest("Informe um endereço IPv4 ou IPv6 válido.") from None
        # Public registration must not expose the API host's private network.
        effective_address = address.ipv4_mapped if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped else address
        if not effective_address.is_global:
            raise BadRequest("Informe um IP público para a VPS.")
        port = data.get("port", 22)
        if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
            raise BadRequest("A porta SSH deve ser um número entre 1 e 65535.")
        if allowed_ports and port not in allowed_ports:
            raise BadRequest("Esta porta SSH não está habilitada pelo administrador.")
        ssh_user = text_field(data, "user", "Usuário SSH", 100, required=False) or "root"
        location = text_field(data, "location", "Localização", 100, required=False) or "Brasil"
        credentials = {
            "password": text_field(data, "password", "Senha SSH", 1024, required=False, strip=False),
            "ssh_key": text_field(data, "ssh_key", "Chave SSH", 32768, required=False),
            "passphrase": text_field(data, "passphrase", "Senha da chave SSH", 1024, required=False, strip=False),
            "host_key_fingerprint": text_field(data, "host_key_fingerprint", "Identidade SSH da VPS", 100, required=False),
        }
        fingerprint = credentials["host_key_fingerprint"]
        if fingerprint and not re.fullmatch(r"SHA256:[A-Za-z0-9+/]{43}", fingerprint):
            raise BadRequest("Informe a fingerprint SSH no formato SHA256: seguido de 43 caracteres.")
        if production and not fingerprint:
            raise BadRequest("Informe a identidade SSH da VPS (fingerprint SHA256), confirmada no console do provedor.")
        if not credentials["password"] and not credentials["ssh_key"]:
            raise BadRequest("Informe uma senha SSH ou o conteúdo de uma chave privada.")
        if credentials["ssh_key"] and not (
            credentials["ssh_key"].startswith("-----BEGIN ") and "PRIVATE KEY-----" in credentials["ssh_key"]
        ):
            raise BadRequest("Cole o conteúdo da chave privada SSH, incluindo BEGIN e END.")
        cipher = app.extensions["vps_cipher"]
        server = VPSServer(
            user_id=g.user.id, name=name, ip=str(address), port=port,
            location=location, ssh_user=ssh_user,
            encrypted_credentials=cipher.encrypt(json.dumps(credentials).encode()).decode(),
        )
        with db_session() as db:
            # Serialize additions for this owner so concurrent requests respect the quota.
            db.scalar(select(User.id).where(User.id == g.user.id).with_for_update())
            count = db.scalar(select(func.count()).select_from(VPSServer).where(VPSServer.user_id == g.user.id))
            if count >= app.config["MAX_VPS_PER_USER"]:
                return jsonify(error="Limite de VPS da conta atingido. Contate o administrador."), 409
            db.add(server)
            db.commit()
        return jsonify(server.public_data()), 201

    @app.delete("/api/vps/<server_id>")
    @login_required
    def delete_vps(server_id):
        with db_session() as db:
            server = db.scalar(select(VPSServer).where(
                VPSServer.id == server_id, VPSServer.user_id == g.user.id,
            ))
            if server is None:
                return jsonify(error="Servidor não encontrado."), 404
            db.delete(server)
            db.commit()
        return jsonify(message="Servidor removido.")

    @app.get("/api/vps/debug-ssh")
    @login_required
    def debug_ssh():
        servers = owned_servers()
        if not servers:
            return jsonify([])
        with ThreadPoolExecutor(max_workers=min(8, len(servers))) as executor:
            results = list(executor.map(debug_vps_ssh, servers))
        return jsonify(results)

    @app.get("/")
    def index():
        if (FRONTEND_DIR / "index.html").is_file():
            return send_from_directory(FRONTEND_DIR, "index.html")
        return jsonify(message="VPS Monitor API. Inicie o frontend com npm run dev.")

    @app.get("/<path:asset>")
    def frontend_asset(asset):
        return send_from_directory(FRONTEND_DIR, asset)

    return app


if __name__ == "__main__":
    create_app().run(
        host="0.0.0.0", port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "false").lower() == "true",
    )
