"""Cookie sessions, CSRF protection and authenticated account endpoints."""

import hmac
import re
import secrets
from functools import wraps

from flask import Blueprint, current_app, g, jsonify, request, session
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import BadRequest
from werkzeug.security import check_password_hash, generate_password_hash

from database import User

auth = Blueprint("auth", __name__, url_prefix="/api/auth")


def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def json_object():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise BadRequest("Envie um objeto JSON válido.")
    return data


def text_field(data, key, label, maximum, *, required=True, strip=True):
    value = data.get(key, "")
    if not isinstance(value, str):
        raise BadRequest(f"{label} deve ser um texto.")
    if strip:
        value = value.strip()
    if required and not value:
        raise BadRequest(f"Informe {label.lower()}.")
    if len(value) > maximum:
        raise BadRequest(f"{label} deve ter no máximo {maximum} caracteres.")
    return value


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return jsonify(error="Faça login para continuar."), 401
        return view(*args, **kwargs)
    return wrapped


def init_auth(app):
    @app.before_request
    def load_user_and_validate_csrf():
        g.user = None
        if not request.path.startswith("/api/"):
            return
        user_id = session.get("user_id")
        if user_id:
            with current_app.extensions["db_session"]() as db:
                g.user = db.get(User, user_id)
            if g.user is None:
                session.clear()
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            # Reject unauthenticated VPS requests before checking the CSRF token.
            if request.path.startswith("/api/vps") and g.user is None:
                return jsonify(error="Faça login para continuar."), 401
            expected = session.get("csrf_token", "")
            supplied = request.headers.get("X-CSRF-Token", "")
            if not expected or not hmac.compare_digest(expected.encode(), supplied.encode()):
                return jsonify(error="Sua sessão mudou. Recarregue a página e tente novamente."), 403

    app.register_blueprint(auth)


def sign_in(user):
    session.clear()
    session.permanent = True
    session["user_id"] = user.id
    return {"user": user.public_data(), "csrf_token": csrf_token()}


@auth.get("/me")
def me():
    return jsonify(user=g.user.public_data() if g.user else None, csrf_token=csrf_token())


@auth.post("/register")
def register():
    data = json_object()
    name = text_field(data, "name", "Nome", 100)
    email = text_field(data, "email", "E-mail", 254).lower()
    password = text_field(data, "password", "Senha", 128, strip=False)
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise BadRequest("Informe um e-mail válido.")
    if len(password) < 8:
        raise BadRequest("A senha deve ter pelo menos 8 caracteres.")
    user = User(name=name, email=email, password_hash=generate_password_hash(password))
    with current_app.extensions["db_session"]() as db:
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return jsonify(error="Este e-mail já está cadastrado."), 409
    return jsonify(sign_in(user)), 201


@auth.post("/login")
def login():
    data = json_object()
    email = text_field(data, "email", "E-mail", 254).lower()
    password = text_field(data, "password", "Senha", 128, strip=False)
    with current_app.extensions["db_session"]() as db:
        user = db.scalar(select(User).where(User.email == email))
    # Keep a real password verification even when the account does not exist.
    password_hash = user.password_hash if user else current_app.extensions["dummy_password_hash"]
    if not check_password_hash(password_hash, password) or user is None:
        return jsonify(error="E-mail ou senha incorretos."), 401
    return jsonify(sign_in(user))


@auth.post("/logout")
@login_required
def logout():
    session.clear()
    return jsonify(user=None, csrf_token=csrf_token())
