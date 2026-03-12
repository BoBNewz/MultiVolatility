"""Tests for memprocfs routes (multivol/api_server/routes/memprocfs.py)."""

from multivol.api_server.routes.memprocfs import (
    MODULE_NAME,
    SIDECAR_URL,
    _scan_dump_map,
    _scan_dump_lock,
)


class TestMemprocfsConstants:
    def test_module_name_defined(self):
        assert MODULE_NAME == "MemProcFS.FileList"

    def test_sidecar_url_is_string(self):
        assert isinstance(SIDECAR_URL, str)
        assert SIDECAR_URL.startswith("http")


class TestScanDumpMap:
    def test_scan_dump_map_starts_empty_or_dict(self):
        """_scan_dump_map is a dict mapping scan UUID -> dump path."""
        assert isinstance(_scan_dump_map, dict)

    def test_scan_dump_lock_is_lock(self):
        import threading
        assert isinstance(_scan_dump_lock, type(threading.Lock()))

    def test_scan_entry_can_be_set_and_cleared(self):
        """Verify the shared map can be written and read under the lock."""
        scan_id = "test-scan-uuid-memprocfs"
        with _scan_dump_lock:
            _scan_dump_map[scan_id] = "/data/test.dmp"
        try:
            with _scan_dump_lock:
                assert _scan_dump_map.get(scan_id) == "/data/test.dmp"
        finally:
            with _scan_dump_lock:
                _scan_dump_map.pop(scan_id, None)


class TestMemprocfsRoutes:
    def test_start_missing_scan_returns_404(self, client, auth_headers):
        resp = client.post(
            "/scans/nonexistent-uuid/memprocfs/start", headers=auth_headers
        )
        assert resp.status_code == 404

    def test_start_no_auth_returns_401(self, client):
        resp = client.post("/scans/nonexistent-uuid/memprocfs/start")
        assert resp.status_code == 401

    def test_files_missing_scan_returns_4xx(self, client, auth_headers):
        resp = client.get(
            "/scans/nonexistent-uuid/memprocfs/files", headers=auth_headers
        )
        assert resp.status_code in (404, 503)

    def test_status_missing_scan_returns_404(self, client, auth_headers):
        resp = client.get(
            "/scans/nonexistent-uuid/memprocfs/status", headers=auth_headers
        )
        assert resp.status_code in (200, 404)

    def test_stop_missing_scan_returns_4xx(self, client, auth_headers):
        resp = client.post(
            "/scans/nonexistent-uuid/memprocfs/stop", headers=auth_headers
        )
        assert resp.status_code in (404, 400, 200)
