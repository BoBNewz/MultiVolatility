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
from flask import Blueprint, request, jsonify, Response
import requests as http_requests
from ..database import get_db_connection
from ..utils import resolve_host_path
from ..config import STORAGE_DIR, BASE_DIR

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


def get_sidecar_url(scan_id):
    """Get the sidecar URL for a scan session."""
    with sessions_lock:
        session = active_sessions.get(scan_id)
        if not session:
            return None
        # Use container name as hostname (Docker DNS on shared network)
        return f"http://{session['container_name']}:5002"


def get_next_port():
    """Get the next available port for a sidecar."""
    with sessions_lock:
        used_ports = {s['port'] for s in active_sessions.values()}
        port = SIDECAR_BASE_PORT
        while port in used_ports:
            port += 1
        return port


def cleanup_container(container_name):
    """Stop and remove a container by name."""
    try:
        client = docker.from_env()
        try:
            container = client.containers.get(container_name)
            container.stop(timeout=5)
            container.remove(force=True)
        except docker.errors.NotFound:
            pass
    except Exception as e:
        print(f"[WARN] Failed to cleanup container {container_name}: {e}")


# ──────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────

@memprocfs_bp.route('/memprocfs/<uuid>/start', methods=['POST'])
def start_memprocfs(uuid):
    """
    Start a MemProcFS sidecar container for a Windows scan.
    The sidecar auto-initializes with the dump file and keeps the VMM handle alive.
    """
    # Check if already running
    with sessions_lock:
        if uuid in active_sessions:
            session = active_sessions[uuid]
            # Verify container is still alive
            try:
                client = docker.from_env()
                container = client.containers.get(session['container_name'])
                if container.status == 'running':
                    return jsonify({
                        "status": "already_running",
                        "port": session['port']
                    })
            except:
                # Container died, clean up
                del active_sessions[uuid]

    # Get scan info from DB
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM scans WHERE uuid = ?", (uuid,))
    scan = c.fetchone()

    if not scan:
        conn.close()
        return jsonify({"error": "Scan not found"}), 404

    if scan['os'] != 'windows':
        conn.close()
        return jsonify({"error": "MemProcFS is only supported for Windows scans"}), 400

    dump_path = scan['dump_path']
    if not dump_path or not os.path.exists(dump_path):
        conn.close()
        return jsonify({"error": f"Dump file not found: {dump_path}"}), 404

    # Register module in scan_module_status
    try:
        c.execute("SELECT id FROM scan_module_status WHERE scan_id = ? AND module = ?", (uuid, MODULE_NAME))
        if not c.fetchone():
            c.execute(
                "INSERT INTO scan_module_status (scan_id, module, status, updated_at) VALUES (?, ?, 'RUNNING', ?)",
                (uuid, MODULE_NAME, time.time())
            )
            conn.commit()
        else:
            c.execute(
                "UPDATE scan_module_status SET status = 'RUNNING', updated_at = ? WHERE scan_id = ? AND module = ?",
                (time.time(), uuid, MODULE_NAME)
            )
            conn.commit()
    except Exception as e:
        print(f"[ERROR] Failed to update module status: {e}")
    finally:
        conn.close()

    # Start the sidecar container
    safe_uuid = re.sub(r'[^a-zA-Z0-9]', '', uuid)[:12]
    container_name = f"memprocfs_{safe_uuid}"

    # Clean up any stale container with same name
    cleanup_container(container_name)

    try:
        client = docker.from_env()

        # Detect our own network to connect the sidecar to
        try:
            api_container = client.containers.get('multivol-api')
            api_networks = list(api_container.attrs['NetworkSettings']['Networks'].keys())
            network_name = api_networks[0] if api_networks else 'bridge'
        except:
            network_name = 'bridge'

        # Resolve host path for the dump file directory
        dump_dir = os.path.dirname(dump_path)
        dump_filename = os.path.basename(dump_path)
        host_dump_dir = resolve_host_path(dump_dir)

        container = client.containers.run(
            image=MEMPROCFS_IMAGE,
            name=container_name,
            detach=True,
            network=network_name,  # Same network as API for Docker DNS
            volumes={
                host_dump_dir: {'bind': '/src', 'mode': 'ro'},
            },
            environment={
                'DUMP_PATH': f'/src/{dump_filename}',
                'AUTO_INIT': 'true'
            },
            remove=False  # We manage lifecycle ourselves
        )

        with sessions_lock:
            active_sessions[uuid] = {
                'container_name': container_name,
                'started_at': time.time()
            }

        # Wait for sidecar to become healthy
        def wait_and_update_status():
            """Wait for sidecar health, then mark module as ready."""
            max_wait = 500
            start = time.time()
            sidecar_url = f"http://{container_name}:5002"

            while time.time() - start < max_wait:
                try:
                    resp = http_requests.get(f"{sidecar_url}/health", timeout=3)
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get('vmm_active'):
                            # VMM is ready
                            conn2 = get_db_connection()
                            c2 = conn2.cursor()
                            c2.execute(
                                "UPDATE scan_module_status SET status = 'COMPLETED', updated_at = ? WHERE scan_id = ? AND module = ?",
                                (time.time(), uuid, MODULE_NAME)
                            )
                            conn2.commit()
                            conn2.close()
                            print(f"[+] MemProcFS sidecar ready for {uuid}", flush=True)
                            return
                except:
                    pass
                time.sleep(3)

            print(f"[-] MemProcFS sidecar timeout for {uuid}", flush=True)
            # Mark as failed
            conn2 = get_db_connection()
            c2 = conn2.cursor()
            c2.execute(
                "UPDATE scan_module_status SET status = 'FAILED', error_message = 'Sidecar initialization timeout', updated_at = ? WHERE scan_id = ? AND module = ?",
                (time.time(), uuid, MODULE_NAME)
            )
            conn2.commit()
            conn2.close()

        thread = threading.Thread(target=wait_and_update_status, daemon=True)
        thread.start()

        return jsonify({
            "status": "starting",
            "container": container_name
        })

    except docker.errors.ImageNotFound:
        return jsonify({
            "error": f"MemProcFS image '{MEMPROCFS_IMAGE}' not found. Build it first: docker build -t {MEMPROCFS_IMAGE} ./Dockerfiles/memprocfs/"
        }), 500
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Failed to start sidecar: {str(e)}"}), 500


@memprocfs_bp.route('/memprocfs/<uuid>/files', methods=['GET'])
def get_memprocfs_files(uuid):
    """
    Get file listing from the MemProcFS sidecar.
    Supports pagination: ?limit=500&offset=0&search=
    Caches the FULL results in scan_results, serves paginated slices.
    """
    limit = request.args.get('limit', 500, type=int)
    offset = request.args.get('offset', 0, type=int)
    search = request.args.get('search', '', type=str).strip().lower()

    # Try to get cached full listing
    all_files = None
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT content FROM scan_results WHERE scan_id = ? AND module = ?", (uuid, MODULE_NAME))
    cached = c.fetchone()

    if cached:
        conn.close()
        try:
            all_files = json.loads(cached['content'])
        except:
            all_files = None

    if all_files is None:
        conn.close()
        # Fetch from sidecar
        sidecar_url = get_sidecar_url(uuid)
        if not sidecar_url:
            return jsonify({"error": "MemProcFS session not active. Start it first."}), 400

        try:
            resp = http_requests.get(f"{sidecar_url}/list", timeout=300)
            if resp.status_code != 200:
                return jsonify(resp.json()), resp.status_code

            all_files = resp.json()

            # Cache full results in DB
            try:
                conn = get_db_connection()
                c = conn.cursor()
                c.execute("SELECT id FROM scan_results WHERE scan_id = ? AND module = ?", (uuid, MODULE_NAME))
                if not c.fetchone():
                    c.execute(
                        "INSERT INTO scan_results (scan_id, module, content, created_at) VALUES (?, ?, ?, ?)",
                        (uuid, MODULE_NAME, json.dumps(all_files), time.time())
                    )
                conn.commit()
                conn.close()
            except Exception as e:
                print(f"[WARN] Failed to cache MemProcFS results: {e}")

        except http_requests.exceptions.ConnectionError:
            return jsonify({"error": "MemProcFS sidecar is not reachable. It may still be initializing."}), 503
        except http_requests.exceptions.Timeout:
            return jsonify({"error": "MemProcFS file listing timed out (>5 min)"}), 504
        except Exception as e:
            return jsonify({"error": f"Failed to fetch files: {str(e)}"}), 500

    # Apply search filter
    if search:
        all_files = [f for f in all_files if search in f.get('Name', '').lower()]

    total = len(all_files)

    # Paginate
    if limit > 0:
        page_files = all_files[offset:offset + limit]
    else:
        page_files = all_files

    return jsonify({
        "results": page_files,
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": (offset + limit) < total if limit > 0 else False
    })


@memprocfs_bp.route('/memprocfs/<uuid>/download', methods=['GET'])
def download_memprocfs_file(uuid):
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
            except:
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
def stop_memprocfs(uuid):
    """Stop and remove the MemProcFS sidecar container."""
    with sessions_lock:
        session = active_sessions.pop(uuid, None)

    if not session:
        return jsonify({"status": "not_running"})

    cleanup_container(session['container_name'])
    return jsonify({"status": "stopped"})


@memprocfs_bp.route('/memprocfs/<uuid>/status', methods=['GET'])
def memprocfs_status(uuid):
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
    except:
        pass

    return jsonify({"active": False})
