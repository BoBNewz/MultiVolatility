"""Tests for dump routes (multivol/api_server/routes/dump.py)."""
import pytest
from multivol.api_server.routes.dump import dump_tasks, dump_tasks_lock, DumpTask


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
        resp = client.get("/dump-tasks/nonexistent-task-id", headers=auth_headers)
        assert resp.status_code == 404

    def test_no_auth_returns_401(self, client):
        resp = client.get("/dump-tasks/nonexistent-task-id")
        assert resp.status_code == 401


class TestDownloadDumpResult:
    def test_missing_task_returns_404(self, client, auth_headers):
        resp = client.get("/dump-tasks/nonexistent-task-id/download", headers=auth_headers)
        assert resp.status_code == 404

    def test_no_auth_returns_401(self, client):
        resp = client.get("/dump-tasks/some-task/download")
        assert resp.status_code == 401


class TestDumpTaskDataStructure:
    def test_dump_task_typed_dict(self):
        """DumpTask TypedDict can hold expected fields."""
        task: DumpTask = {"status": "running", "output_dir": "/tmp/out"}
        assert task["status"] == "running"

    def test_dump_tasks_is_dict(self):
        assert isinstance(dump_tasks, dict)
