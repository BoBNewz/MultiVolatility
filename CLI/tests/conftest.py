"""Pytest fixtures shared across all test modules."""

import os
import pytest

# Point storage at a temp dir so tests don't touch real files
os.environ.setdefault("STORAGE_DIR", "/tmp/multivol_test_storage")
os.environ.setdefault("API_TOKEN", "test_token")
os.environ.setdefault("APP_PASSWORD", "test_password")


@pytest.fixture()
def app():
    """Create a Flask test application with a no-op runner."""
    from multivol.api_server import app as flask_app
    from multivol.api_server.routes.scan import init_runner

    init_runner(lambda args: None)  # no-op runner so /scan routes don't crash
    flask_app.app.config["TESTING"] = True
    yield flask_app.app


@pytest.fixture()
def client(app):
    """Flask test client with the API token pre-set."""
    return app.test_client()


@pytest.fixture()
def auth_headers():
    """Authorization header for authenticated requests."""
    return {"Authorization": "Bearer test_token"}


@pytest.fixture()
def tmp_file(tmp_path):
    """A real temporary file path (not yet created)."""
    return str(tmp_path / "testfile.bin")
