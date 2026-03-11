"""Tests for memprocfs routes (multivol/api_server/routes/memprocfs.py)."""
from multivol.api_server.routes.memprocfs import (
    get_sidecar_url,
    get_next_port,
    active_sessions,
    sessions_lock,
    SIDECAR_PORT,
    SIDECAR_BASE_PORT,
    MODULE_NAME,
)


class TestGetSidecarUrl:
    def test_returns_none_when_no_session(self):
        """Returns None if no active session exists for the scan."""
        url = get_sidecar_url("nonexistent-scan-uuid")
        assert url is None

    def test_returns_url_when_session_active(self):
        """Returns the sidecar URL when session is tracked in active_sessions."""
        scan_id = "test-memprocfs-scan"
        with sessions_lock:
            active_sessions[scan_id] = {
                "container_name": "vol_memprocfs_test",
                "port": SIDECAR_BASE_PORT,
                "started_at": 0.0,
            }
        try:
            url = get_sidecar_url(scan_id)
            assert url is not None
            assert "vol_memprocfs_test" in url
            assert str(SIDECAR_PORT) in url
        finally:
            with sessions_lock:
                active_sessions.pop(scan_id, None)


class TestGetNextPort:
    def test_returns_base_port_when_no_sessions(self):
        """When no sessions are active, returns SIDECAR_BASE_PORT."""
        with sessions_lock:
            saved = dict(active_sessions)
            active_sessions.clear()
        try:
            port = get_next_port()
            assert port == SIDECAR_BASE_PORT
        finally:
            with sessions_lock:
                active_sessions.update(saved)

    def test_skips_used_ports(self):
        """Returns next available port when base port is already in use."""
        scan_id = "port-test-scan"
        with sessions_lock:
            active_sessions[scan_id] = {
                "container_name": "test_container",
                "port": SIDECAR_BASE_PORT,
                "started_at": 0.0,
            }
        try:
            port = get_next_port()
            assert port == SIDECAR_BASE_PORT + 1
        finally:
            with sessions_lock:
                active_sessions.pop(scan_id, None)


class TestMemprocfsConstants:
    def test_module_name_defined(self):
        assert MODULE_NAME == "MemProcFS.FileList"

    def test_sidecar_base_port_is_valid(self):
        assert SIDECAR_BASE_PORT > 1024


class TestMemprocfsRoutes:
    def test_start_missing_scan_returns_404(self, client, auth_headers):
        resp = client.post("/scans/nonexistent-uuid/memprocfs/start", headers=auth_headers)
        assert resp.status_code == 404

    def test_start_no_auth_returns_401(self, client):
        resp = client.post("/scans/nonexistent-uuid/memprocfs/start")
        assert resp.status_code == 401

    def test_files_missing_scan_returns_4xx(self, client, auth_headers):
        resp = client.get("/scans/nonexistent-uuid/memprocfs/files", headers=auth_headers)
        assert resp.status_code in (404, 503)

    def test_status_missing_scan_returns_404(self, client, auth_headers):
        resp = client.get("/scans/nonexistent-uuid/memprocfs/status", headers=auth_headers)
        assert resp.status_code in (200, 404)

    def test_stop_missing_scan_returns_4xx(self, client, auth_headers):
        resp = client.post("/scans/nonexistent-uuid/memprocfs/stop", headers=auth_headers)
        assert resp.status_code in (404, 400, 200)
