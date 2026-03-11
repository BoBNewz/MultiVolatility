import os
import logging

# Base paths — __file__ is CLI/multivol/api_server/config.py, BASE_DIR is CLI/
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

UPLOAD_FOLDER = os.path.join(BASE_DIR, 'storage', 'uploads')
STORAGE_DIR = os.environ.get("STORAGE_DIR", os.path.join(BASE_DIR, "storage"))

API_TOKEN = os.getenv("API_TOKEN", "multivol_default_secret_token")
APP_PASSWORD = os.getenv("APP_PASSWORD", "multivol_password")


def ensure_dirs() -> None:
    """Create required runtime directories. Called once at app startup."""
    for path in [
        STORAGE_DIR,
        UPLOAD_FOLDER,
        os.path.join(BASE_DIR, 'volatility3_plugins'),
        os.path.join(BASE_DIR, 'volatility3_symbols'),
        os.path.join(BASE_DIR, 'volatility3_cache'),
        os.path.join(BASE_DIR, 'volatility2_profiles'),
    ]:
        os.makedirs(path, exist_ok=True)
