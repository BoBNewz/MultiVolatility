"""Evidence file upload, symbol management, and file listing routes."""

import io
import os
import sqlite3
import subprocess
import tarfile
import time
import shutil
import logging
import threading
import uuid
import zipfile
from typing import Any
from flask import Blueprint, request, jsonify, send_from_directory, Response
from werkzeug.utils import secure_filename
from multivol.api_server.config import STORAGE_DIR, BASE_DIR
from multivol.api_server.utils import get_file_hash
from multivol.api_server.database import get_db_connection

files_bp = Blueprint("files_bp", __name__)

# In-memory extraction task registry  {task_id: {progress, status, files, error}}
_extraction_tasks: dict[str, dict] = {}
_extraction_lock = threading.Lock()

_ARCHIVE_SUFFIXES = (".zip", ".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz")
# Dump file extensions — used to pick the "primary" file after extraction
_DUMP_EXTENSIONS = (".raw", ".mem", ".vmem", ".dd", ".img", ".bin", ".dmp", ".lime", ".E01", ".e01")


def _is_archive(filename: str) -> bool:
    lower = filename.lower()
    return any(lower.endswith(s) for s in _ARCHIVE_SUFFIXES)


def _safe_extract_path(dest_dir: str, member_path: str) -> str | None:
    """Return the absolute destination path for *member_path* or None if unsafe."""
    member_path = member_path.lstrip("/")
    if ".." in member_path.split(os.sep):
        return None
    full = os.path.realpath(os.path.join(dest_dir, member_path))
    if not full.startswith(os.path.realpath(dest_dir)):
        return None
    return full


def _extract_archive(task_id: str, archive_path: str, dest_dir: str) -> None:
    """Extract *archive_path* into *dest_dir*, updating progress in _extraction_tasks."""
    def _set(progress: int, status: str, files: list[str] | None = None, error: str = "") -> None:
        with _extraction_lock:
            _extraction_tasks[task_id].update(
                {"progress": progress, "status": status, "files": files or [], "error": error}
            )

    try:
        os.makedirs(dest_dir, exist_ok=True)
        lower = archive_path.lower()
        extracted: list[str] = []

        if lower.endswith(".zip"):
            with zipfile.ZipFile(archive_path, "r") as zf:
                members = [m for m in zf.infolist() if not m.is_dir()]
                total = max(sum(m.file_size for m in members), 1)
                done = 0
                CHUNK = 8 * 1024 * 1024
                for member in members:
                    dest = _safe_extract_path(dest_dir, member.filename)
                    if dest is None:
                        logging.warning("Skipping unsafe zip entry: %s", member.filename)
                        continue
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with zf.open(member) as src, open(dest, "wb") as dst:
                        while True:
                            chunk = src.read(CHUNK)
                            if not chunk:
                                break
                            dst.write(chunk)
                            done += len(chunk)
                            _set(int(done / total * 100), "extracting")
                    extracted.append(dest)

        else:  # tar family
            # ── Use native `tar` for ~10× faster extraction (C vs Python) ──
            archive_bytes = os.path.getsize(archive_path)
            total_blocks = archive_bytes // 512 + 1
            # Emit ~200 progress ticks across the extraction
            cp_interval = max(total_blocks // 200, 1)

            # Extract into a temp subdirectory so we can track which files are new
            tmp_dir = os.path.join(dest_dir, f".extract_{task_id}")
            os.makedirs(tmp_dir, exist_ok=True)
            try:
                proc = subprocess.Popen(
                    [
                        "tar", "xf", archive_path,
                        "-C", tmp_dir,
                        "--no-same-owner",
                        f"--checkpoint={cp_interval}",
                        "--checkpoint-action=echo=%u",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                # Read checkpoint ticks from stdout for real-time progress
                for line in proc.stdout:  # type: ignore[union-attr]
                    try:
                        block_num = int(line.strip())
                        pct = min(int(block_num / total_blocks * 100), 99)
                        _set(pct, "extracting")
                    except ValueError:
                        pass
                proc.wait()
                if proc.returncode != 0:
                    stderr_txt = proc.stderr.read() if proc.stderr else ""  # type: ignore[union-attr]
                    raise RuntimeError(f"tar extraction failed (rc={proc.returncode}): {stderr_txt}")
            except FileNotFoundError:
                # `tar` not on PATH — fall back to Python tarfile (slower)
                logging.warning("Native tar not found; falling back to Python tarfile")
                shutil.rmtree(tmp_dir, ignore_errors=True)
                os.makedirs(tmp_dir, exist_ok=True)
                with tarfile.open(archive_path, "r") as tf:
                    for member in tf:
                        if not member.isfile():
                            continue
                        dest = _safe_extract_path(tmp_dir, member.name)
                        if dest is None:
                            continue
                        os.makedirs(os.path.dirname(dest), exist_ok=True)
                        src = tf.extractfile(member)
                        if src is None:
                            continue
                        with open(dest, "wb") as dst:
                            shutil.copyfileobj(src, dst, 8 * 1024 * 1024)
                        try:
                            pos = tf.fileobj.tell()
                            _set(min(int(pos / archive_bytes * 100), 99), "extracting")
                        except (AttributeError, OSError):
                            pass

            # Move extracted files from tmp_dir → dest_dir (same FS = instant rename)
            for root, _, fnames in os.walk(tmp_dir):
                for fname in fnames:
                    src_path = os.path.join(root, fname)
                    rel = os.path.relpath(src_path, tmp_dir)
                    dst_path = os.path.join(dest_dir, rel)
                    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                    shutil.move(src_path, dst_path)
                    extracted.append(dst_path)
            shutil.rmtree(tmp_dir, ignore_errors=True)

        # Delete the archive itself after successful extraction
        try:
            os.remove(archive_path)
        except OSError:
            pass

        # Sort: prefer known dump extensions, then largest file
        def _rank(p: str) -> tuple[int, int]:
            ext = os.path.splitext(p)[1].lower()
            pref = 0 if ext in _DUMP_EXTENSIONS else 1
            size = -os.path.getsize(p) if os.path.exists(p) else 0
            return (pref, size)

        extracted.sort(key=_rank)
        _set(100, "done", extracted)
        logging.info("Extraction complete, %d files: %s", len(extracted), extracted)

    except Exception as exc:  # pylint: disable=broad-except
        logging.exception("Extraction failed for task %s", task_id)
        _set(0, "error", error=str(exc))


def _save_stream(stream, save_path: str) -> None:
    """Write *stream* to *save_path* using the fastest available method.

    Priority:
    1. os.sendfile (Linux zero-copy, data stays in kernel buffers)
    2. shutil.copyfileobj with a 64 MiB buffer (userspace fallback)
    """
    try:
        stream.seek(0)
    except (AttributeError, io.UnsupportedOperation):
        pass

    src_fd: int | None = None
    try:
        src_fd = stream.fileno()
    except (AttributeError, io.UnsupportedOperation):
        pass

    with open(save_path, "wb") as dst:
        if src_fd is not None and hasattr(os, "sendfile"):
            dst_fd = dst.fileno()
            try:
                remaining = os.fstat(src_fd).st_size
                offset = 0
                while remaining > 0:
                    sent = os.sendfile(dst_fd, src_fd, offset, min(remaining, 256 * 1024 * 1024))
                    if sent == 0:
                        break
                    offset += sent
                    remaining -= sent
                return
            except OSError:
                # sendfile failed (cross-device, unsupported FS, etc.) — fall through
                try:
                    stream.seek(0)
                except (AttributeError, io.UnsupportedOperation):
                    pass

        shutil.copyfileobj(stream, dst, 64 * 1024 * 1024)


@files_bp.route("/upload", methods=["POST"])
def upload_file() -> Response:
    """Upload a memory dump or evidence file to the storage directory.

    Archives (.zip, .tar, .tar.gz, .tgz, .tar.bz2, .tar.xz) are saved then
    extracted asynchronously.  The response includes a ``task_id`` which the
    client polls via GET /upload/progress/<task_id>.
    """
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No chosen file"}), 400

    if file:
        filename = secure_filename(file.filename)
        save_path = os.path.join(STORAGE_DIR, filename)

        try:
            logging.debug("Saving upload to %s", save_path)
            _save_stream(file.stream, save_path)
            logging.debug("File saved to %s", save_path)
        except OSError as e:
            logging.exception("Failed to save file")
            return jsonify({"error": str(e)}), 500

        if _is_archive(filename):
            task_id = str(uuid.uuid4())
            extract_dir = STORAGE_DIR  # extract flat into storage root
            with _extraction_lock:
                _extraction_tasks[task_id] = {"progress": 0, "status": "extracting", "files": [], "error": ""}
            threading.Thread(
                target=_extract_archive, args=(task_id, save_path, extract_dir), daemon=True
            ).start()
            return jsonify({"status": "extracting", "task_id": task_id, "path": save_path})

        # Plain file — background hash, immediate success
        threading.Thread(target=get_file_hash, args=(save_path,), daemon=True).start()
        return jsonify({"status": "success", "path": save_path, "server_path": save_path})

    return jsonify({"error": "No file content"}), 400


@files_bp.route("/upload/progress/<task_id>", methods=["GET"])
def upload_progress(task_id: str) -> Response:
    """Return extraction progress for an archive upload task."""
    with _extraction_lock:
        task = _extraction_tasks.get(task_id)
    if task is None:
        return jsonify({"error": "Unknown task"}), 404

    resp = dict(task)
    if task["status"] == "done":
        # Start background hash for each extracted file
        for f in task.get("files", []):
            threading.Thread(target=get_file_hash, args=(f,), daemon=True).start()
        # Clean up completed task after client retrieves it
        with _extraction_lock:
            _extraction_tasks.pop(task_id, None)
    return jsonify(resp)


@files_bp.route("/symbols", methods=["GET"])
def list_symbols() -> Response:
    """List all Volatility 3 symbol files in the symbols directory."""
    symbols_dir = os.path.join(BASE_DIR, "volatility3_symbols")
    os.makedirs(symbols_dir, exist_ok=True)
    symbols = []
    for root, _, files in os.walk(symbols_dir):
        for file in files:
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, symbols_dir)
            try:
                stat = os.stat(full_path)
                size = stat.st_size
                modified = time.strftime("%Y-%m-%d %H:%M", time.localtime(stat.st_mtime))
            except OSError:
                size = 0
                modified = ""
            symbols.append({"name": rel_path, "size": size, "modified": modified})
    symbols.sort(key=lambda s: s["name"].lower())
    return jsonify({"symbols": symbols})


@files_bp.route("/symbols", methods=["POST"])
def upload_symbol() -> Response:
    """Upload a Volatility 3 symbol file, optionally into a subdirectory."""
    symbols_dir = os.path.join(BASE_DIR, "volatility3_symbols")
    os.makedirs(symbols_dir, exist_ok=True)
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    path = request.form.get("path", "")  # Allow specifying subdirectories

    filename = secure_filename(file.filename)
    # Prevent traversal
    safe_path = os.path.normpath(os.path.join(symbols_dir, path))
    if not safe_path.startswith(symbols_dir):
        return jsonify({"error": "Invalid path"}), 400

    os.makedirs(safe_path, exist_ok=True)
    file.save(os.path.join(safe_path, filename))
    return jsonify({"status": "success"})


@files_bp.route("/symbols", methods=["DELETE"])
def delete_symbol() -> Response:
    """Delete a Volatility 3 symbol file or directory."""
    symbols_dir = os.path.join(BASE_DIR, "volatility3_symbols")
    os.makedirs(symbols_dir, exist_ok=True)
    path = request.args.get("path")
    if not path:
        return jsonify({"error": "Path required"}), 400

    # Prevent traversal
    safe_path = os.path.normpath(os.path.join(symbols_dir, path))
    if not safe_path.startswith(symbols_dir):
        return jsonify({"error": "Invalid path"}), 400

    if os.path.exists(safe_path):
        if os.path.isdir(safe_path):
            shutil.rmtree(safe_path)
        else:
            os.remove(safe_path)
        return jsonify({"status": "success"})
    return jsonify({"error": "Not found"}), 404


def _get_dir_size(start_path: str) -> int:
    """Return total byte size of all files under start_path."""
    total = 0
    for dirpath, _, filenames in os.walk(start_path):
        for f in filenames:
            total += os.path.getsize(os.path.join(dirpath, f))
    return total


def _load_case_name_map() -> dict[str, str]:
    """Return a dict mapping dump filename → case name from the scans table."""
    case_map: dict[str, str] = {}
    try:
        conn = get_db_connection()
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT name, dump_path FROM scans ORDER BY created_at ASC")
        for row in c.fetchall():
            if row["name"] and row["dump_path"]:
                case_map[os.path.basename(row["dump_path"])] = row["name"]
        conn.close()
    except Exception:  # pylint: disable=broad-except
        logging.warning("Failed to load case names from DB for evidence listing.", exc_info=True)
    return case_map


def _resolve_source_dump_name(dump_base: str) -> str:
    """Return the dump filename for a case name (dump_base), or dump_base as fallback."""
    try:
        conn = get_db_connection()
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute(
            "SELECT dump_path FROM scans WHERE name = ? ORDER BY created_at DESC LIMIT 1",
            (dump_base,),
        )
        row = c.fetchone()
        conn.close()
        if row:
            return os.path.basename(row["dump_path"])
    except Exception:  # pylint: disable=broad-except
        logging.warning(
            "Failed to resolve source dump from DB; falling back to folder name.",
            exc_info=True,
        )
    return dump_base


def _build_extracted_group(item: str, path: str, processed_dumps: set[str]) -> dict[str, Any]:
    """Build an evidence-group dict for a *_extracted directory."""
    dump_base = item[:-10]  # strip _extracted
    files = []
    try:
        for sub in os.listdir(path):
            if sub.endswith(".sha256"):
                continue
            subpath = os.path.join(path, sub)
            if os.path.isfile(subpath):
                files.append(
                    {
                        "id": os.path.join(item, sub),
                        "name": sub,
                        "size": os.path.getsize(subpath),
                        "type": "Extracted File",
                    }
                )
    except Exception:  # pylint: disable=broad-except
        logging.exception("Error reading subdir %s", path)

    source_dump = _resolve_source_dump_name(dump_base)
    if source_dump and source_dump != "Unknown Source":
        dump_path = os.path.join(STORAGE_DIR, source_dump)
        if os.path.exists(dump_path):
            processed_dumps.add(source_dump)
            files.insert(
                0,
                {
                    "id": source_dump,
                    "name": source_dump,
                    "size": os.path.getsize(dump_path),
                    "type": "Memory Dump",
                    "is_source": True,
                },
            )

    return {
        "id": item,
        "name": dump_base,
        "type": "Evidence Group",
        "size": _get_dir_size(path),
        "hash": source_dump,
        "source_id": source_dump
        if os.path.exists(os.path.join(STORAGE_DIR, source_dump))
        else None,
        "uploaded": "Extracted group",
        "children": files,
    }


def _build_dump_group(item: str, path: str, case_map: dict[str, str]) -> dict[str, Any]:
    """Build an evidence-group dict for a standalone dump file."""
    display_name = case_map.get(item, "Unassigned Evidence")
    child_file = {
        "id": item,
        "name": item,
        "size": os.path.getsize(path),
        "type": "Memory Dump",
        "hash": get_file_hash(path),
        "uploaded": time.strftime("%Y-%m-%d", time.localtime(os.path.getmtime(path))),
        "is_source": True,
    }
    return {
        "id": f"group_{item}",
        "name": display_name,
        "size": os.path.getsize(path),
        "type": "Evidence Group",
        "hash": item,
        "source_id": item,
        "uploaded": time.strftime("%Y-%m-%d", time.localtime(os.path.getmtime(path))),
        "children": [child_file],
    }


@files_bp.route("/evidences", methods=["GET"])
def list_evidences() -> Response:
    """List all evidence files grouped by dump and extracted data."""
    try:
        all_items = [
            i
            for i in os.listdir(STORAGE_DIR)
            if not (i.startswith("scans.db") or i.endswith(".sha256"))
        ]
    except FileNotFoundError:
        logging.error("Storage dir not found: %s", STORAGE_DIR)
        all_items = []

    case_map = _load_case_name_map()
    evidences: list[dict[str, Any]] = []
    processed_dumps: set[str] = set()

    for item in all_items:
        path = os.path.join(STORAGE_DIR, item)
        if os.path.isdir(path) and item.endswith("_extracted"):
            evidences.append(_build_extracted_group(item, path, processed_dumps))

    for item in all_items:
        path = os.path.join(STORAGE_DIR, item)
        if os.path.isfile(path) and not item.endswith(".sha256") and item not in processed_dumps:
            evidences.append(_build_dump_group(item, path, case_map))

    return jsonify(evidences)


@files_bp.route("/evidence/<filename>", methods=["DELETE"])
def delete_evidence(filename: str) -> Response:
    """Delete an evidence file and its associated extracted directory."""
    # Strip virtual group prefix if present
    if filename.startswith("group_"):
        filename = filename[6:]

    filename = secure_filename(filename)
    path = os.path.join(STORAGE_DIR, filename)
    if os.path.exists(path):
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
                # Remove sidecar hash if exists
                if os.path.exists(path + ".sha256"):
                    os.remove(path + ".sha256")

                # Also remove extracted directory (if this was a dump file)
                # Checks for standard <filename>_extracted pattern
                extracted_dir = os.path.join(STORAGE_DIR, f"{filename}_extracted")
                if os.path.exists(extracted_dir):
                    shutil.rmtree(extracted_dir)

            return jsonify({"status": "deleted"})
        except OSError as e:
            logging.exception("Failed to delete %s", path)
            return jsonify({"error": str(e)}), 500
    return jsonify({"error": "File not found"}), 404


@files_bp.route("/evidence/<path:filename>/download", methods=["GET"])
def download_evidence(filename: str) -> Response:
    """Download an evidence file or extracted sub-file by path."""
    # Allow nested paths for extracted files.
    # send_from_directory handles traversal attacks; don't use
    # secure_filename on the whole path.
    return send_from_directory(STORAGE_DIR, filename, as_attachment=True)
