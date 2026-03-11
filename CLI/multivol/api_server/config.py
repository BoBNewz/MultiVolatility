"""Runtime configuration: paths, tokens, and startup helpers."""
import os
import logging
import secrets

# Base paths — __file__ is CLI/multivol/api_server/config.py, BASE_DIR is CLI/
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

UPLOAD_FOLDER = os.path.join(BASE_DIR, 'storage', 'uploads')
STORAGE_DIR = os.environ.get("STORAGE_DIR", os.path.join(BASE_DIR, "storage"))

# Module-level snapshot used by code that imports these directly.
# For test overrides, prefer get_api_token() / get_app_password().
API_TOKEN = os.getenv("API_TOKEN") or ""
APP_PASSWORD = os.getenv("APP_PASSWORD") or ""

if not API_TOKEN:
    API_TOKEN = secrets.token_hex(32)
    logging.warning(
        "API_TOKEN env var is not set. Generated a random token for this session. "
        "Set API_TOKEN in your environment to use a stable token."
    )

if not APP_PASSWORD:
    logging.warning(
        "APP_PASSWORD env var is not set. Login will be disabled. "
        "Set APP_PASSWORD in your environment to enable password authentication."
    )


def get_api_token() -> str:
    """Read API_TOKEN from env at call time, falling back to the module-level snapshot."""
    return os.getenv("API_TOKEN") or API_TOKEN


def get_app_password() -> str:
    """Read APP_PASSWORD from env at call time."""
    return os.getenv("APP_PASSWORD") or APP_PASSWORD


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
