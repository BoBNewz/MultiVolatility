"""Tests for multivol/api_server/database.py"""
import sqlite3
import pytest


@pytest.fixture()
def isolated_storage(tmp_path, monkeypatch):
    """Point STORAGE_DIR and the config module at a fresh temp dir for each test."""
    import multivol.api_server.config as cfg
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    monkeypatch.setattr(cfg, "STORAGE_DIR", str(tmp_path))
    # Force database module to pick up the new path
    import multivol.api_server.database as db_mod
    monkeypatch.setattr(db_mod, "STORAGE_DIR", str(tmp_path))
    yield tmp_path


def test_init_db_creates_tables(isolated_storage):
    from multivol.api_server.database import init_db, get_db_connection

    init_db()
    conn = get_db_connection()
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}
    conn.close()
    assert "scans" in tables
    assert "scan_module_status" in tables
    assert "scan_results" in tables
    assert "dump_tasks" in tables


def test_get_db_connection_returns_connection(isolated_storage):
    from multivol.api_server.database import init_db, get_db_connection

    init_db()
    conn = get_db_connection()
    assert isinstance(conn, sqlite3.Connection)
    result = conn.execute("SELECT 1").fetchone()
    assert result[0] == 1
    conn.close()


def test_init_db_idempotent(isolated_storage):
    from multivol.api_server.database import init_db, get_db_connection

    init_db()
    init_db()  # second call must not raise

    conn = get_db_connection()
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}
    conn.close()
    assert "scans" in tables
