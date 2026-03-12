"""
MemProcFS Sidecar Server
========================
Persistent, request-driven Flask API that holds a single live memprocfs.Vmm
handle (1-slot session cache).  Instead of being launched per-scan, this
server runs continuously as a compose service and accepts dump-switching via
POST /load.

Endpoints:
  POST /load         — Load (or hot-swap to) a different dump file
  POST /unload       — Release the current VMM and return to idle
  GET  /health       — Health check and current session info
  GET  /list         — List all recoverable files (NTFS + files sources)
  GET  /read?path=   — Read/download a specific file from the VFS
"""

import os
import queue
import time
import logging
import threading
import concurrent.futures
import memprocfs
from flask import Flask, request, jsonify, Response

# Configurable forensic-ready timeout (seconds). Large dumps (>8 GB) can need 10–20 min.
_FORENSIC_TIMEOUT = int(os.environ.get("MEMPROCFS_FORENSIC_TIMEOUT", "900"))

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)

app = Flask(__name__)

# ──────────────────────────────────────────────
# Authentication
# ──────────────────────────────────────────────
_SIDECAR_TOKEN = os.environ.get("SIDECAR_TOKEN", "")
_PUBLIC_PATHS = {"/health"}


@app.before_request
def check_sidecar_auth():
    """Require SIDECAR_TOKEN on all non-public endpoints when configured."""
    if not _SIDECAR_TOKEN or request.path in _PUBLIC_PATHS:
        return None
    auth = request.headers.get("Authorization", "")
    token = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else ""
    if not token or token != _SIDECAR_TOKEN:
        logging.warning("Unauthorized sidecar request to %s", request.path)
        return jsonify({"error": "Unauthorized"}), 401
    return None


# ──────────────────────────────────────────────
# 1-slot session state (Actor Pattern)
# ──────────────────────────────────────────────
# MemProcFS's C library relies heavily on Thread Local Storage (TLS).
# Creating a VMM on one thread and calling it from another leads to an instant SIGSEGV.
# Solution: A single background worker thread owns the Vmm object and executes all calls.

_task_queue: queue.Queue = queue.Queue()

_session = {
    "dump_path": None,
    "status": "idle",  # idle | loading | ready | error
    "error": None,
    "files_cache": None,
}

# Coalesces concurrent /list requests: only one enumeration runs at a time.
# All other callers wait on this event and read from files_cache when it fires.
_list_lock = threading.Lock()
_list_event: threading.Event | None = None

def _vmm_worker():
    """Single thread that owns the vmm object and executes all requests."""
    global _list_event  # pylint: disable=global-statement
    vmm = None

    while True:
        task = _task_queue.get()
        if task is None:
            if vmm:
                try:
                    vmm.close()
                except Exception:  # pylint: disable=broad-exception-caught
                    pass
            break

        action = task.get("action")

        if action == "load":
            if vmm:
                try:
                    vmm.close()
                except Exception:  # pylint: disable=broad-exception-caught
                    pass
                vmm = None

            dump_path = task["dump_path"]
            _session["dump_path"] = dump_path
            _session["status"] = "loading"
            _session["error"] = None
            _session["files_cache"] = None
            # Reset list coalescing state for the new dump
            with _list_lock:
                if _list_event is not None:
                    _list_event.set()
                _list_event = None
            logging.info("Loading VMM for: %s", dump_path)

            try:
                vmm = memprocfs.Vmm(["-device", dump_path, "-forensic", "1"])
                _session["status"] = "ready"
                logging.info("VMM ready for: %s", dump_path)
            except Exception as e:  # pylint: disable=broad-exception-caught
                logging.error("VMM init failed: %s", e)
                vmm = None
                _session["status"] = "error"
                _session["error"] = str(e)

        elif action == "unload":
            if vmm:
                try:
                    vmm.close()
                except Exception:  # pylint: disable=broad-exception-caught
                    pass
                vmm = None
            _session["dump_path"] = None
            _session["status"] = "idle"
            _session["error"] = None
            _session["files_cache"] = None
            with _list_lock:
                if _list_event is not None:
                    _list_event.set()
                _list_event = None
            logging.info("VMM unloaded, session idle")

        elif action == "list":
            result_box = task["result_box"]
            if not vmm:
                result_box.put(Exception("VMM not loaded"))
            else:
                # A previous queued task may have already populated the cache —
                # avoid re-enumerating 400 k+ entries for every duplicate request.
                if _session["files_cache"] is not None:
                    result_box.put(_session["files_cache"])
                else:
                    try:
                        res = _do_list_files(vmm)
                        _session["files_cache"] = res
                        result_box.put(res)
                    except Exception as e:  # pylint: disable=broad-exception-caught
                        logging.exception("Worker list_files failed")
                        result_box.put(e)
                    finally:
                        # Wake any threads waiting via _list_event
                        with _list_lock:
                            if _list_event is not None:
                                _list_event.set()
                                _list_event = None
                    
        elif action == "read":
            result_box = task["result_box"]
            vfs_path = task["vfs_path"]
            if not vmm:
                result_box.put(Exception("VMM not loaded"))
            else:
                try:
                    parent = os.path.dirname(vfs_path)
                    basename = os.path.basename(vfs_path)
                    info_parent = vmm.vfs.list(parent)
                    if basename not in info_parent:
                        result_box.put(FileNotFoundError(f"File not found in VFS: {vfs_path}"))
                    else:
                        size = info_parent[basename].get("size", 0)
                        if size == 0:
                            result_box.put(ValueError("File has zero size"))
                        else:
                            data = vmm.vfs.read(vfs_path, size, 0)
                            if data is None or _is_null_bytes(data):
                                alt = _try_alternate_source(vmm, vfs_path)
                                if alt:
                                    data = alt
                                else:
                                    raise ValueError("File content is unrecoverable (null bytes)")
                            result_box.put(data)
                except Exception as e:  # pylint: disable=broad-exception-caught
                    logging.exception("Worker read failed")
                    result_box.put(e)

# ──────────────────────────────────────────────
# Flask routes
# ──────────────────────────────────────────────

_worker_thread = None
_worker_lock = threading.Lock()

@app.before_request
def ensure_worker_started():
    global _worker_thread  # pylint: disable=global-statement
    with _worker_lock:
        if _worker_thread is None or not _worker_thread.is_alive():
            _worker_thread = threading.Thread(target=_vmm_worker, daemon=True)
            _worker_thread.start()

@app.route("/load", methods=["POST"])
def load():
    """Dispatch a load command to the worker thread."""
    data = request.get_json(silent=True) or {}
    dump_path = data.get("dump_path", "").strip()

    if not dump_path:
        return jsonify({"error": "dump_path is required"}), 400
    if not os.path.exists(dump_path):
        return jsonify({"error": f"Dump file not found: {dump_path}"}), 404

    if _session["dump_path"] == dump_path:
        if _session["status"] in ("ready", "loading"):
            msg = "already loaded" if _session["status"] == "ready" else "still loading"
            return jsonify({"status": _session["status"], "dump_path": dump_path, "message": msg})

    # Push to worker queue asynchronously
    _task_queue.put({"action": "load", "dump_path": dump_path})
    return jsonify({"status": "loading", "dump_path": dump_path})

@app.route("/unload", methods=["POST"])
def unload():
    """Dispatch an unload command to the worker thread."""
    _task_queue.put({"action": "unload"})
    return jsonify({"status": "idle"})


@app.route("/health", methods=["GET"])
def health():
    return jsonify(
        {
            "status": _session["status"],
            "vmm_active": _session["status"] == "ready",
            "dump_path": _session["dump_path"],
            "files_cached": _session["files_cache"] is not None,
            "error": _session["error"],
            "forensic_timeout": _FORENSIC_TIMEOUT,
        }
    )


@app.route("/list", methods=["GET"])
def list_files_endpoint():
    if _session["status"] != "ready":
        return jsonify({"error": f"VMM not ready (status={_session['status']})"}), 503

    # Fast path: cache is hot
    if _session["files_cache"] is not None:
        return jsonify(_session["files_cache"])

    global _list_event  # pylint: disable=global-statement

    with _list_lock:
        # Re-check inside the lock — another thread may have finished while we waited
        if _session["files_cache"] is not None:
            return jsonify(_session["files_cache"])

        if _list_event is not None:
            # Enumeration already in progress — subscribe to the existing event
            event_to_wait = _list_event
            result_box = None
        else:
            # We are first — create event and dispatch exactly one worker task
            _list_event = threading.Event()
            event_to_wait = None
            result_box = queue.Queue()
            _task_queue.put({"action": "list", "result_box": result_box})

    wait_seconds = _FORENSIC_TIMEOUT * 2

    if event_to_wait is not None:
        # Wait for the in-progress enumeration then return from cache
        if not event_to_wait.wait(timeout=wait_seconds):
            return jsonify({"error": "Worker thread timeout waiting for list"}), 504
        cached = _session.get("files_cache")
        if cached is None:
            return jsonify({"error": "List enumeration failed"}), 500
        return jsonify(cached)

    # We dispatched the task — wait for the result directly
    try:
        res = result_box.get(timeout=wait_seconds)
    except queue.Empty:
        return jsonify({"error": "Worker thread timeout"}), 504

    if isinstance(res, Exception):
        logging.exception("Failed to list files")
        return jsonify({"error": f"Failed to list files: {str(res)}"}), 500

    return jsonify(res)


@app.route("/read", methods=["GET"])
def read_file():
    vfs_path = request.args.get("path", "")
    if not vfs_path:
        return jsonify({"error": "path parameter required"}), 400

    if _session["status"] != "ready":
        return jsonify({"error": "VMM not ready"}), 503

    result_box = queue.Queue()
    _task_queue.put({"action": "read", "vfs_path": vfs_path, "result_box": result_box})

    try:
        data = result_box.get(timeout=120)  # 2 minute read timeout
    except queue.Empty:
        return jsonify({"error": "Worker thread timeout"}), 504

    if isinstance(data, Exception):
        return jsonify({"error": str(data)}), 500 if not isinstance(data, (FileNotFoundError, ValueError)) else 404

    filename = os.path.basename(vfs_path)
    return Response(
        data,
        mimetype="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(data)),
        },
    )


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────


def _is_null_bytes(data: bytes) -> bool:
    return len(data) > 0 and all(b == 0 for b in data)


def _wait_for_forensic(vmm, path: str, timeout: int | None = None) -> bool:
    """Poll until the VFS path is non-empty or timeout expires."""
    if timeout is None:
        timeout = _FORENSIC_TIMEOUT
    start = time.time()
    while time.time() - start < timeout:
        try:
            if len(vmm.vfs.list(path)) > 0:
                return True
        except Exception:  # pylint: disable=broad-exception-caught
            pass
        time.sleep(5)
    return False


def _list_recursive(
    vmm, vfs_root: str, results: list, max_depth: int = 50, depth: int = 0
) -> None:
    """Walk the VFS tree and collect (path, size) pairs.

    No per-file read probe — null-byte detection is deferred to /read time.
    This eliminates thousands of unnecessary VFS reads during the listing phase.
    """
    if depth > max_depth:
        return
    try:
        entries = vmm.vfs.list(vfs_root)
    except Exception:  # pylint: disable=broad-exception-caught
        return
    for name, info in entries.items():
        if name in (".", ".."):
            continue
        vfs_path = f"{vfs_root}/{name}".replace("//", "/")
        if info.get("f_isdir", False):
            _list_recursive(vmm, vfs_path, results, max_depth, depth + 1)
        else:
            results.append((vfs_path, info.get("size", 0)))


def _list_source(vmm, source: str, root: str) -> list[tuple[str, int]]:
    """Wait for one forensic source and return its (vfs_path, size) list."""
    logging.info("Waiting for %s...", root)
    if not _wait_for_forensic(vmm, root):
        logging.warning("Timeout waiting for %s — skipping", root)
        return []
    logging.info("%s is ready, enumerating...", root)
    file_list: list[tuple[str, int]] = []
    _list_recursive(vmm, root, file_list)
    logging.info("%s: found %d entries", source, len(file_list))
    return file_list


def _do_list_files(vmm) -> list:
    """Build the unified file list from NTFS and files forensic sources.

    Both sources are waited on in parallel so a slow NTFS scan does not delay
    the files source (and vice-versa).  NTFS entries take priority; files
    entries fill in gaps where NTFS reported size 0.
    """
    sources = [("ntfs", "/forensic/ntfs"), ("files", "/forensic/files")]

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = {
            pool.submit(_list_source, vmm, src, root): src
            for src, root in sources
        }
        results_by_source: dict[str, list[tuple[str, int]]] = {}
        for fut in concurrent.futures.as_completed(futures):
            src = futures[fut]
            try:
                results_by_source[src] = fut.result()
            except Exception:  # pylint: disable=broad-exception-caught
                logging.exception("Error listing source %s", src)
                results_by_source[src] = []

    raw: dict = {}
    for source in ("ntfs", "files"):  # ntfs first so it wins on conflicts
        for vfs_path, size in results_by_source.get(source, []):
            rel = vfs_path[len(f"/forensic/{source}"):]
            if source == "ntfs":
                parts = rel.split("/", 2)
                rel = ("/" + parts[2]) if len(parts) >= 3 else "/"
            win_path = rel.replace("/", "\\")
            if not win_path.startswith("\\"):
                win_path = "\\" + win_path
            key = win_path.lower()
            if key not in raw or (size > 0 and raw[key]["Size"] == 0):
                raw[key] = {
                    "Name": win_path,
                    "Size": size,
                    "Source": source,
                    "VfsPath": vfs_path,
                    "__children": [],
                }

    results = sorted(raw.values(), key=lambda x: x["Name"].lower())
    logging.info("Listed %d unique files", len(results))
    return results


def _try_alternate_source(vmm, vfs_path: str):
    if "/forensic/ntfs" in vfs_path:
        alt = vfs_path.replace("/forensic/ntfs", "/forensic/files", 1)
    elif "/forensic/files" in vfs_path:
        alt = vfs_path.replace("/forensic/files", "/forensic/ntfs", 1)
    else:
        return None
    try:
        parent = os.path.dirname(alt)
        basename = os.path.basename(alt)
        info = vmm.vfs.list(parent)
        if basename not in info:
            return None
        size = info[basename].get("size", 0)
        if not size:
            return None
        data = vmm.vfs.read(alt, size, 0)
        return data if data and not _is_null_bytes(data) else None
    except Exception:  # pylint: disable=broad-exception-caught
        return None