"""Tests for memprocfs routes (multivol/api_server/routes/memprocfs.py)."""

import json
from unittest.mock import patch, MagicMock
import requests as http_requests

from multivol.api_server.routes.memprocfs import (
    MODULE_NAME,
    _lookup_scan,
    _load_cached_files,
    _scan_dump_map,
    _scan_dump_lock,
)


# ──────────────────────────────────────────────
# _lookup_scan
# ──────────────────────────────────────────────


class TestLookupScan:
    def test_missing_scan_raises(self, app):
        with app.app_context():
            try:
                _lookup_scan("nonexistent-uuid")
                assert False, "Should have raised"
            except ValueError as exc:
                assert exc.args[1] == 404

    def test_linux_scan_raises_400(self, app, db_conn):
        db_conn.execute(
            "INSERT INTO scans (uuid, os, dump_path, created_at) VALUES (?,?,?,?)",
            ("linux-scan-uuid", "linux", "/tmp/fake.dmp", 0),
        )
        db_conn.commit()
        with app.app_context():
            try:
                _lookup_scan("linux-scan-uuid")
                assert False, "Should have raised"
            except ValueError as exc:
                assert exc.args[1] == 400

    def test_missing_dump_file_raises_404(self, app, db_conn):
        db_conn.execute(
            "INSERT INTO scans (uuid, os, dump_path, created_at) VALUES (?,?,?,?)",
            ("win-scan-uuid", "windows", "/nonexistent/path.dmp", 0),
        )
        db_conn.commit()
        with app.app_context():
            try:
                _lookup_scan("win-scan-uuid")
                assert False, "Should have raised"
            except ValueError as exc:
                assert exc.args[1] == 404


# ──────────────────────────────────────────────
# _load_cached_files
# ──────────────────────────────────────────────


class TestLoadCachedFiles:
    def test_returns_none_when_no_cache(self, app):
        with app.app_context():
            result = _load_cached_files("no-cache-uuid")
        assert result is None

    def test_returns_list_when_cached(self, app, db_conn):
        files = [{"Name": "\\Windows\\notepad.exe", "Size": 1234}]
        db_conn.execute(
            "INSERT INTO scan_results (scan_id, module, content, created_at) VALUES (?,?,?,?)",
            ("cached-scan-uuid", MODULE_NAME, json.dumps(files), 0),
        )
        db_conn.commit()
        with app.app_context():
            result = _load_cached_files("cached-scan-uuid")
        assert result == files

    def test_returns_none_on_corrupt_json(self, app, db_conn):
        db_conn.execute(
            "INSERT INTO scan_results (scan_id, module, content, created_at) VALUES (?,?,?,?)",
            ("corrupt-scan-uuid", MODULE_NAME, "not-json{{", 0),
        )
        db_conn.commit()
        with app.app_context():
            result = _load_cached_files("corrupt-scan-uuid")
        assert result is None


# ──────────────────────────────────────────────
# Routes — sidecar mocked
# ──────────────────────────────────────────────


class TestMemprocfsRoutes:
    def test_start_missing_scan_returns_404(self, client, auth_headers):
        resp = client.post(
            "/memprocfs/nonexistent-uuid/start", headers=auth_headers
        )
        assert resp.status_code == 404

    def test_start_no_auth_returns_401(self, client):
        resp = client.post("/memprocfs/nonexistent-uuid/start")
        assert resp.status_code == 401

    def test_files_missing_scan_returns_503_when_sidecar_down(self, client, auth_headers):
        """When no cache and sidecar is unreachable, /files returns 503."""
        with patch("multivol.api_server.routes.memprocfs.http_requests.get") as mock_get:
            mock_get.side_effect = http_requests.exceptions.ConnectionError("down")
            resp = client.get(
                "/memprocfs/nonexistent-uuid/files", headers=auth_headers
            )
        assert resp.status_code == 503

    def test_files_returns_paginated_results_from_cache(self, client, auth_headers, db_conn):
        """When the DB cache is warm, /files returns paginated data without hitting sidecar."""
        files = [{"Name": f"\\file{i}.exe", "Size": i * 100} for i in range(10)]
        db_conn.execute(
            "INSERT INTO scan_results (scan_id, module, content, created_at) VALUES (?,?,?,?)",
            ("paged-scan-uuid", MODULE_NAME, json.dumps(files), 0),
        )
        db_conn.commit()
        resp = client.get(
            "/memprocfs/paged-scan-uuid/files?limit=3&offset=0",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["results"]) == 3
        assert data["total"] == 10
        assert data["has_more"] is True

    def test_files_search_filters_results(self, client, auth_headers, db_conn):
        """Search param filters by name (case-insensitive)."""
        files = [
            {"Name": "\\Windows\\notepad.exe", "Size": 100},
            {"Name": "\\Windows\\cmd.exe", "Size": 200},
        ]
        db_conn.execute(
            "INSERT INTO scan_results (scan_id, module, content, created_at) VALUES (?,?,?,?)",
            ("search-scan-uuid", MODULE_NAME, json.dumps(files), 0),
        )
        db_conn.commit()
        resp = client.get(
            "/memprocfs/search-scan-uuid/files?search=notepad",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 1
        assert "notepad" in data["results"][0]["Name"].lower()

    def test_status_returns_inactive_when_scan_not_tracked(self, client, auth_headers):
        """Status for an untracked scan UUID reports active=False."""
        mock_health = {"vmm_active": True, "dump_path": "/other.dmp", "status": "ready", "files_cached": False}
        with patch("multivol.api_server.routes.memprocfs.http_requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_health
            mock_get.return_value = mock_resp
            resp = client.get(
                "/memprocfs/untracked-uuid/status", headers=auth_headers
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["active"] is False
        assert data["vmm_ready"] is False

    def test_stop_clears_scan_tracking(self, client, auth_headers):
        """POST /stop removes the scan from _scan_dump_map."""
        with _scan_dump_lock:
            _scan_dump_map["stop-test-uuid"] = "/app/storage/test.dmp"
        with patch("multivol.api_server.routes.memprocfs.http_requests.post"):
            resp = client.delete(
                "/memprocfs/stop-test-uuid/stop", headers=auth_headers
            )
        assert resp.status_code in (200, 405)
        with _scan_dump_lock:
            assert "stop-test-uuid" not in _scan_dump_map

    def test_download_missing_path_returns_400(self, client, auth_headers):
        resp = client.get(
            "/memprocfs/any-uuid/download", headers=auth_headers
        )
        assert resp.status_code == 400
