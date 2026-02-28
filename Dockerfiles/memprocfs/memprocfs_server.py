"""
MemProcFS Sidecar Server
========================
A lightweight Flask API that keeps a memprocfs.Vmm handle alive
for instant VFS operations (file listing & extraction).

Endpoints:
  POST /init         — Open VMM handle on a dump file
  GET  /list         — List all recoverable files (NTFS + files sources)
  GET  /read?path=   — Read/download a specific file from the VFS
  GET  /health       — Health check
  POST /shutdown     — Graceful shutdown
"""

import os
import sys
import time
import threading
import signal
from flask import Flask, request, jsonify, Response

app = Flask(__name__)

# ──────────────────────────────────────────────
# Global VMM state
# ──────────────────────────────────────────────
vmm_handle = None
vmm_lock = threading.Lock()
file_cache = None  # Cached file listing


def is_null_bytes(data):
    """Check if data is entirely null bytes."""
    return all(b == 0 for b in data)


def wait_for_forensic(vmm, path, timeout=300, poll_interval=5):
    """Wait for forensic mode to populate the given VFS path."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            entries = vmm.vfs.list(path)
            if len(entries) > 0:
                return True
        except Exception:
            pass
        time.sleep(poll_interval)
    return False


def list_files_recursive(vmm, vfs_root, file_list, max_depth=50, _depth=0):
    """Recursively list all files under a VFS path."""
    if _depth > max_depth:
        return

    try:
        entries = vmm.vfs.list(vfs_root)
    except Exception:
        return

    for name in entries:
        if name in ['.', '..']:
            continue

        vfs_path = f"{vfs_root}/{name}".replace('//', '/')
        info = entries[name]

        if info.get('f_isdir', False):
            list_files_recursive(vmm, vfs_path, file_list, max_depth, _depth + 1)
        else:
            size = info.get('size', 0)
            # Check for null-byte files (unrecoverable)
            if size > 0:
                try:
                    # Only read a small sample to check, not the entire file
                    sample_size = min(size, 4096)
                    data = vmm.vfs.read(vfs_path, sample_size, 0)
                    if data and is_null_bytes(data):
                        size = 0
                except Exception:
                    pass
            file_list.append((vfs_path, size))


def do_list_files(vmm):
    """
    List files from both /forensic/ntfs and /forensic/files,
    deduplicate by Windows path, and return in filescan-compatible format.
    """
    raw_files = {}  # keyed by Windows path to deduplicate

    for source_name, vfs_root in [("ntfs", "/forensic/ntfs"), ("files", "/forensic/files")]:
        print(f"[*] Waiting for {vfs_root}...", flush=True)
        if not wait_for_forensic(vmm, vfs_root, timeout=120):
            print(f"[-] Timeout waiting for {vfs_root}", flush=True)
            continue

        print(f"[*] Listing {vfs_root}...", flush=True)
        file_list = []
        list_files_recursive(vmm, vfs_root, file_list)

        for vfs_path, size in file_list:
            # Convert VFS path to Windows-style path
            # /forensic/ntfs/0/Windows/System32/foo.dll -> \Windows\System32\foo.dll
            # /forensic/files/ROOT/... -> ...
            rel = vfs_path
            if rel.startswith(f"/forensic/{source_name}"):
                rel = rel[len(f"/forensic/{source_name}"):]

            # Strip the volume number from NTFS paths (e.g., /0/Windows -> /Windows)
            if source_name == "ntfs":
                parts = rel.split("/", 2)  # ['', '0', 'Windows/...']
                if len(parts) >= 3:
                    rel = "/" + parts[2]
                elif len(parts) == 2:
                    rel = "/"

            # Convert forward slashes to Windows backslashes
            win_path = rel.replace("/", "\\")
            if not win_path.startswith("\\"):
                win_path = "\\" + win_path

            # Deduplicate: keep the entry with non-zero size, or the first one
            key = win_path.lower()
            if key not in raw_files or (size > 0 and raw_files[key]["Size"] == 0):
                raw_files[key] = {
                    "Name": win_path,
                    "Size": size,
                    "Source": source_name,
                    "VfsPath": vfs_path,
                    "__children": []
                }

    results = list(raw_files.values())
    # Sort by Name
    results.sort(key=lambda x: x["Name"].lower())
    print(f"[+] Listed {len(results)} unique files", flush=True)
    return results


# ──────────────────────────────────────────────
# Flask routes
# ──────────────────────────────────────────────

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "ok",
        "vmm_active": vmm_handle is not None,
        "files_cached": file_cache is not None
    })


@app.route('/init', methods=['POST'])
def init_vmm():
    global vmm_handle, file_cache
    import memprocfs

    data = request.json or {}
    dump_path = data.get('dump_path', os.environ.get('DUMP_PATH', '/src/dump.dmp'))

    if not os.path.exists(dump_path):
        return jsonify({"error": f"Dump file not found: {dump_path}"}), 404

    with vmm_lock:
        if vmm_handle is not None:
            return jsonify({"status": "already_initialized"})

        try:
            print(f"[*] Initializing MemProcFS with forensic mode for {dump_path}...", flush=True)
            vmm_handle = memprocfs.Vmm(['-device', dump_path, '-forensic', '1'])
            file_cache = None  # Reset cache
            print(f"[+] VMM initialized successfully", flush=True)
            return jsonify({"status": "initialized"})
        except Exception as e:
            return jsonify({"error": f"Failed to initialize VMM: {str(e)}"}), 500


@app.route('/list', methods=['GET'])
def list_files_endpoint():
    global file_cache

    if vmm_handle is None:
        return jsonify({"error": "VMM not initialized. Call /init first."}), 400

    # Return cached results if available
    if file_cache is not None:
        return jsonify(file_cache)

    try:
        results = do_list_files(vmm_handle)
        file_cache = results
        return jsonify(results)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Failed to list files: {str(e)}"}), 500


@app.route('/read', methods=['GET'])
def read_file():
    if vmm_handle is None:
        return jsonify({"error": "VMM not initialized"}), 400

    vfs_path = request.args.get('path')
    if not vfs_path:
        return jsonify({"error": "Missing 'path' parameter"}), 400

    # Try reading from the given VFS path directly
    try:
        parent = os.path.dirname(vfs_path)
        basename = os.path.basename(vfs_path)
        info_parent = vmm_handle.vfs.list(parent)
        if basename not in info_parent:
            return jsonify({"error": f"File not found in VFS: {vfs_path}"}), 404

        size = info_parent[basename].get('size', 0)
        if size == 0:
            return jsonify({"error": "File has zero size"}), 404

        data = vmm_handle.vfs.read(vfs_path, size, 0)
        if data is None:
            return jsonify({"error": "Failed to read file"}), 500

        if is_null_bytes(data):
            # Try alternate source
            alt_data = try_alternate_source(vfs_path)
            if alt_data:
                data = alt_data
            else:
                return jsonify({"error": "File content is entirely null bytes (unrecoverable)"}), 404

        filename = os.path.basename(vfs_path)
        return Response(
            data,
            mimetype='application/octet-stream',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Content-Length': str(len(data))
            }
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Read failed: {str(e)}"}), 500


def try_alternate_source(vfs_path):
    """If the primary source returns null bytes, try the alternate source."""
    if vmm_handle is None:
        return None

    # Determine relative path and try the other source
    rel = None
    if "/forensic/ntfs" in vfs_path:
        # Extract relative path from ntfs, try files
        parts = vfs_path.split("/forensic/ntfs", 1)
        if len(parts) == 2:
            rel = parts[1]
            alt_path = f"/forensic/files{rel}"
    elif "/forensic/files" in vfs_path:
        parts = vfs_path.split("/forensic/files", 1)
        if len(parts) == 2:
            rel = parts[1]
            alt_path = f"/forensic/ntfs{rel}"
    else:
        return None

    try:
        parent = os.path.dirname(alt_path)
        basename = os.path.basename(alt_path)
        info_parent = vmm_handle.vfs.list(parent)
        if basename not in info_parent:
            return None
        size = info_parent[basename].get('size', 0)
        if size == 0:
            return None
        data = vmm_handle.vfs.read(alt_path, size, 0)
        if data and not is_null_bytes(data):
            return data
    except Exception:
        pass
    return None


@app.route('/shutdown', methods=['POST'])
def shutdown():
    global vmm_handle, file_cache
    with vmm_lock:
        vmm_handle = None
        file_cache = None
    print("[*] VMM handle released", flush=True)

    # Schedule shutdown after response
    def do_shutdown():
        time.sleep(1)
        os.kill(os.getpid(), signal.SIGTERM)

    threading.Thread(target=do_shutdown, daemon=True).start()
    return jsonify({"status": "shutting_down"})


if __name__ == '__main__':
    # Auto-init if DUMP_PATH is set and AUTO_INIT is true
    dump_path = os.environ.get('DUMP_PATH')
    auto_init = os.environ.get('AUTO_INIT', 'true').lower() == 'true'

    if dump_path and auto_init and os.path.exists(dump_path):
        import memprocfs

        # Initialize VMM in the MAIN thread before Flask starts.
        # memprocfs.Vmm spawns internal C-level threads for forensic mode.
        # Doing this in a Python daemon thread causes SIGSEGV when the
        # daemon thread is cleaned up while C threads are still running.
        try:
            print(f"[*] Auto-initializing VMM for {dump_path}...", flush=True)
            vmm_handle = memprocfs.Vmm(['-device', dump_path, '-forensic', '1'])
            print(f"[+] VMM auto-initialized successfully", flush=True)
        except Exception as e:
            print(f"[-] Auto-init failed: {e}", flush=True)
            sys.exit(1)

    # Use threaded=False to avoid threading conflicts with native VMM code
    app.run(host='0.0.0.0', port=5002, threaded=False)
