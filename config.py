import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    INITIAL_OWNER_EMAIL = os.environ.get("INITIAL_OWNER_EMAIL", "dono@pontofacil.local")
    INITIAL_OWNER_PASSWORD = os.environ.get("INITIAL_OWNER_PASSWORD")
    TIMEZONE = os.environ.get("TIMEZONE", "America/Sao_Paulo")
    WTF_CSRF_TIME_LIMIT = 3600
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'instance' / 'pontofacil.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
