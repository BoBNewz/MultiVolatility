import os

# Base paths
# Compute BASE_DIR as the directory containing the CLI
# __file__ is CLI/multivol/api_server/config.py
# BASE_DIR should be CLI/ (which is /app in the docker container)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

UPLOAD_FOLDER = os.path.join(BASE_DIR, 'storage', 'uploads')
STORAGE_DIR = os.environ.get("STORAGE_DIR", os.path.join(BASE_DIR, "storage"))

# Create dirs if they don't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, 'volatility3_plugins'), exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, 'volatility3_symbols'), exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, 'volatility3_cache'), exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, 'volatility2_profiles'), exist_ok=True)

API_TOKEN = os.getenv("API_TOKEN", "multivol_default_secret_token")
