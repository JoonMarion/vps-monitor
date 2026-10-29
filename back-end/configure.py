"""Prepare local configuration without printing or replacing existing secrets."""

import secrets
import shutil
from pathlib import Path

from cryptography.fernet import Fernet
from dotenv import dotenv_values, set_key


def configure_environment():
    backend_dir = Path(__file__).resolve().parent
    env_path = backend_dir / ".env"
    if not env_path.exists():
        shutil.copyfile(backend_dir / ".env.example", env_path)
    values = dotenv_values(env_path)
    if not values.get("SECRET_KEY"):
        set_key(env_path, "SECRET_KEY", secrets.token_hex(32))
    if not values.get("VPS_ENCRYPTION_KEY"):
        set_key(env_path, "VPS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    print("Configuração pronta em back-end/.env. Confira DATABASE_URL antes de iniciar.")


if __name__ == "__main__":
    configure_environment()
