"""Tests for dump routes (multivol/api_server/routes/dump.py)."""
import pytest


class TestDumpFileFromMemory:
    def test_missing_scan_returns_404(self, client, auth_headers):
        resp = client.post(
            "/scans/nonexistent-scan-id/dump-file",
            json={"virt_addr": "0x1234"},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_no_auth_returns_401(self, client):
        resp = client.post(
            "/scans/nonexistent-scan-id/dump-file",
            json={"virt_addr": "0x1234"},
        )
        assert resp.status_code == 401


class TestGetDumpStatus:
    def test_missing_task_returns_404(self, client, auth_headers):
        resp = client.get("/dump-task/nonexistent-task-id", headers=auth_headers)
        assert resp.status_code == 404

    def test_no_auth_returns_401(self, client):
        resp = client.get("/dump-task/nonexistent-task-id")
        assert resp.status_code == 401
