"""Integration tests for critical Flask route handlers using the test client."""
import json
import os
import sqlite3
import time
import pytest


def _seed_scan(storage_dir: str, uuid: str, name: str = "test-case") -> None:
    """Insert a minimal scan row into the test database."""
    db_path = os.path.join(storage_dir, "scans.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT OR REPLACE INTO scans
           (uuid, name, status, dump_path, size, image, os, volatility_version, output_dir, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (uuid, name, "completed", "/tmp/fake.dump", 0, "vol3-img", "windows", "vol3",
         "/tmp/output", time.time()),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# POST /scan — validation
# ---------------------------------------------------------------------------

class TestCreateScan:
    def test_missing_dump_returns_400(self, client, auth_headers):
        resp = client.post("/scan", json={"os": "windows", "mode": "vol3"}, headers=auth_headers)
        assert resp.status_code == 400
        data = resp.get_json()
        assert "error" in data

    def test_missing_os_returns_400(self, client, auth_headers):
        resp = client.post("/scan", json={"dump": "/some/file.dmp", "mode": "vol3"}, headers=auth_headers)
        assert resp.status_code == 400
        data = resp.get_json()
        assert "error" in data

    def test_unauthenticated_returns_401(self, client):
        resp = client.post("/scan", json={"dump": "/some/file.dmp", "os": "windows"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /scans/<uuid>/status
# ---------------------------------------------------------------------------

class TestGetStatus:
    def test_unknown_uuid_returns_404(self, client, auth_headers):
        resp = client.get("/scans/nonexistent-uuid-123/status", headers=auth_headers)
        assert resp.status_code == 404

    def test_known_uuid_returns_status(self, client, auth_headers):
        storage_dir = os.environ.get("STORAGE_DIR", "/tmp/multivol_test_storage")
        scan_id = "test-scan-uuid-001"
        _seed_scan(storage_dir, scan_id)
        resp = client.get(f"/scans/{scan_id}/status", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "status" in data


# ---------------------------------------------------------------------------
# GET /evidences — response structure
# ---------------------------------------------------------------------------

class TestListEvidences:
    def test_returns_list(self, client, auth_headers):
        resp = client.get("/evidences", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

    def test_unauthenticated_returns_401(self, client):
        resp = client.get("/evidences")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /scans — list all scans
# ---------------------------------------------------------------------------

class TestListScans:
    def test_returns_list(self, client, auth_headers):
        resp = client.get("/scans", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

    def test_seeded_scan_appears(self, client, auth_headers):
        storage_dir = os.environ.get("STORAGE_DIR", "/tmp/multivol_test_storage")
        scan_id = "test-scan-uuid-002"
        _seed_scan(storage_dir, scan_id, name="visible-case")
        resp = client.get("/scans", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        uuids = [s.get("uuid") for s in data]
        assert scan_id in uuids


# ---------------------------------------------------------------------------
# GET /health — no auth required
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health_without_token_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
