"""
MemProcFS routes — manages on-demand MemProcFS sidecar containers
for Windows memory dump file recovery.

The sidecar container keeps a persistent memprocfs.Vmm handle open,
enabling instant file listing and downloads without re-initialization.
"""

import os
import re
import time
import json
import sqlite3
import threading
import docker
import logging
from typing import Any, Optional
from flask import Blueprint, request, jsonify, Response
import requests as http_requests
from multivol.api_server.database import get_db_connection
from multivol.api_server.utils import resolve_host_path
from multivol.api_server.config import STORAGE_DIR, BASE_DIR

memprocfs_bp = Blueprint('memprocfs_bp', __name__)

# ──────────────────────────────────────────────
# In-memory session tracking
# ──────────────────────────────────────────────
# Maps scan UUID -> {"container_name": str, "port": int, "started_at": float}
active_sessions = {}
sessions_lock = threading.Lock()

MEMPROCFS_IMAGE = "multivol-memprocfs"
SIDECAR_BASE_PORT = 15000  # Ephemeral port range start
MODULE_NAME = "MemProcFS.FileList"


def get_sidecar_url(scan_id: str) -> Optional[str]:
    """Return the sidecar base URL for a scan session, or None if no session is active."""
    with sessions_lock:
        session = active_sessions.get(scan_id)
        if not session:
            return None
        # Use container name as hostname (Docker DNS on shared network)
        return f"http://{session['container_name']}:5002"


def get_next_port() -> int:
    """Get the next available port for a sidecar."""
    with sessions_lock:
        used_ports = {s['port'] for s in active_sessions.values()}
        port = SIDECAR_BASE_PORT
        while port in used_ports:
            port += 1
        return port


def cleanup_container(container_name: str) -> None:
    """Stop and remove a container by name."""
    try:
        client = docker.from_env()
        try:
            container = client.containers.get(container_name)
            container.stop(timeout=5)
            container.remove(force=True)
        except docker.errors.NotFound:
            pass
    except Exception:
        logging.warning("Failed to cleanup container %s", container_name, exc_info=True)


# ──────────────────────────────────────────────
# Helpers for start_memprocfs
# ──────────────────────────────────────────────

def _get_or_check_active_session(uuid: str) -> Optional[Response]:
    """
    If a session exists and its container is still running, return a 200
    already_running response.  If the container has died, evict the stale
    session entry and return None so the caller can start fresh.
    Returns None when no session exists at all.
    """
    with sessions_lock:
        if uuid not in active_sessions:
            return None
        session = active_sessions[uuid]
        try:
            client = docker.from_env()
            container = client.containers.get(session['container_name'])
            if container.status == 'running':
                return jsonify({"status": "already_running", "port": session.get('port')})
        except Exception:
            del active_sessions[uuid]
    return None


def _lookup_scan_for_memprocfs(uuid: str) -> tuple[sqlite3.Row, str, str]:
    """
    Fetch the scan row, validate OS and dump file presence.
    Returns (scan, dump_path, dump_filename) on success.
    Raises ValueError with a (message, status_code) args tuple on failure.
    """
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM scans WHERE uuid = ?", (uuid,))
    scan = c.fetchone()
    conn.close()

    if not scan:
        raise ValueError("Scan not found", 404)
    if scan['os'] != 'windows':
        raise ValueError("MemProcFS is only supported for Windows scans", 400)

    dump_path = scan['dump_path']
    if not dump_path or not os.path.exists(dump_path):
        raise ValueError(f"Dump file not found: {dump_path}", 404)

    return scan, dump_path, os.path.basename(dump_path)


def _register_module_status(uuid: str) -> None:
    """Insert or update scan_module_status for MODULE_NAME to 'RUNNING'."""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute(
            "SELECT id FROM scan_module_status WHERE scan_id = ? AND module = ?",
            (uuid, MODULE_NAME)
        )
        if not c.fetchone():
            c.execute(
                "INSERT INTO scan_module_status (scan_id, module, status, updated_at) VALUES (?, ?, 'RUNNING', ?)",
                (uuid, MODULE_NAME, time.time())
            )
        else:
            c.execute(
                "UPDATE scan_module_status SET status = 'RUNNING', updated_at = ? WHERE scan_id = ? AND module = ?",
                (time.time(), uuid, MODULE_NAME)
            )
        conn.commit()
    except Exception:
        logging.exception("Failed to update module status for scan %s", uuid)
    finally:
        conn.close()


def _detect_network(client: docker.DockerClient) -> str:
    """Return the Docker network name shared with the multivol-api container, or 'bridge'."""
    try:
        api_container = client.containers.get('multivol-api')
        api_networks = list(api_container.attrs['NetworkSettings']['Networks'].keys())
        return api_networks[0] if api_networks else 'bridge'
    except Exception:
        return 'bridge'


def _wait_for_sidecar(container_name: str, uuid: str) -> None:
    """Poll the sidecar's /health endpoint and update module status when ready or timed out."""
    max_wait = 500
    start = time.time()
    sidecar_url = f"http://{container_name}:5002"

    while time.time() - start < max_wait:
        try:
            resp = http_requests.get(f"{sidecar_url}/health", timeout=3)
            if resp.status_code == 200 and resp.json().get('vmm_active'):
                conn = get_db_connection()
                c = conn.cursor()
                c.execute(
                    "UPDATE scan_module_status SET status = 'COMPLETED', updated_at = ? WHERE scan_id = ? AND module = ?",
                    (time.time(), uuid, MODULE_NAME)
                )
                conn.commit()
                conn.close()
                logging.info(f"MemProcFS sidecar ready for {uuid}")
                return
        except http_requests.exceptions.RequestException as poll_err:
            # Expected during sidecar initialization — suppress until ready
            logging.debug("Sidecar health check not ready yet: %s", poll_err)
        time.sleep(3)

    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "UPDATE scan_module_status SET status = 'FAILED', error_message = 'Sidecar initialization timeout', updated_at = ? WHERE scan_id = ? AND module = ?",
        (time.time(), uuid, MODULE_NAME)
    )
    conn.commit()
    conn.close()


# ──────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────

@memprocfs_bp.route('/memprocfs/<uuid>/start', methods=['POST'])
def start_memprocfs(uuid: str) -> Response:
    """
    Start a MemProcFS sidecar container for a Windows scan.
    The sidecar auto-initializes with the dump file and keeps the VMM handle alive.
    """
    already_running = _get_or_check_active_session(uuid)
    if already_running is not None:
        return already_running

    try:
        _scan, dump_path, dump_filename = _lookup_scan_for_memprocfs(uuid)
    except ValueError as exc:
        message, status_code = exc.args
        return jsonify({"error": message}), status_code

    _register_module_status(uuid)

    safe_uuid = re.sub(r'[^a-zA-Z0-9]', '', uuid)[:12]
    container_name = f"memprocfs_{safe_uuid}"
    cleanup_container(container_name)

    try:
        client = docker.from_env()
        network_name = _detect_network(client)
        host_dump_dir = resolve_host_path(os.path.dirname(dump_path))

        client.containers.run(
            image=MEMPROCFS_IMAGE,
            name=container_name,
            detach=True,
            network=network_name,
            volumes={host_dump_dir: {'bind': '/src', 'mode': 'ro'}},
            environment={'DUMP_PATH': f'/src/{dump_filename}', 'AUTO_INIT': 'true'},
            remove=False,
        )

        with sessions_lock:
            active_sessions[uuid] = {'container_name': container_name, 'started_at': time.time()}

        threading.Thread(
            target=_wait_for_sidecar, args=(container_name, uuid), daemon=True
        ).start()

        return jsonify({"status": "starting", "container": container_name})

    except docker.errors.ImageNotFound:
        return jsonify({
            "error": f"MemProcFS image '{MEMPROCFS_IMAGE}' not found. Build it first: docker build -t {MEMPROCFS_IMAGE} ./Dockerfiles/memprocfs/"
        }), 500
    except Exception as e:
        logging.error(f"Failed to start sidecar: {e}", exc_info=True)
        return jsonify({"error": f"Failed to start sidecar: {str(e)}"}), 500


def _load_cached_files(uuid: str) -> Optional[list]:
    """Return the cached file listing from the DB, or None if not cached / invalid."""
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT content FROM scan_results WHERE scan_id = ? AND module = ?", (uuid, MODULE_NAME))
    cached = c.fetchone()
    conn.close()
    if not cached:
        return None
    try:
        return json.loads(cached['content'])
    except json.JSONDecodeError:
        return None


def _fetch_and_cache_files(uuid: str) -> tuple[Optional[list], Optional[Response]]:
    """Fetch file listing from the MemProcFS sidecar and cache it. Returns (files, error_response)."""
    sidecar_url = get_sidecar_url(uuid)
    if not sidecar_url:
        return None, (jsonify({"error": "MemProcFS session not active. Start it first."}), 400)

    try:
        resp = http_requests.get(f"{sidecar_url}/list", timeout=300)
        if resp.status_code != 200:
            return None, (jsonify(resp.json()), resp.status_code)
        all_files = resp.json()
    except http_requests.exceptions.ConnectionError:
        return None, (jsonify({"error": "MemProcFS sidecar is not reachable. It may still be initializing."}), 503)
    except http_requests.exceptions.Timeout:
        return None, (jsonify({"error": "MemProcFS file listing timed out (>5 min)"}), 504)
    except Exception as e:
        return None, (jsonify({"error": f"Failed to fetch files: {str(e)}"}), 500)

    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT id FROM scan_results WHERE scan_id = ? AND module = ?", (uuid, MODULE_NAME))
        if not c.fetchone():
            c.execute(
                "INSERT INTO scan_results (scan_id, module, content, created_at) VALUES (?, ?, ?, ?)",
                (uuid, MODULE_NAME, json.dumps(all_files), time.time()),
            )
        conn.commit()
        conn.close()
    except Exception:
        logging.warning("Failed to cache MemProcFS results for scan %s", uuid, exc_info=True)

    return all_files, None


@memprocfs_bp.route('/memprocfs/<uuid>/files', methods=['GET'])
def get_memprocfs_files(uuid: str) -> Response:
    """
    Get file listing from the MemProcFS sidecar.
    Supports pagination: ?limit=500&offset=0&search=
    Caches the FULL results in scan_results, serves paginated slices.
    """
    limit = request.args.get('limit', 500, type=int)
    offset = request.args.get('offset', 0, type=int)
    search = request.args.get('search', '', type=str).strip().lower()

    all_files = _load_cached_files(uuid)
    if all_files is None:
        all_files, error_response = _fetch_and_cache_files(uuid)
        if error_response is not None:
            return error_response

    if search:
        all_files = [f for f in all_files if search in f.get('Name', '').lower()]

    total = len(all_files)
    page_files = all_files[offset:offset + limit] if limit > 0 else all_files

    return jsonify({
        "results": page_files,
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": (offset + limit) < total if limit > 0 else False,
    })


@memprocfs_bp.route('/memprocfs/<uuid>/download', methods=['GET'])
def download_memprocfs_file(uuid: str) -> Response:
    """
    Download a file via the MemProcFS sidecar's persistent VMM handle.
    Instant because the handle is already open.
    """
    vfs_path = request.args.get('path')
    if not vfs_path:
        return jsonify({"error": "Missing 'path' parameter"}), 400

    sidecar_url = get_sidecar_url(uuid)
    if not sidecar_url:
        return jsonify({"error": "MemProcFS session not active"}), 400

    try:
        resp = http_requests.get(
            f"{sidecar_url}/read",
            params={'path': vfs_path},
            timeout=60,
            stream=True
        )

        if resp.status_code != 200:
            try:
                return jsonify(resp.json()), resp.status_code
            except Exception:
                return jsonify({"error": "Download failed"}), resp.status_code

        # Stream the response back to the client
        filename = os.path.basename(vfs_path)
        return Response(
            resp.iter_content(chunk_size=8192),
            mimetype='application/octet-stream',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Content-Length': resp.headers.get('Content-Length', '')
            }
        )

    except Exception as e:
        return jsonify({"error": f"Download failed: {str(e)}"}), 500


@memprocfs_bp.route('/memprocfs/<uuid>/stop', methods=['DELETE'])
def stop_memprocfs(uuid: str) -> Response:
    """Stop and remove the MemProcFS sidecar container."""
    with sessions_lock:
        session = active_sessions.pop(uuid, None)

    if not session:
        return jsonify({"status": "not_running"})

    cleanup_container(session['container_name'])
    return jsonify({"status": "stopped"})


@memprocfs_bp.route('/memprocfs/<uuid>/status', methods=['GET'])
def memprocfs_status(uuid: str) -> Response:
    """Check if a MemProcFS session is active and healthy."""
    sidecar_url = get_sidecar_url(uuid)
    if not sidecar_url:
        return jsonify({"active": False})

    try:
        resp = http_requests.get(f"{sidecar_url}/health", timeout=3)
        if resp.status_code == 200:
            health = resp.json()
            return jsonify({
                "active": True,
                "vmm_ready": health.get('vmm_active', False),
                "files_cached": health.get('files_cached', False)
            })
    except http_requests.exceptions.RequestException as health_err:
        # Sidecar unreachable — treat as inactive
        logging.debug("MemProcFS health check failed: %s", health_err)
