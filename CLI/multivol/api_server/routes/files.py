import os
import sqlite3
import time
import shutil
import logging
from typing import Any
from flask import Blueprint, request, jsonify, send_from_directory, Response
from werkzeug.utils import secure_filename
from multivol.api_server.config import UPLOAD_FOLDER, STORAGE_DIR, BASE_DIR
from multivol.api_server.utils import get_file_hash
from multivol.api_server.database import get_db_connection

files_bp = Blueprint('files_bp', __name__)

@files_bp.route('/upload', methods=['POST'])
def upload_file() -> Response:
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No chosen file"}), 400
    
    if file:
        filename = secure_filename(file.filename)
        save_path = os.path.join(STORAGE_DIR, filename)
        
        # Check if file already exists to avoid overwrite or just overwrite?
        # For simplicity, we overwrite.
        try:
            logging.debug(f"Saving file to {save_path}")
            file.save(save_path)
            
            # Calculate and cache hash immediately
            logging.debug(f"Calculating hash for {save_path}")
            get_file_hash(save_path)
            
            logging.debug(f"File saved successfully")
            return jsonify({"status": "success", "path": save_path, "server_path": save_path})
        except Exception as e:
            logging.exception("Failed to save file")
            return jsonify({"error": str(e)}), 500

@files_bp.route('/symbols', methods=['GET'])
def list_symbols() -> Response:
    symbols_dir = os.path.join(BASE_DIR, 'volatility3_symbols')
    os.makedirs(symbols_dir, exist_ok=True)
    symbols = []
    for root, dirs, files in os.walk(symbols_dir):
        for file in files:
            rel_path = os.path.relpath(os.path.join(root, file), symbols_dir)
            symbols.append(rel_path)
    return jsonify({"symbols": symbols})

@files_bp.route('/symbols', methods=['POST'])
def upload_symbol() -> Response:
    symbols_dir = os.path.join(BASE_DIR, 'volatility3_symbols')
    os.makedirs(symbols_dir, exist_ok=True)
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files['file']
    path = request.form.get('path', '')  # Allow specifying subdirectories

    filename = secure_filename(file.filename)
    # Prevent traversal
    safe_path = os.path.normpath(os.path.join(symbols_dir, path))
    if not safe_path.startswith(symbols_dir):
        return jsonify({"error": "Invalid path"}), 400

    os.makedirs(safe_path, exist_ok=True)
    file.save(os.path.join(safe_path, filename))
    return jsonify({"status": "success"})

@files_bp.route('/symbols', methods=['DELETE'])
def delete_symbol() -> Response:
    symbols_dir = os.path.join(BASE_DIR, 'volatility3_symbols')
    os.makedirs(symbols_dir, exist_ok=True)
    path = request.args.get('path')
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
            if row['name'] and row['dump_path']:
                case_map[os.path.basename(row['dump_path'])] = row['name']
        conn.close()
    except Exception:
        logging.warning("Failed to load case names from DB for evidence listing.", exc_info=True)
    return case_map


def _resolve_source_dump_name(dump_base: str) -> str:
    """Return the dump filename for a case name (dump_base), or dump_base as fallback."""
    try:
        conn = get_db_connection()
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT dump_path FROM scans WHERE name = ? ORDER BY created_at DESC LIMIT 1", (dump_base,))
        row = c.fetchone()
        conn.close()
        if row:
            return os.path.basename(row['dump_path'])
    except Exception:
        logging.warning("Failed to resolve source dump from DB; falling back to folder name.", exc_info=True)
    return dump_base


def _build_extracted_group(item: str, path: str, processed_dumps: set[str]) -> dict[str, Any]:
    """Build an evidence-group dict for a *_extracted directory."""
    dump_base = item[:-10]  # strip _extracted
    files = []
    try:
        for sub in os.listdir(path):
            if sub.endswith('.sha256'):
                continue
            subpath = os.path.join(path, sub)
            if os.path.isfile(subpath):
                files.append({"id": os.path.join(item, sub), "name": sub,
                               "size": os.path.getsize(subpath), "type": "Extracted File"})
    except Exception as e:
        logging.exception("Error reading subdir %s", path)

    source_dump = _resolve_source_dump_name(dump_base)
    if source_dump and source_dump != "Unknown Source":
        dump_path = os.path.join(STORAGE_DIR, source_dump)
        if os.path.exists(dump_path):
            processed_dumps.add(source_dump)
            files.insert(0, {"id": source_dump, "name": source_dump,
                              "size": os.path.getsize(dump_path),
                              "type": "Memory Dump", "is_source": True})

    return {
        "id": item, "name": dump_base, "type": "Evidence Group",
        "size": _get_dir_size(path), "hash": source_dump,
        "source_id": source_dump if os.path.exists(os.path.join(STORAGE_DIR, source_dump)) else None,
        "uploaded": "Extracted group", "children": files,
    }


def _build_dump_group(item: str, path: str, case_map: dict[str, str]) -> dict[str, Any]:
    """Build an evidence-group dict for a standalone dump file."""
    display_name = case_map.get(item, "Unassigned Evidence")
    child_file = {
        "id": item, "name": item, "size": os.path.getsize(path),
        "type": "Memory Dump",
        "hash": get_file_hash(path),
        "uploaded": time.strftime('%Y-%m-%d', time.localtime(os.path.getmtime(path))),
        "is_source": True,
    }
    return {
        "id": f"group_{item}", "name": display_name,
        "size": os.path.getsize(path), "type": "Evidence Group",
        "hash": item, "source_id": item,
        "uploaded": time.strftime('%Y-%m-%d', time.localtime(os.path.getmtime(path))),
        "children": [child_file],
    }


@files_bp.route('/evidences', methods=['GET'])
def list_evidences() -> Response:
    try:
        all_items = [i for i in os.listdir(STORAGE_DIR)
                     if not (i.startswith("scans.db") or i.endswith(".sha256"))]
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
        if os.path.isfile(path) and not item.endswith('.sha256') and item not in processed_dumps:
            evidences.append(_build_dump_group(item, path, case_map))
            
    return jsonify(evidences)

@files_bp.route('/evidence/<filename>', methods=['DELETE'])
def delete_evidence(filename: str) -> Response:
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
        except Exception as e:
            logging.exception("Failed to delete %s", path)
            return jsonify({"error": str(e)}), 500
    return jsonify({"error": "File not found"}), 404

@files_bp.route('/evidence/<path:filename>/download', methods=['GET'])
def download_evidence(filename: str) -> Response:
    # Allow nested paths for extracted files
    # send_from_directory handles traversal attacks (mostly), but we shouldn't use secure_filename on the whole path
    return send_from_directory(STORAGE_DIR, filename, as_attachment=True)
