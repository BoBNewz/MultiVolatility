"""Pytest fixtures shared across all test modules."""

import os
import tempfile
import pytest

# Point storage at a temp dir so tests don't touch real files.
# Use a tmpdir so parallel CI runs don't collide and cleanup is automatic.
_tmp_storage = tempfile.mkdtemp(prefix="multivol_test_")
os.environ.setdefault("STORAGE_DIR", _tmp_storage)
os.environ.setdefault("API_TOKEN", "test_token")
os.environ.setdefault("APP_PASSWORD", "test_password")


@pytest.fixture()
def app():
    """Create a Flask test application with a no-op runner."""
    from multivol.api_server import app as flask_app
    from multivol.api_server.routes.scan import init_runner
    from multivol.api_server.database import init_db
    from multivol.api_server.config import ensure_dirs

    ensure_dirs()   # create STORAGE_DIR and siblings so SQLite can open scans.db
    init_db()       # create tables
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
def db_conn(app):
    """Direct SQLite connection to the test database for test setup/teardown."""
    from multivol.api_server.database import get_db_connection
    with app.app_context():
        conn = get_db_connection()
        yield conn
        conn.close()


@pytest.fixture()
def tmp_file(tmp_path):
    """A real temporary file path (not yet created)."""
    return str(tmp_path / "testfile.bin")
