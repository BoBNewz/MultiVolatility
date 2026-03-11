import os
import sqlite3
import time
import shutil
import logging
from flask import Blueprint, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from multivol.api_server.config import UPLOAD_FOLDER, STORAGE_DIR, BASE_DIR
from multivol.api_server.utils import get_file_hash
from multivol.api_server.database import get_db_connection

files_bp = Blueprint('files_bp', __name__)

@files_bp.route('/upload', methods=['POST'])
def upload_file():
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
            logging.error(f"Failed to save file: {e}")
            return jsonify({"error": str(e)}), 500

@files_bp.route('/symbols', methods=['GET'])
def list_symbols():
    symbols_dir = os.path.join(BASE_DIR, 'volatility3_symbols')
    os.makedirs(symbols_dir, exist_ok=True)
    symbols = []
    for root, dirs, files in os.walk(symbols_dir):
        for file in files:
            rel_path = os.path.relpath(os.path.join(root, file), symbols_dir)
            symbols.append(rel_path)
    return jsonify(symbols)

@files_bp.route('/symbols', methods=['POST'])
def upload_symbol():
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
def delete_symbol():
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

@files_bp.route('/evidences', methods=['GET'])
def list_evidences():
    # Helper to calculate size recursively
    def get_dir_size(start_path):
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(start_path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                total_size += os.path.getsize(fp)
        return total_size

    try:
        items = os.listdir(STORAGE_DIR)
        # Robustly filter system files immediately
        items = [i for i in items if not (i.startswith("scans.db") or i.endswith(".sha256"))]
    except FileNotFoundError:
        logging.error(f"Storage dir not found: {STORAGE_DIR}")
        items = []

    # Pre-load Case Name map from DB
    case_map = {} # filename -> case name
    try:
        conn = get_db_connection()
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT name, dump_path FROM scans ORDER BY created_at ASC")
        rows = c.fetchall()
        for r in rows:
            if r['name'] and r['dump_path']:
                fname = os.path.basename(r['dump_path'])
                case_map[fname] = r['name']
        conn.close()
    except Exception:
        logging.warning("Failed to load case names from DB for evidence listing.", exc_info=True)

    evidences = []
    
    # First pass: Identify extracted folders
    processed_dumps = set()

    for item in items:
        # Filter out system files
        if item.startswith("scans.db") or item.endswith(".sha256"):
            continue

        path = os.path.join(STORAGE_DIR, item)
        if os.path.isdir(path) and item.endswith("_extracted"):
             # This is an extracted folder
             dump_base = item[:-10] # remove _extracted
             files = []
             try:
                  subitems = os.listdir(path)
                  for sub in subitems:
                      if sub.endswith('.sha256'):
                          continue
                      
                      subpath = os.path.join(path, sub)
                      if os.path.isfile(subpath):
                         files.append({
                             "id": os.path.join(item, sub), # Relative path ID for download
                             "name": sub,
                             "size": os.path.getsize(subpath),
                             "type": "Extracted File"
                         })
             except Exception as e:
                 logging.error(f"Error reading subdir {path}: {e}")
            
             # Resolve Source Dump from DB using Folder Name matches
             source_dump = "Unknown Source"
             # 1. Check if dump_base matches a Case Name (Case Name Extraction)
             # If so, source is the dump file associated with that case
             # 2. Check if dump_base matches a Filename (Legacy Extraction)
             
             # Case Name match attempt
             matched_case_name = dump_base
             try:
                 conn = get_db_connection()
                 conn.row_factory = sqlite3.Row
                 c = conn.cursor()
                 c.execute("SELECT dump_path FROM scans WHERE name = ? ORDER BY created_at DESC LIMIT 1", (dump_base,))
                 row = c.fetchone()
                 if row:
                     source_dump = os.path.basename(row['dump_path'])
                 else:
                     source_dump = dump_base
                 conn.close()
             except Exception:
                 logging.warning("Failed to resolve source dump from DB; falling back to folder name.", exc_info=True)
                 source_dump = dump_base

             # If source dump exists in storage, add it to children list as requested
             if source_dump and source_dump != "Unknown Source":
                 dump_path = os.path.join(STORAGE_DIR, source_dump)
                 if os.path.exists(dump_path):
                     processed_dumps.add(source_dump)
                     files.insert(0, {
                         "id": source_dump, # Relative path (just filename)
                         "name": source_dump,
                         "size": os.path.getsize(dump_path),
                         "type": "Memory Dump",
                         "is_source": True
                     })

             evidences.append({
                 "id": item,
                 "name": matched_case_name, 
                 "type": "Evidence Group",
                 "size": get_dir_size(path),
                 "hash": source_dump, 
                 "source_id": source_dump if os.path.exists(os.path.join(STORAGE_DIR, source_dump)) else None, 
                 "uploaded": "Extracted group",
                 "children": files
             })
             
    # Second pass: List main dumps and attach extracted files
    for item in items:
        path = os.path.join(STORAGE_DIR, item)
        if os.path.isfile(path) and not item.endswith('.sha256'):
            # It's a dump file (or other uploaded file)
            # Skip if it's already included in an evidence group
            if item in processed_dumps:
                continue

            # Resolve Display Name (Case Name)
            display_name = case_map.get(item, "Unassigned Evidence")
            
            # WRAP IN GROUP to ensure Folder Style
            child_file = {
                "id": item,
                "name": item,
                "size": os.path.getsize(path),
                "type": "Memory Dump",
                "hash": get_file_hash(path) if os.path.exists(path) else None,
                "uploaded": time.strftime('%Y-%m-%d', time.localtime(os.path.getmtime(path))),
                "is_source": True
            }
            
            evidences.append({
                "id": f"group_{item}", # Virtual ID for the group
                "name": display_name,
                "size": os.path.getsize(path),
                "type": "Evidence Group",
                "hash": item, 
                "source_id": item,
                "uploaded": time.strftime('%Y-%m-%d', time.localtime(os.path.getmtime(path))),
                "children": [child_file] 
            })
            
    return jsonify(evidences)

@files_bp.route('/evidence/<filename>', methods=['DELETE'])
def delete_evidence(filename):
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
            logging.error(f"Failed to delete {path}: {e}")
            return jsonify({"error": str(e)}), 500
    return jsonify({"error": "File not found"}), 404

@files_bp.route('/evidence/<path:filename>/download', methods=['GET'])
def download_evidence(filename):
    # Allow nested paths for extracted files
    # send_from_directory handles traversal attacks (mostly), but we shouldn't use secure_filename on the whole path
    return send_from_directory(STORAGE_DIR, filename, as_attachment=True)
