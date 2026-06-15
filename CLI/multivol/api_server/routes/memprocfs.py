"""
MemProcFS routes — proxies requests to the persistent memprocfs compose service.

Instead of spawning per-scan containers, the API talks to a single always-running
sidecar (service name: memprocfs, port 5002) via its /load endpoint.  The sidecar
maintains a 1-slot VMM cache: it keeps the last loaded dump warm and evicts it
when a different dump is requested.
"""

import os
import time
import json
import sqlite3
import threading
import logging
from typing import Optional
from flask import Blueprint, request, jsonify, Response
import requests as http_requests
from multivol.api_server.database import get_db_connection

# Fixed URL for the compose sidecar service (Docker DNS resolves the service name)
SIDECAR_URL: str = os.environ.get("MEMPROCFS_SIDECAR_URL", "http://memprocfs:5002")

MODULE_NAME = "MemProcFS.FileList"

memprocfs_bp = Blueprint("memprocfs_bp", __name__)

# ──────────────────────────────────────────────
# In-memory scan → dump-path tracking
# ──────────────────────────────────────────────
# Maps scan UUID -> dump_path that was sent to the sidecar.
# Used to detect whether the sidecar already holds the right dump.
_scan_dump_map: dict[str, str] = {}
_scan_dump_lock = threading.Lock()


# ──────────────────────────────────────────────
# DB helpers
# ──────────────────────────────────────────────


def _lookup_scan(uuid: str) -> sqlite3.Row:
    """Fetch and return the scan row, or raise ValueError if not found / invalid."""
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM scans WHERE uuid = ?", (uuid,))
    scan = c.fetchone()
    conn.close()
    if not scan:
        raise ValueError("Scan not found", 404)
    if scan["os"] != "windows":
        raise ValueError("MemProcFS is only supported for Windows scans", 400)
    dump_path = scan["dump_path"]
    if not dump_path or not os.path.exists(dump_path):
        raise ValueError(f"Dump file not found: {dump_path}", 404)
    return scan


def _set_module_status(uuid: str, status: str, error_msg: str = "") -> None:
    """Upsert the scan_module_status row for MODULE_NAME."""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute(
            "SELECT id FROM scan_module_status WHERE scan_id = ? AND module = ?",
            (uuid, MODULE_NAME),
        )
        exists = c.fetchone()
        if exists:
            c.execute(
                "UPDATE scan_module_status SET status = ?, error_message = ?,"
                " updated_at = ? WHERE scan_id = ? AND module = ?",
                (status, error_msg, time.time(), uuid, MODULE_NAME),
            )
        else:
            c.execute(
                "INSERT INTO scan_module_status"
                " (scan_id, module, status, error_message, updated_at) VALUES (?,?,?,?,?)",
                (uuid, MODULE_NAME, status, error_msg, time.time()),
            )
        conn.commit()
    except Exception:  # pylint: disable=broad-except
        logging.exception("Failed to update module status for %s", uuid)
    finally:
        conn.close()


# ──────────────────────────────────────────────
# Sidecar communication
# ──────────────────────────────────────────────


def _wait_for_sidecar(uuid: str, dump_path: str) -> None:
    """Poll /health until the sidecar has the correct dump loaded, then update DB."""
    max_wait = 7200  # 2 hours max wait for large memory dumps
    start = time.time()

    while time.time() - start < max_wait:
        try:
            resp = http_requests.get(f"{SIDECAR_URL}/health", timeout=3)
            if resp.status_code == 200:
                health = resp.json()
                if health.get("vmm_active") and health.get("dump_path") == dump_path:
                    _set_module_status(uuid, "COMPLETED")
                    logging.info("MemProcFS ready for scan %s", uuid)
                    return
                if health.get("status") == "error":
                    _set_module_status(uuid, "FAILED", health.get("error", "VMM init error"))
                    return
        except http_requests.exceptions.RequestException as e:
            logging.debug("Health poll not ready yet: %s", e)
        time.sleep(3)

    _set_module_status(uuid, "FAILED", "Sidecar initialization timeout")
    logging.error("MemProcFS timed out for scan %s", uuid)


def _load_cached_files(uuid: str) -> Optional[list]:
    """Return the cached file listing from the DB, or None."""
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        "SELECT content FROM scan_results WHERE scan_id = ? AND module = ?",
        (uuid, MODULE_NAME),
    )
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    try:
        return json.loads(row["content"])
    except json.JSONDecodeError:
        return None


def _fetch_and_cache_files(uuid: str) -> tuple[Optional[list], Optional[tuple]]:
    """Fetch file listing from the sidecar and cache in DB.  Returns (files, error_tuple)."""
    try:
        resp = http_requests.get(f"{SIDECAR_URL}/list", timeout=300)
    except http_requests.exceptions.ConnectionError:
        return None, (
            jsonify({"error": "MemProcFS sidecar unreachable. It may still be loading."}),
            503,
        )
    except http_requests.exceptions.Timeout:
        return None, (jsonify({"error": "MemProcFS file listing timed out (>5 min)"}), 504)
    except Exception as e:  # pylint: disable=broad-except
        return None, (jsonify({"error": f"Failed to fetch files: {str(e)}"}), 500)

    if resp.status_code != 200:
        return None, (jsonify(resp.json()), resp.status_code)

    all_files = resp.json()

    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            "SELECT id FROM scan_results WHERE scan_id = ? AND module = ?",
            (uuid, MODULE_NAME),
        )
        if not c.fetchone():
            c.execute(
                "INSERT INTO scan_results (scan_id, module, content, created_at)"
                " VALUES (?, ?, ?, ?)",
                (uuid, MODULE_NAME, json.dumps(all_files), time.time()),
            )
        conn.commit()
        conn.close()
    except Exception:  # pylint: disable=broad-except
        logging.warning("Failed to cache MemProcFS results for scan %s", uuid, exc_info=True)

    return all_files, None


# ──────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────


@memprocfs_bp.route("/memprocfs/<uuid>/start", methods=["POST"])
def start_memprocfs(uuid: str) -> Response:
    """Tell the sidecar to load this scan's dump file."""
    try:
        scan = _lookup_scan(uuid)
    except ValueError as exc:
        message = exc.args[0] if exc.args else "Unknown error"
        status_code = exc.args[1] if len(exc.args) > 1 else 500
        return jsonify({"error": message}), status_code

    dump_path: str = scan["dump_path"]

    # If the sidecar already has this dump loaded (or is loading it), don't re-request.
    with _scan_dump_lock:
        already_requested = _scan_dump_map.get(uuid) == dump_path
    if already_requested:
        return jsonify({"status": "already_starting", "dump_path": dump_path})

    _set_module_status(uuid, "RUNNING")

    try:
        resp = http_requests.post(
            f"{SIDECAR_URL}/load", json={"dump_path": dump_path}, timeout=10
        )
        if resp.status_code not in (200, 202):
            _set_module_status(uuid, "FAILED", resp.json().get("error", "load failed"))
            return jsonify(resp.json()), resp.status_code
    except http_requests.exceptions.RequestException as e:
        _set_module_status(uuid, "FAILED", str(e))
        return jsonify({"error": f"Could not reach MemProcFS sidecar: {e}"}), 503

    with _scan_dump_lock:
        _scan_dump_map[uuid] = dump_path

    threading.Thread(
        target=_wait_for_sidecar, args=(uuid, dump_path), daemon=True
    ).start()

    return jsonify({"status": "starting", "dump_path": dump_path})


@memprocfs_bp.route("/memprocfs/<uuid>/files", methods=["GET"])
def get_memprocfs_files(uuid: str) -> Response:
    """Paginated file listing from the sidecar (cached after first fetch)."""
    limit = request.args.get("limit", 500, type=int)
    offset = request.args.get("offset", 0, type=int)
    search = request.args.get("search", "", type=str).strip().lower()

    all_files = _load_cached_files(uuid)
    if all_files is None:
        all_files, error_response = _fetch_and_cache_files(uuid)
        if error_response is not None:
            return error_response

    if search:
        all_files = [f for f in all_files if search in f.get("Name", "").lower()]

    total = len(all_files)
    page_files = all_files[offset : offset + limit] if limit > 0 else all_files

    return jsonify(
        {
            "results": page_files,
            "total": total,
            "offset": offset,
            "limit": limit,
            "has_more": (offset + limit) < total if limit > 0 else False,
        }
    )


@memprocfs_bp.route("/memprocfs/<uuid>/download", methods=["GET"])
def download_memprocfs_file(uuid: str) -> Response:
    """Proxy a file download from the sidecar."""
    vfs_path = request.args.get("path")
    if not vfs_path:
        return jsonify({"error": "Missing 'path' parameter"}), 400

    try:
        resp = http_requests.get(
            f"{SIDECAR_URL}/read", params={"path": vfs_path}, timeout=60, stream=True
        )
    except Exception as e:  # pylint: disable=broad-except
        return jsonify({"error": f"Download failed: {str(e)}"}), 500

    if resp.status_code != 200:
        try:
            return jsonify(resp.json()), resp.status_code
        except Exception:  # pylint: disable=broad-except
            return jsonify({"error": "Download failed"}), resp.status_code

    filename = os.path.basename(vfs_path)
    return Response(
        resp.iter_content(chunk_size=8192),
        mimetype="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": resp.headers.get("Content-Length", ""),
        },
    )


@memprocfs_bp.route("/memprocfs/<uuid>/stop", methods=["DELETE"])
def stop_memprocfs(uuid: str) -> Response:
    """Unload the sidecar's current VMM and clear local tracking."""
    with _scan_dump_lock:
        _scan_dump_map.pop(uuid, None)

    try:
        http_requests.post(f"{SIDECAR_URL}/unload", timeout=5)
    except http_requests.exceptions.RequestException:
        pass  # Best-effort; sidecar may already be idle

    return jsonify({"status": "stopped"})


@memprocfs_bp.route("/memprocfs/<uuid>/status", methods=["GET"])
def memprocfs_status(uuid: str) -> Response:
    """Check the sidecar health and whether it holds this scan's dump."""
    with _scan_dump_lock:
        expected_dump = _scan_dump_map.get(uuid)

    try:
        resp = http_requests.get(f"{SIDECAR_URL}/health", timeout=3)
        if resp.status_code == 200:
            health = resp.json()
            dump_matches = (
                expected_dump is not None and health.get("dump_path") == expected_dump
            )
            return jsonify(
                {
                    "active": dump_matches,
                    "vmm_ready": health.get("vmm_active", False) and dump_matches,
                    "files_cached": health.get("files_cached", False),
                    "sidecar_status": health.get("status"),
                }
            )
    except http_requests.exceptions.RequestException as e:
        logging.debug("MemProcFS health check failed: %s", e)

    return jsonify({"active": False, "vmm_ready": False})
