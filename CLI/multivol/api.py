from flask import Flask, request, jsonify, abort
import argparse
import os
import docker
import threading
import uuid
import re
import time
import sqlite3
import json
import glob
import hashlib
from werkzeug.utils import secure_filename
from flask import Flask, request, jsonify, abort, send_from_directory, send_file
from flask_cors import CORS
import zipfile
import shutil
import zipfile
import io
import textwrap
import subprocess

try:
    from .multi_volatility2 import multi_volatility2
    from .multi_volatility3 import multi_volatility3
except ImportError:
    from multi_volatility2 import multi_volatility2
    from multi_volatility3 import multi_volatility3

app = Flask(__name__)
# Increase max upload size to 16GB (or appropriate limit for dumps)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 * 1024 
CORS(app, resources={r"/*": {"origins": "*"}}) # Explicitly allow all origins

STORAGE_DIR = os.environ.get("STORAGE_DIR", os.path.join(os.getcwd(), "storage"))
if not os.path.exists(STORAGE_DIR):
    os.makedirs(STORAGE_DIR)


DB_PATH = os.path.join(STORAGE_DIR, "scans.db")
SYMBOLS_DIR = os.path.join(os.getcwd(), "volatility3_symbols")
if not os.path.exists(SYMBOLS_DIR):
    os.makedirs(SYMBOLS_DIR)

def get_db_connection(timeout=30.0):
    """Factory for robust SQLite connections with WAL mode and timeout."""
    conn = sqlite3.connect(DB_PATH, timeout=timeout)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except Exception as e:
        print(f"[WARN] Failed to enable WAL mode: {e}")
    return conn

runner_func = None

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "ok", "timestamp": time.time()})

@app.before_request
def restrict_to_localhost():
    # Allow bypass via environment variable
    if os.environ.get("DISABLE_LOCALHOST_ONLY"):
        return

    # Allow 127.0.0.1 and ::1 (IPv6 localhost)
    allowed_ips = ["127.0.0.1", "::1"]
    
    # Always allow OPTIONS for CORS preflight
    if request.method == 'OPTIONS':
        return
        
    if request.remote_addr not in allowed_ips:
        print(f"[WARNING] Access blocked from: {request.remote_addr}")
        abort(403, description="Access forbidden: Only localhost connections allowed, please set DISABLE_LOCALHOST_ONLY=1 to disable this check.")

def resolve_host_path(path):
    """Resolves a container path to a host path for DooD."""
    host_path = os.environ.get("HOST_PATH")
    if host_path and path.startswith(os.getcwd()):
        return os.path.join(host_path, os.path.relpath(path, os.getcwd()))
    return path

def build_file_tree(base_path, relative_root=""):
    tree = []
    try:
        items = sorted(os.listdir(base_path))
        for item in items:
            full_path = os.path.join(base_path, item)
            rel_path = os.path.join(relative_root, item)
            
            # Skip broken symlinks (symlinks pointing to non-existent targets)
            if os.path.islink(full_path) and not os.path.exists(full_path):
                continue
            
            node = {
                "name": item,
                "path": rel_path
            }
            
            try:
                if os.path.isdir(full_path):
                    node["type"] = "directory"
                    node["children"] = build_file_tree(full_path, rel_path)
                else:
                    node["type"] = "file"
                    node["size"] = os.path.getsize(full_path)
                
                tree.append(node)
            except OSError:
                # Skip files that can't be accessed (permission errors, etc.)
                continue
    except Exception as e:
        print(f"[ERROR] build_file_tree: {e}")
    return tree

def process_recover_fs(output_dir):
    """Checks for a tar file in output_dir (from RecoverFs), extracts it, and generates a JSON tree."""
    print(f"[DEBUG] process_recover_fs scanning directory: {output_dir}")
    if not os.path.exists(output_dir):
        print(f"[ERROR] Output directory does not exist: {output_dir}")
        return

    # List all files for debugging
    all_files = os.listdir(output_dir)
    print(f"[DEBUG] Files in output_dir: {all_files}")

    tar_files = [f for f in glob.glob(os.path.join(output_dir, "*.tar*"))]
    
    if not tar_files:
        print("[DEBUG] No tar files found.")
        return

    target_tar = tar_files[0]
    print(f"[DEBUG] Found tarball: {target_tar}")
    
    extract_dir = os.path.join(output_dir, "recovered_fs")
    json_path = os.path.join(output_dir, "linux.pagecache.RecoverFs_output.json")
    
    # Check if already processed (idempotency)
    # If extract_dir exists and JSON is a small file (tree), skip processing
    if os.path.exists(extract_dir) and os.path.exists(json_path):
        try:
            with open(json_path, 'r') as f:
                data = json.load(f)
                # Check if it's already a tree (has 'path' and 'type' at root level)
                if data and isinstance(data, list) and len(data) > 0:
                    if 'type' in data[0] and data[0].get('type') in ['file', 'directory']:
                        print("[DEBUG] RecoverFs already processed, skipping.")
                        return
        except:
            pass
    
    # Create extraction directory
    if not os.path.exists(extract_dir):
        os.makedirs(extract_dir)
    
    try:
        print(f"[DEBUG] Extracting {target_tar} to {extract_dir}...")
        # Extract tarball
        result = subprocess.run(
            ['tar', '-xzf' if target_tar.endswith('.gz') else '-xf', target_tar, '-C', extract_dir],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=300  # 5 minute timeout for large archives
        )
        print(f"[DEBUG] Extraction completed successfully")
        
        # Verify extraction worked
        extracted_files = os.listdir(extract_dir)
        if not extracted_files:
            print(f"[ERROR] Extraction produced no files")
            return
            
        print(f"[DEBUG] Building file tree from {len(extracted_files)} top-level items...")
        # Build Tree
        tree = build_file_tree(extract_dir)
        
        if not tree:
            print(f"[ERROR] build_file_tree returned empty tree")
            return
        
        print(f"[DEBUG] Tree built with {len(tree)} root nodes. Writing to {json_path}...")
        # Save JSON
        with open(json_path, 'w') as f:
            json.dump(tree, f, indent=2)
        
        print(f"[DEBUG] RecoverFs processing complete. JSON file size: {os.path.getsize(json_path)} bytes")
            
    except subprocess.TimeoutExpired:
        print(f"[ERROR] Extraction timed out after 300 seconds")
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Extraction failed: {e.stderr.decode() if e.stderr else str(e)}")
    except Exception as e:
        print(f"[ERROR] RecoverFs processing failed: {e}")
        import traceback
        traceback.print_exc()


def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS scans
                 (uuid TEXT PRIMARY KEY, status TEXT, mode TEXT, os TEXT, volatility_version TEXT, dump_path TEXT, output_dir TEXT, created_at REAL, error TEXT)''')
    
    # New table for results
    c.execute('''CREATE TABLE IF NOT EXISTS scan_results
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, scan_id TEXT, module TEXT, content TEXT, created_at REAL,
                 FOREIGN KEY(scan_id) REFERENCES scans(uuid))''')
                 
    # Migration: Check if 'name' column exists
    try:
        c.execute("SELECT name FROM scans LIMIT 1")
    except sqlite3.OperationalError:
        print("[INFO] Migrating DB: Adding 'name' column to scans table")
        c.execute("ALTER TABLE scans ADD COLUMN name TEXT")

    # Migration: Check if 'image' column exists (New for file download)
    try:
        c.execute("SELECT image FROM scans LIMIT 1")
    except sqlite3.OperationalError:
        print("[INFO] Migrating DB: Adding 'image' column to scans table")
        c.execute("ALTER TABLE scans ADD COLUMN image TEXT")

    # Migration: Check if 'config_json' column exists (For storing scan options like fetch_symbol)
    try:
        c.execute("SELECT config_json FROM scans LIMIT 1")
    except sqlite3.OperationalError:
        print("[INFO] Migrating DB: Adding 'config_json' column to scans table")
        c.execute("ALTER TABLE scans ADD COLUMN config_json TEXT")

    # Table for async dump tasks
    c.execute('''CREATE TABLE IF NOT EXISTS dump_tasks
                 (task_id TEXT PRIMARY KEY, scan_id TEXT, status TEXT, output_path TEXT, error TEXT, created_at REAL)''')
    
    # Table for module status (Debug/Progress UI)
    c.execute('''CREATE TABLE IF NOT EXISTS scan_module_status
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, scan_id TEXT, module TEXT, status TEXT, error_message TEXT, updated_at REAL,
                 FOREIGN KEY(scan_id) REFERENCES scans(uuid))''')

    conn.commit()
    conn.close()

init_db()

@app.route('/scans/<uuid>', methods=['PUT'])
def rename_scan(uuid):
    data = request.json
    new_name = data.get('name')
    if not new_name:
        return jsonify({"error": "Name is required"}), 400
        
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE scans SET name = ? WHERE uuid = ?", (new_name, uuid))
    conn.commit()
    conn.close()
    return jsonify({"status": "updated"})

@app.route('/scans/<uuid>', methods=['DELETE'])
def delete_scan(uuid):
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # Get output dir to cleanup
    c.execute("SELECT output_dir FROM scans WHERE uuid = ?", (uuid,))
    row = c.fetchone()
    
    if row and row['output_dir'] and os.path.exists(row['output_dir']):
        import shutil
        try:
            shutil.rmtree(row['output_dir'])
        except Exception as e:
            print(f"Error deleting output dir: {e}")
            
    # Delete related records first (foreign key constraints)
    c.execute("DELETE FROM scan_module_status WHERE scan_id = ?", (uuid,))
    c.execute("DELETE FROM scan_results WHERE scan_id = ?", (uuid,))
    c.execute("DELETE FROM scans WHERE uuid = ?", (uuid,))
    conn.commit()
    conn.close()
    return jsonify({"status": "deleted"})

@app.route('/scans/<uuid>/download', methods=['GET'])
def download_scan_zip(uuid):
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT output_dir, name FROM scans WHERE uuid = ?", (uuid,))
    row = c.fetchone()
    conn.close()

    if not row:
        return jsonify({"error": "Scan not found"}), 404
        
    output_dir = row['output_dir']
    scan_name = row['name'] or f"scan_{uuid[:8]}"
    
    if not output_dir:
        return jsonify({"error": "No output directory for this scan"}), 404

    # Ensure absolute path resolution
    if not os.path.isabs(output_dir):
        output_dir = os.path.join(os.getcwd(), output_dir)

    if not os.path.exists(output_dir):
        # Scan might have failed before creating dir, or it was deleted
        return jsonify({"error": "Output directory not found on server"}), 404

    # Create Zip in memory
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        json_files = glob.glob(os.path.join(output_dir, "*_output.json"))
        for f in json_files:
             # Validate JSON
            parsed = clean_and_parse_json(f)
            # Only include if valid JSON and not an error object we created
            if parsed and not (isinstance(parsed, dict) and "error" in parsed and parsed["error"] == "Invalid JSON output"):                 
                 # Add to zip
                 arcname = os.path.basename(f)
                 zf.writestr(arcname, json.dumps(parsed, indent=2))

    memory_file.seek(0)
    return send_file(
        memory_file,
        mimetype='application/zip',
        as_attachment=True,
        download_name=f"{secure_filename(scan_name)}_results.zip"
    )


def clean_and_parse_json(filepath):
    """Helper to parse JSON from Volatility output files, handling errors gracefully."""
    try:
        with open(filepath, 'r') as f:
            content = f.read()
            
        start_index = content.find('[')
        if start_index == -1:
            start_index = content.find('{')
        
        parsed_data = None
        if start_index != -1:
            try:
                json_content = content[start_index:]
                parsed_data = json.loads(json_content)
            except:
                pass # Try fallback
        
        if parsed_data is None:
             lines = content.splitlines()
             if len(lines) > 1:
                 try:
                    parsed_data = json.loads('\n'.join(lines[1:]))
                 except:
                    pass
        
        if parsed_data is not None:
            return parsed_data
            
        # Fallback: Return raw content as error object if not valid JSON
        # This handles Volatility error messages stored in .json files
        return {"error": "Invalid JSON output", "raw_output": content}

    except Exception as e:
        return {"error": f"Error reading file: {str(e)}"}

def ingest_results_to_db(scan_id, output_dir):
    """Reads JSON output files and stores them in the database."""
    print(f"[DEBUG] Ingesting results for {scan_id} from {output_dir}")
    if not os.path.exists(output_dir):
         print(f"[ERROR] Output dir not found: {output_dir}")
         return

    conn = get_db_connection()
    c = conn.cursor()
    
    json_files = glob.glob(os.path.join(output_dir, "*_output.json"))
    for f in json_files:
        try:
            filename = os.path.basename(f)
            if filename.endswith("_output.json"):
                module_name = filename[:-12]
                
                # Check if result already exists to avoid duplicates (idempotency)
                c.execute("SELECT id FROM scan_results WHERE scan_id = ? AND module = ?", (scan_id, module_name))
                if c.fetchone():
                    continue
                
                # Parse or read content
                parsed_data = clean_and_parse_json(f)
                content_str = json.dumps(parsed_data) if parsed_data else "{}"
                if parsed_data and "error" in parsed_data and parsed_data["error"] == "Invalid JSON output":
                     # Store raw output if it was an error
                     content_str = json.dumps(parsed_data)

                c.execute("INSERT INTO scan_results (scan_id, module, content, created_at) VALUES (?, ?, ?, ?)",
                          (scan_id, module_name, content_str, time.time()))

                c.execute(
                    """
                    UPDATE scan_module_status
                    SET status = 'COMPLETED',
                        updated_at = ?
                    WHERE scan_id = ? AND module = ?
                    """,
                    (time.time(), scan_id, module_name)
                )
        except Exception as e:
            print(f"[ERROR] Failed to ingest {f}: {e}")
            
    conn.commit()
    conn.close()
    print(f"[DEBUG] Ingestion complete for {scan_id}")

@app.route('/upload', methods=['POST'])
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
            print(f"[DEBUG] Saving file to {save_path}")
            file.save(save_path)
            
            # Calculate and cache hash immediately
            print(f"[DEBUG] Calculating hash for {save_path}")
            get_file_hash(save_path)
            
            print(f"[DEBUG] File saved successfully")
            return jsonify({"status": "success", "path": save_path, "server_path": save_path})
        except Exception as e:
            print(f"[ERROR] Failed to save file: {e}")
            return jsonify({"error": str(e)}), 500
            return jsonify({"error": str(e)}), 500

@app.route('/symbols', methods=['GET'])
def list_symbols():
    try:
        symbols_files = []
        for root, dirs, files in os.walk(SYMBOLS_DIR):
            for file in files:
                # We want relative path from symbols root
                abs_path = os.path.join(root, file)
                rel_path = os.path.relpath(abs_path, SYMBOLS_DIR)
                symbols_files.append({
                    "name": rel_path,
                    "size": os.path.getsize(abs_path),
                    "modified": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(os.path.getmtime(abs_path)))
                })
        return jsonify({"symbols": symbols_files})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/symbols', methods=['POST'])
def upload_symbol():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No chosen file"}), 400
    
    if file:
        filename = secure_filename(file.filename)
        save_path = os.path.join(SYMBOLS_DIR, filename)
        
        try:
            print(f"[DEBUG] Saving symbol file to {save_path}")
            file.save(save_path)
            
            # If zip, unzip?
            if filename.endswith(".zip"):
                 # Optional: Unzip if user uploads a full pack
                 # For now, let's just save it. User usually uploads .json or .zip for profiles.
                 # Actually, Vol3 can use zip files directly if placed correctly, or we might want to unzip.
                 # Let's verify what the user likely wants. Usually it's a JSON/ISF.
                 pass

            return jsonify({"status": "success", "path": save_path})
        except Exception as e:
             return jsonify({"error": str(e)}), 500

@app.route('/scan', methods=['POST'])
def scan():
    # Check for existing running/pending scans to prevent concurrency
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT uuid FROM scans WHERE status IN ('pending', 'running')")
        existing_scan = c.fetchone()
        conn.close()
        
        if existing_scan:
            return jsonify({"error": "A scan is already in progress. Please wait for it to complete."}), 429
    except Exception as e:
        print(f"[ERROR] Failed to check concurrency: {e}")
        # Fail open or closed? Closed seems safer for stability.
        return jsonify({"error": f"Database error checking concurrency: {e}"}), 500

    data = request.json
    
    # Determine default image based on mode from request
    req_mode = data.get('mode', 'vol3') # Default to vol3 if not specified (though validation requires it)
    default_image = "sp00kyskelet0n/volatility3"
    if req_mode == "vol2":
        default_image = "sp00kyskelet0n/volatility2"

    # Define default arguments matching CLI defaults and requirements
    default_args = {
        "profiles_path": os.path.join(os.getcwd(), "volatility2_profiles"),
        "symbols_path": os.path.join(os.getcwd(), "volatility3_symbols"),
        "cache_path": os.path.join(os.getcwd(), "volatility3_cache"),
        "plugins_dir": os.path.join(os.getcwd(), "volatility3_plugins"),
        "format": "json",
        "commands": None,
        "light": False,
        "full": False,
        "linux": False,
        "windows": False,
        "mode": None,
        "profile": None,
        "processes": None,
        "host_path": os.environ.get("HOST_PATH"), # Added for DooD support via Env
        "debug": True, # Enable command logging for API
        "fetch_symbol": False,
        "custom_symbol": None,
        "image": default_image
    }
    
    args_dict = default_args.copy()
    args_dict.update(data)
    
    # Basic Validation
    # Basic Validation
    if "dump" not in data or "mode" not in data:
         return jsonify({"error": "Missing required fields: dump, mode"}), 400

    # Ensure mutual exclusion for OS flags
    is_linux = bool(data.get("linux"))
    is_windows = bool(data.get("windows"))
    
    if is_linux == is_windows:
        return jsonify({"error": "You must specify either 'linux': true or 'windows': true, but not both or neither."}), 400

    # Default fetch_symbol to True for Linux if not explicitly provided
    if is_linux and "fetch_symbol" not in data:
        args_dict["fetch_symbol"] = True

    args_obj = argparse.Namespace(**args_dict)
    
    scan_id = str(uuid.uuid4())
    args_obj.scan_id = scan_id # Pass scan_id to runner for status updates
    # Construct output directory with UUID
    base_name = f"volatility2_{scan_id}" if args_obj.mode == "vol2" else f"volatility3_{scan_id}"
    # Use absolute path for output_dir to avoid CWD ambiguity and ensure persistence
    final_output_dir = os.path.join(os.getcwd(), "outputs", base_name)
    args_obj.output_dir = final_output_dir
    
    # Ensure directory exists immediately (even if empty) to prevent "No output dir" errors on early failure
    try:
        os.makedirs(final_output_dir, exist_ok=True)
    except Exception as e:
        print(f"[ERROR] Failed to create output dir {final_output_dir}: {e}")
        return jsonify({"error": f"Failed to create output directory: {e}"}), 500

    # Determine OS and Volatility Version for DB
    target_os = "windows" if args_obj.windows else ("linux" if args_obj.linux else "unknown")
    vol_version = args_obj.mode

    # Fix dump path if it's just a filename (assume it's in storage)
    # If it's an absolute path (from previous configs), we trust it?
    # Actually, we should force it to check /storage if it looks like a filename
    if not os.path.isabs(args_obj.dump) and not args_obj.dump.startswith('/'):
         args_obj.dump = os.path.join(STORAGE_DIR, args_obj.dump)

    if not os.path.exists(args_obj.dump):
        return jsonify({"error": f"Dump file not found at {args_obj.dump}"}), 400

    case_name = data.get("name") # Optional custom case name

    # Determine command list for pre-population
    try:
        command_list = []
        if args_obj.mode == "vol2":
            vol_instance = multi_volatility2()
            if args_obj.commands:
                command_list = args_obj.commands.split(",")
            elif args_obj.windows:
                command_list = vol_instance.getCommands("windows.light" if args_obj.light else "windows.full")
            elif args_obj.linux:
                command_list = vol_instance.getCommands("linux.light" if args_obj.light else "linux.full")
        else: # vol3
            vol_instance = multi_volatility3()
            if args_obj.commands:
                 command_list = args_obj.commands.split(",")
            elif args_obj.windows:
                command_list = vol_instance.getCommands("windows.light" if args_obj.light else "windows.full")
            elif args_obj.linux:
                command_list = vol_instance.getCommands("linux.light" if args_obj.light else "linux.full")
        
        # Inject explicit commands into args for CLI
        if command_list:
            args_obj.commands = ",".join(command_list)
            
    except Exception as e:
        print(f"[ERROR] Failed to determine commands: {e}")
        command_list = []

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("INSERT INTO scans (uuid, status, mode, os, volatility_version, dump_path, output_dir, created_at, image, name, config_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
              (scan_id, "pending", "light" if args_obj.light else "full", target_os, vol_version, args_obj.dump, final_output_dir, time.time(), args_obj.image, case_name, json.dumps(data)))
    
    # Pre-populate module status
    if command_list:
        for cmd in command_list:
             c.execute("INSERT INTO scan_module_status (scan_id, module, status, updated_at) VALUES (?, ?, 'PENDING', ?)", (scan_id, cmd, time.time()))

    conn.commit()
    conn.close()

    def background_scan(s_id, args):
        conn = get_db_connection()
        c = conn.cursor()
        
        try:
            c.execute("UPDATE scans SET status = 'running' WHERE uuid = ?", (s_id,))
            conn.commit()
            
            # Execute the runner
            if runner_func:
                runner_func(args)
            
            # Process RecoverFs if present (Extract tarball)
            process_recover_fs(args.output_dir)
            
            # Ingest results to DB
            ingest_results_to_db(s_id, args.output_dir)
            
            # Sweep Logic: Mark any still-pending modules as FAILED
            # This handles cases where containers crashed or produced no output
            c.execute("UPDATE scan_module_status SET status = 'FAILED', error_message = 'Module failed to produce output', updated_at = ? WHERE scan_id = ? AND status IN ('PENDING', 'RUNNING')", (time.time(), s_id))
            conn.commit()
            
            c.execute("UPDATE scans SET status = 'completed' WHERE uuid = ?", (s_id,))
            conn.commit()
        except Exception as e:
            print(f"[ERROR] Scan failed: {e}")
            c.execute("UPDATE scans SET status = 'failed', error = ? WHERE uuid = ?", (str(e), s_id))
            conn.commit()
        finally:
            conn.close()

    thread = threading.Thread(target=background_scan, args=(scan_id, args_obj))
    thread.daemon = True
    thread.start()

    return jsonify({"scan_id": scan_id, "status": "pending", "output_dir": final_output_dir})

@app.route('/status/<scan_id>', methods=['GET'])
def get_status(scan_id):
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM scans WHERE uuid = ?", (scan_id,))
    row = c.fetchone()
    conn.close()
    
    if row:
        return jsonify(dict(row))
    return jsonify({"error": "Scan not found"}), 404

@app.route('/list_images', methods=['GET'])
def list_images():
    try:
        client = docker.from_env()
        images = client.images.list()
        volatility_images = []
        for img in images:
            if img.tags:
                for tag in img.tags:
                    if "volatility" in tag:
                        volatility_images.append(tag)
        return jsonify({"images": list(set(volatility_images))})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/volatility3/plugins', methods=['GET'])
def list_volatility_plugins():
    image = request.args.get('image')
    if not image:
         return jsonify({"error": "Missing 'image' query parameter"}), 400
         
    try:
        script_content = """
            import sys
            # Ensure we can find the package in typical locations
            if "/volatility3" not in sys.path:
                sys.path.insert(0, "/volatility3")
            
            from volatility3 import framework
            import volatility3.plugins
            import json

            try:
                failures = framework.import_files(volatility3.plugins, ignore_errors=True)
                plugins = framework.list_plugins()  # dict: {"windows.pslist.PsList": <class ...>, ...}
                
                output = {
                    "count": len(plugins),
                    "plugins": sorted(list(plugins.keys())),
                    "failures": sorted([str(f) for f in failures]) if failures else []
                }
                print(json.dumps(output))
            except Exception as e:
                import traceback
                print(json.dumps({"error": str(e), "traceback": traceback.format_exc()}))
        """
        script_content = textwrap.dedent(script_content)
        
        # Write script to outputs dir so we can mount it
        output_dir = os.path.join(os.getcwd(), "outputs")
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        script_path = os.path.join(output_dir, "list_plugins_script.py")
        with open(script_path, "w") as f:
            f.write(script_content)
            
        # Resolve host path for Docker volume
        host_script_path = resolve_host_path(script_path)
        
        client = docker.from_env()
        
        # Run container
        print(f"[DEBUG] running list_plugins on image {image}")
        container = client.containers.run(
            image=image,
            entrypoint="python3", 
            command="/list_plugins.py",
            volumes={
                host_script_path: {'bind': '/list_plugins.py', 'mode': 'ro'}
            },
            working_dir="/volatility3", # Set working dir to repo root avoids some path issues
            environment={"PYTHONPATH": "/volatility3"}, # Explicitly set pythonpath
            stderr=True,
            remove=True
        )
        
        # Parse output
        raw_output = container.decode('utf-8')
        try:
            # Output should be mainly JSON
            lines = raw_output.splitlines()
            # It might have stderr logs, so look for JSON
            json_line = None
            for line in reversed(lines):
                if line.strip().startswith('{'):
                    json_line = line
                    break
            
            if json_line:
                data = json.loads(json_line)
                return jsonify(data)
            else:
                 return jsonify({"error": "No JSON output found", "raw": raw_output}), 500
        except:
             return jsonify({"error": "Failed to parse script output", "raw": raw_output}), 500

    except Exception as e:
        print(f"[ERROR] List plugins failed: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/scan/<uuid>/log', methods=['POST'])
def log_scan_module_status(uuid):
    data = request.json
    if not data:
        return jsonify({"error": "Missing JSON body"}), 400
        
    module = data.get('module')
    status = data.get('status')
    error = data.get('error')
    
    if not module or not status:
        return jsonify({"error": "Missing module or status"}), 400

    conn = get_db_connection()
    c = conn.cursor()
    try:
        # Upsert status
        # Check if exists
        c.execute("SELECT 1 FROM scan_module_status WHERE scan_id = ? AND module = ?", (uuid, module))
        exists = c.fetchone()
        
        if exists:
            c.execute("UPDATE scan_module_status SET status = ?, error_message = ?, updated_at = ? WHERE scan_id = ? AND module = ?", 
                      (status, error, time.time(), uuid, module))
        else:
             c.execute("INSERT INTO scan_module_status (scan_id, module, status, error_message, updated_at) VALUES (?, ?, ?, ?, ?)",
                       (uuid, module, status, error, time.time()))
        
        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        print(f"[ERROR] Failed to log status: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/scan/<uuid>/modules', methods=['GET'])
def get_scan_modules_status(uuid):
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    try:
        # Get scan output directory
        c.execute("SELECT output_dir FROM scans WHERE uuid = ?", (uuid,))
        scan_row = c.fetchone()
        output_dir = scan_row['output_dir'] if scan_row else None
        
        # Try to get status from the status table
        c.execute("SELECT module, status, error_message FROM scan_module_status WHERE scan_id = ?", (uuid,))
        rows = c.fetchall()
        
        status_list = []
        docker_client = None
        
        if rows:
            for row in rows:
                mod_dict = dict(row)
                module_name = mod_dict['module']
                
                # For PENDING/RUNNING modules, check Docker container status
                if mod_dict['status'] in ['PENDING', 'RUNNING']:
                    # Predictable container name: vol3_{scan_id[:8]}_{sanitized_module}
                    # Must match CLI: re.sub(r'[^a-zA-Z0-9_.-]', '', command)
                    import re as re_module
                    sanitized_name = re_module.sub(r'[^a-zA-Z0-9_.-]', '', module_name)
                    container_name = f"vol3_{uuid[:8]}_{sanitized_name}"
                    # Debug print if needed: print(f"[DEBUG] Looking for container: {container_name}")
                    
                    try:
                        if docker_client is None:
                            import docker
                            docker_client = docker.from_env()
                        
                        container = docker_client.containers.get(container_name)
                        container_status = container.status  # 'running', 'exited', 'created', etc.
                        
                        if container_status == 'running':
                            mod_dict['status'] = 'RUNNING'
                            c.execute("UPDATE scan_module_status SET status = 'RUNNING', updated_at = ? WHERE scan_id = ? AND module = ?",
                                      (time.time(), uuid, module_name))
                        elif container_status == 'exited':
                            # Container finished - file should be ready now
                            
                            # Special handling for RecoverFs: Detect completion and Process/Extract immediatley
                            if module_name == "linux.pagecache.RecoverFs" and output_dir:
                                 # We check if the tar exists. If so, process it.
                                 # This overwrites the .json with the file tree.
                                 # We use a flag file to prevent re-processing? 
                                 # process_recover_fs is idempotent if we check for existing tree, but better just run it if we are ingesting.
                                 process_recover_fs(output_dir)

                            # Read and ingest JSON
                            if output_dir:
                                output_file = os.path.join(output_dir, f"{module_name}_output.json")
                                if os.path.exists(output_file):
                                    try:
                                        parsed_data = clean_and_parse_json(output_file)
                                        content_str = json.dumps(parsed_data) if parsed_data else "{}"
                                        # Check if result already exists
                                        c.execute("SELECT id FROM scan_results WHERE scan_id = ? AND module = ?", (uuid, module_name))
                                        if not c.fetchone():
                                            c.execute("INSERT INTO scan_results (scan_id, module, content, created_at) VALUES (?, ?, ?, ?)",
                                                      (uuid, module_name, content_str, time.time()))
                                    except Exception as e:
                                        print(f"[ERROR] Failed to ingest {module_name}: {e}")
                            
                            mod_dict['status'] = 'COMPLETED'
                            c.execute("UPDATE scan_module_status SET status = 'COMPLETED', updated_at = ? WHERE scan_id = ? AND module = ?",
                                      (time.time(), uuid, module_name))
                            
                            # Clean up container
                            try:
                                container.remove()
                            except Exception as rm_err:
                                print(f"[WARN] Failed to remove container {container_name}: {rm_err}")
                                
                    except Exception as e:
                        # Container not found or docker error - leave status as-is
                        pass
                
                status_list.append(mod_dict)
            
            conn.commit()
        else:
            # Fallback: check scan_results table for completed modules
            c.execute("SELECT module FROM scan_results WHERE scan_id = ?", (uuid,))
            result_rows = c.fetchall()
            for r in result_rows:
                status_list.append({
                    "module": r['module'], 
                    "status": "COMPLETED", 
                    "error_message": None
                })
        
        # Fallback 2: If status_list is still empty, scan output_dir for JSON files
        if len(status_list) == 0 and output_dir and os.path.isdir(output_dir):
            import glob
            json_files = glob.glob(os.path.join(output_dir, "*_output.json"))
            for jf in json_files:
                basename = os.path.basename(jf)
                # Extract module name from filename: "linux.pstree.PsTree_output.json" -> "linux.pstree.PsTree"
                if basename.endswith("_output.json"):
                    module_name = basename[:-len("_output.json")]
                    status_list.append({
                        "module": module_name,
                        "status": "COMPLETED",
                        "error_message": None
                    })

        # Check for strings output file and inject into list if present
        if output_dir:
            strings_path = os.path.join(output_dir, "strings_output.txt")
            if os.path.exists(strings_path):
                # Avoid duplicates
                if not any(m['module'] == 'strings' for m in status_list):
                    status_list.append({"module": "strings", "status": "COMPLETED"})

        return jsonify(status_list)

    except Exception as e:
        print(f"[ERROR] Fetching module status: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


@app.route('/results/<uuid>', methods=['GET'])
def get_scan_results(uuid):
    module_param = request.args.get('module')
    if not module_param:
        return jsonify({"error": "Missing 'module' query parameter"}), 400
        
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # RecoverFs module: ALWAYS read from filesystem (not DB) because the filesystem
    # has the processed tree structure with name/path/type fields, while DB has raw Volatility output
    if module_param != 'linux.pagecache.RecoverFs':
        # try DB first for other modules
        c.execute("SELECT content FROM scan_results WHERE scan_id = ? AND module = ?", (uuid, module_param))
        row = c.fetchone()
        if row:
            conn.close()
            try:
                return jsonify(json.loads(row['content']))
            except:
                return jsonify({"error": "Failed to parse stored content", "raw": row['content']}), 500


    # Fallback to filesystem
    c.execute("SELECT output_dir FROM scans WHERE uuid = ?", (uuid,))
    scan = c.fetchone()
    conn.close()
    
    if not scan:
         return jsonify({"error": "Scan not found"}), 404
    
    output_dir = scan['output_dir']
    if not output_dir or not os.path.exists(output_dir):
         return jsonify({"error": "Output directory not found"}), 404

    if module_param == 'all':
        results = {}
        json_files = glob.glob(os.path.join(output_dir, "*_output.json"))
        for f in json_files:
            filename = os.path.basename(f)
            if filename.endswith("_output.json"):
                module_name = filename[:-12]
                parsed_data = clean_and_parse_json(f)
                if parsed_data is not None:
                    results[module_name] = parsed_data
        return jsonify(results)
    else:
        target_file = os.path.join(output_dir, f"{module_param}_output.json")
        if not os.path.exists(target_file):
            return jsonify({"error": f"Module {module_param} output not found"}), 404
            
        parsed_data = clean_and_parse_json(target_file)
        if parsed_data is None:
             return jsonify({"error": f"Failed to parse JSON for {module_param}"}), 500
             
        return jsonify(parsed_data)

@app.route('/scans', methods=['GET'])
def list_scans():
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM scans ORDER BY created_at DESC")
    rows = c.fetchall()
    
    scans_list = []
    for row in rows:
        scan_dict = dict(row)
        scan_uuid = scan_dict['uuid']
        
        # Count valid modules from DB (excluding known errors)
        # We explicitly check for our known error string to filter out failed modules
        c.execute("SELECT COUNT(*) FROM scan_results WHERE scan_id = ? AND content NOT LIKE '%\"error\": \"Invalid JSON output\"%'", (scan_uuid,))
        db_count = c.fetchone()[0]
        
        scan_dict['modules'] = db_count
        
        # Override status to 'failed' if technically completed but 0 valid modules
        if scan_dict['status'] == 'completed' and db_count == 0:
            scan_dict['status'] = 'failed'
            scan_dict['error'] = 'No valid JSON results parsed'

        # Fallback to filesystem count (only if DB count is 0 and we want to be sure? 
        # Actually DB is source of truth for results now. If ingest failed, it's failed.)
        
        scan_dict['findings'] = 0 
        scans_list.append(scan_dict)


    
    conn.close()
    return jsonify(scans_list)

@app.route('/scans/<uuid>/execute', methods=['POST'])
def execute_plugin(uuid):
    data = request.json
    module = data.get('module')
    if not module:
        return jsonify({"error": "Missing 'module' parameter"}), 400

    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM scans WHERE uuid = ?", (uuid,))
    scan = c.fetchone()
    conn.close()

    if not scan:
        return jsonify({"error": "Scan not found"}), 404

    # Reconstruct arguments for runner
    # We use default paths as they are standard in the container
    default_args = {
        "profiles_path": os.path.join(os.getcwd(), "volatility2_profiles"),
        "symbols_path": os.path.join(os.getcwd(), "volatility3_symbols"),
        "cache_path": os.path.join(os.getcwd(), "volatility3_cache"),
        "plugins_dir": os.path.join(os.getcwd(), "volatility3_plugins"),
        "format": "json",
        "commands": module, # Execute only this module
        "light": False,
        "full": False,
        "linux": False,
        "windows": False,
        "mode": scan['volatility_version'], # vol2 or vol3
        "profile": None, # TODO: Store profile in DB for vol2?
        "processes": 1, 
        "host_path": os.environ.get("HOST_PATH"),
        "debug": True,
        "fetch_symbol": False,
        "custom_symbol": None, # TODO: Store custom symbol in DB?
        "dump": scan['dump_path'],
        "image": scan['image'],
        "output_dir": scan['output_dir']
    }

    # Set OS flags based on DB
    if scan['os'] == 'linux':
        default_args['linux'] = True
        default_args['fetch_symbol'] = True # Default for Linux
    elif scan['os'] == 'windows':
        default_args['windows'] = True
    
    args_obj = argparse.Namespace(**default_args)
    args_obj.scan_id = uuid # Add scan_id for tracking

    def background_single_run(s_id, args):
        try:
             # Just run it
             if runner_func:
                 print(f"[DEBUG] Executing manual plugin {args.commands} on {s_id}")
                 runner_func(args)
                 
             # Ingest
             ingest_results_to_db(s_id, args.output_dir)
        except Exception as e:
            print(f"[ERROR] Manual plugin execution failed: {e}")

    # Insert into scan_module_status so UI tracks it
    try:
        conn = get_db_connection()
        c = conn.cursor()
        # Check if exists, update if so, else insert
        c.execute("SELECT id FROM scan_module_status WHERE scan_id = ? AND module = ?", (uuid, module))
        if c.fetchone():
            c.execute("UPDATE scan_module_status SET status = 'RUNNING', updated_at = ? WHERE scan_id = ? AND module = ?", (time.time(), uuid, module))
        else:
            c.execute("INSERT INTO scan_module_status (scan_id, module, status, updated_at) VALUES (?, ?, ?, ?)",
                      (uuid, module, 'RUNNING', time.time()))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[ERROR] Failed to update module status for {module}: {e}")

    thread = threading.Thread(target=background_single_run, args=(uuid, args_obj))
    thread.daemon = True
    thread.start()

    return jsonify({"status": "started", "module": module})

@app.route('/stats', methods=['GET'])
def get_stats():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM scans")
    total_cases = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM scans WHERE status='running'")
    running_cases = c.fetchone()[0]
    
    c.execute("SELECT COUNT(DISTINCT dump_path) FROM scans")
    total_evidences = c.fetchone()[0]
    
    conn.close()
    
    # Count symbols
    symbols_path = os.path.join(os.getcwd(), "volatility3_symbols")
    total_symbols = 0
    if os.path.exists(symbols_path):
        for root, dirs, files in os.walk(symbols_path):
            total_symbols += len(files)

    return jsonify({
        "total_cases": total_cases,
        "processing": running_cases,
        "total_evidences": total_evidences,
        "total_symbols": total_symbols
    })

@app.route('/evidences', methods=['GET'])
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

        print(f"[DEBUG] list_evidences found {len(items)} items in {STORAGE_DIR}")
        print(f"[DEBUG] Items: {items}")
    except FileNotFoundError:
        print(f"[ERROR] Storage dir not found: {STORAGE_DIR}")
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
    except:
        pass

    evidences = []
    
    # First pass: Identify extracted folders
    processed_dumps = set()
    extracted_map = {} # Unused but keeping for minimization if referenced elsewhere, though we will ignore it.

    
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
                 print(f"Error reading subdir {path}: {e}")
            
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
             except:
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
                "hash": get_file_hash(path),
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

def calculate_sha256(filepath):
    """Calculates SHA-256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def get_file_hash(filepath):
    """Gets cached hash or calculates it."""
    hash_file = filepath + ".sha256"
    if os.path.exists(hash_file):
        try:
            with open(hash_file, 'r') as f:
                return f.read().strip()
        except:
            pass
    
    # Calculate and cache
    try:
        file_hash = calculate_sha256(filepath)
        with open(hash_file, 'w') as f:
            f.write(file_hash)
        return file_hash
    except Exception as e:
        print(f"[ERROR] Failed to calc hash for {filepath}: {e}")
        return "Error"



@app.route('/evidence/<filename>', methods=['DELETE'])
def delete_evidence(filename):
    # Strip virtual group prefix if present
    if filename.startswith("group_"):
        filename = filename[6:]
        
    filename = secure_filename(filename)
    path = os.path.join(STORAGE_DIR, filename)
    if os.path.exists(path):
        import shutil
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
            print(f"[ERROR] Failed to delete {path}: {e}")
            return jsonify({"error": str(e)}), 500
    return jsonify({"error": "File not found"}), 404

@app.route('/evidence/<path:filename>/download', methods=['GET'])
def download_evidence(filename):
    # Allow nested paths for extracted files
    # send_from_directory handles traversal attacks (mostly), but we shouldn't use secure_filename on the whole path
    return send_from_directory(STORAGE_DIR, filename, as_attachment=True)


def cleanup_timeouts():
    """Marks scans running for > 1 hour as failed (timeout)."""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        one_hour_ago = time.time() - 3600
        
        # Find tasks that are 'running' and older than 1 hour
        c.execute("SELECT uuid FROM scans WHERE status='running' AND created_at < ?", (one_hour_ago,))
        stale_scans = c.fetchall()
        
        if stale_scans:
            print(f"Cleaning up {len(stale_scans)} stale scans...")
            c.execute("UPDATE scans SET status='failed', error='Timeout (>1h)' WHERE status='running' AND created_at < ?", (one_hour_ago,))
            conn.commit()
            
        conn.close()
    except Exception as e:
        print(f"Error cleaning up timeouts: {e}")


# In-memory dictionary to store dump task statuses
# NOTE: This is a temporary solution for the provided diff.
# A more robust solution would persist this in the database.
dump_tasks = {}

def background_dump_task(task_id, scan, virt_addr, image_tag, file_path=None):
    """
    Executes a Volatility3 dump command.
    Windows: uses windows.dumpfiles.DumpFiles --virtaddr
    Linux: uses linux.pagecache.Files --find <path> --dump
    """
    print(f"[{task_id}] DEBUG: Starting background dump task for scan: {scan['uuid']}")
    dump_tasks[task_id] = {'status': 'running'}
    
    try:
        # We need the memory dump file name on host
        # The 'scan' row has 'filepath'. 
        # But wait, that filepath is the UPLOADED path (e.g. /app/storage/uploads/...)
        # We need the filename to point to /dump_dir inside container.
        uploaded_path = scan['dump_path'] # Changed from 'filepath' to 'dump_path' to match original scan structure
        
        print(f"[{task_id}] DEBUG: Raw uploaded_path: {uploaded_path}")
        if not os.path.isabs(uploaded_path) and not uploaded_path.startswith('/'):
            uploaded_path = os.path.join(STORAGE_DIR, uploaded_path)
            
        print(f"[{task_id}] DEBUG: Resolved uploaded_path: {uploaded_path}")
        dump_filename = os.path.basename(uploaded_path)

        # Construct basic command
        # Removing -q to see errors/warnings, adding -v for verbose
        cmd = ["vol", "-v", "-f", f"/dump_dir/{dump_filename}", "-o", "/output"]

        # Parse Config
        config = {}
        # scan is sqlite3.Row, supports key access
        if 'config_json' in scan.keys() and scan['config_json']:
             try:
                 config = json.loads(scan['config_json'])
             except:
                 print(f"[{task_id}] WARN: Failed to parse config_json")

        # ISF Handling (Must be generally available or before plugin)
        # multi_volatility3.py puts it before command.
        if scan['os'] == 'linux' and config.get('fetch_symbol'):
             print(f"[{task_id}] DEBUG: Enabling remote ISF URL based on scan config")
             cmd.extend(["--remote-isf-url", "https://github.com/Abyss-W4tcher/volatility3-symbols/raw/master/banners/banners.json"])
             
        # Explicitly set symbols path if not using ISF? 
        # Actually vol defaults to checking standard paths, and we mount /symbols.
        # But we should probably add -s /symbols for clarity/correctness if not using ISF?
        # Actually, multi_volatility3 DOES add -s /symbols ALWAYS.
        cmd.extend(["-s", "/symbols"])


        # Determine plugin based on OS
        print(f"[{task_id}] DEBUG: Scan OS: {scan['os']}")
        if scan['os'] == 'linux':
             # Linux dump logic: vol -f ... linux.pagecache.Files --find {path_name} --dump
             if not file_path:
                 raise Exception("File Path is required for Linux dumps")
             
             print(f"[{task_id}] DEBUG: Linux Dump - FilePath: {file_path}")
             cmd.append("linux.pagecache.Files")
             cmd.append("--find")
             cmd.append(file_path)
             cmd.append("--dump")
             
             # Symbols / ISF Handling
             # We assume if it's Linux we might need the ISF URL if local symbols aren't enough.
             # Per user request: "use the /symbols folder ... OR the ISF link".
             # The docker container has /symbols

        else:
            # Windows dump logic (default)
            cmd.append("windows.dumpfiles.DumpFiles")
            
            # Heuristic: If address is small (< 2GB), likely physical offset 
            # (Kernel VAs are usually > 0x80000000 on 32-bit and huge on 64-bit)
            # The observed offsets are ~500MB which match the physical file size.
            addr_val = int(virt_addr)
            if addr_val < 0x80000000:
                print(f"[{task_id}] DEBUG: Address {hex(addr_val)} looks physical, using --physaddr")
                cmd.append("--physaddr")
            else:
                print(f"[{task_id}] DEBUG: Address {hex(addr_val)} looks virtual, using --virtaddr")
                cmd.append("--virtaddr")
                
            cmd.append(hex(addr_val))

        print(f"[{task_id}] Running dump command inside container: {cmd}")

        # Run Docker
        # We must mount:
        #   STORAGE_DIR/uploads -> /dump_dir
        #   STORAGE_DIR/<ScanID>_extracted (or temp) -> /output
        #   STORAGE_DIR/symbols -> /symbols
        #   STORAGE_DIR/cache -> /root/.cache/volatility3
        
        # Output dir:
        # We'll create a specific folder for this extraction or just use the common one.
        # Let's use a temp dir for the dump, then move the file.
        case_name = scan['name'] # Changed from 'case_name' to 'name' to match original scan structure
        case_extract_dir = os.path.join(STORAGE_DIR, f"{case_name}_extracted")
        if not os.path.exists(case_extract_dir):
            os.makedirs(case_extract_dir)

        # We'll map the HOST path to /output. 
        # Actually, simpler to map case_extract_dir to /output.
        # BUT, volatility output filenames usually include virtaddr or pid.
        # We want to identify the file we just dumped.
        
        # Let's use a temporary directory for THIS task
        task_out_dir = os.path.join(STORAGE_DIR, f"task_{task_id}")
        if not os.path.exists(task_out_dir):
           os.makedirs(task_out_dir)

        # Retrieve Docker Image
        # If image_tag is provided, use it. Else use default
        # Check if local build?
        # The frontend sends 'image' from caseDetails.
        
        # Prepare Volumes using STORAGE_DIR
        symbols_path = os.path.join(STORAGE_DIR, 'symbols')
        cache_path = os.path.join(STORAGE_DIR, 'cache')
        
        # Ensure directories exist
        os.makedirs(symbols_path, exist_ok=True)
        os.makedirs(cache_path, exist_ok=True)

        # Docker Volumes Mapping
        volumes = {
            resolve_host_path(os.path.dirname(uploaded_path)): {'bind': '/dump_dir', 'mode': 'ro'},
            resolve_host_path(task_out_dir): {'bind': '/output', 'mode': 'rw'},
            resolve_host_path(symbols_path): {'bind': '/symbols', 'mode': 'rw'},
            resolve_host_path(cache_path): {'bind': '/root/.cache/volatility3', 'mode': 'rw'}
        }

        # Consistent naming for debug
        # Format: vol3_dump_<short_scan_uuid>_<task_id>
        # Scan UUID is text, sanitize just in case
        safe_scan_id = re.sub(r'[^a-zA-Z0-9]', '', scan['uuid'])[:8]
        container_name = f"vol3_dump_{safe_scan_id}_{task_id}"

        print(f"[{task_id}] Launching Docker container: {image_tag}")
        print(f"[{task_id}] Container Name: {container_name}")
        print(f"[{task_id}] Command: {cmd}")
        print(f"[{task_id}] Volumes config: {volumes}")
        
        try:
            client = docker.from_env()
            container = client.containers.run(
                image=image_tag,
                name=container_name,
                command=cmd,
                volumes=volumes,
                remove=True,
                detach=False, # Wait for completion
                stderr=True,
                stdout=True
            )
            # Docker returns byte output when detach=False
            output_str = container.decode('utf-8', errors='replace') if container else ""
            print(f"[{task_id}] Docker execution finished. Output bytes: {len(container) if container else 0}")
            print(f"[{task_id}] Full Container Output:\n{output_str}")
        except docker.errors.ImageNotFound:
             print(f"[{task_id}] Pulling image {image_tag}...")
             client.images.pull(image_tag)
             container = client.containers.run(
                image=image_tag,
                name=container_name,
                command=cmd,
                volumes=volumes,
                remove=True,
                detach=False
            )
        except Exception as e:
            print(f"[{task_id}] CRITICAL DOCKER ERROR: {e}")
            raise Exception(f"Docker execution failed: {e}")

        # After run, check files in task_out_dir
        files = os.listdir(task_out_dir)
        print(f"[{task_id}] Checking output directory: {task_out_dir}")
        print(f"[{task_id}] Files in output dir: {files}")
        if not files:
            raise Exception(f"No file extracted by Volatility plugin. Dump command executed but output dir is empty. \nLast container output: {output_str[-500:] if 'output_str' in locals() else 'N/A'}")
        
        # Move files to final destination (case_extract_dir)
        # And maybe rename?
        created_files = []
        for f in files:
            src = os.path.join(task_out_dir, f)
            dst = os.path.join(case_extract_dir, f)
            shutil.move(src, dst)
            created_files.append(f)
            
        # Cleanup
        os.rmdir(task_out_dir)

        # Update DB/Task status
        # Since we use simple dict for now:
        dump_tasks[task_id]['status'] = 'completed'
        dump_tasks[task_id]['output_path'] = f"/evidence/{created_files[0]}/download" # Basic assumption
        print(f"[{task_id}] Task completed successfully. Output: {dump_tasks[task_id]['output_path']}")

        # Ideally, update DB if we were using it for dump_tasks (we only insert PENDING, but never update status in DB in this code?)
        # Ah, the previous code had DB update logic but I removed it/it's not in this snippet.
        # Let's add basic DB update so status persists if backend restarts?
        # For now, memory dict is what endpoint checks.
        
    except Exception as e:
        print(f"[{task_id}] TASK FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        dump_tasks[task_id]['status'] = 'failed'
        dump_tasks[task_id]['error'] = str(e)
    finally:
        # The original code updated the database, but the provided diff removes this.
        # Keeping the database update for consistency with other functions.
        conn = get_db_connection()
        c = conn.cursor()
        if dump_tasks[task_id]['status'] == 'completed':
            output_path = os.path.join(case_extract_dir, created_files[0]) if created_files else None
            c.execute("UPDATE dump_tasks SET status = 'completed', output_path = ? WHERE task_id = ?", (output_path, task_id))
        else:
            error_msg = dump_tasks[task_id].get('error', 'Unknown error')
            c.execute("UPDATE dump_tasks SET status = 'failed', error = ? WHERE task_id = ?", (error_msg, task_id))
        conn.commit()
        conn.close()


@app.route('/scan/<scan_id>/dump-file', methods=['POST'])
def dump_file_from_memory(scan_id):
    # Use standard connection method
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    c.execute('SELECT * FROM scans WHERE uuid = ?', (scan_id,))
    scan = c.fetchone()

    if not scan:
        conn.close()
        return jsonify({'error': 'Scan not found'}), 404

    data = request.json
    
    # Determine default image fallback based on Volatility version
    default_image = "sp00kyskelet0n/volatility3"
    if scan['volatility_version'] == "2":
        default_image = "sp00kyskelet0n/volatility2"

    virt_addr = data.get('virt_addr')
    image = data.get('image') or scan['image'] or default_image
    file_path = data.get('file_path')
    
    if not virt_addr and not file_path:
        conn.close()
        return jsonify({'error': 'Virtual address or File Path required'}), 400

    # Create Task
    task_id = str(uuid.uuid4())
    c.execute("INSERT INTO dump_tasks (task_id, scan_id, status, created_at) VALUES (?, ?, ?, ?)",
              (task_id, scan_id, "pending", time.time()))
    conn.commit()
    conn.close()
    
    # Convert scan row to dict to pass to thread safely
    scan_dict = dict(scan)

    # Start Background Thread
    # Signature: background_dump_task(task_id, scan, virt_addr, image_tag, file_path=None)
    thread = threading.Thread(target=background_dump_task, args=(task_id, scan_dict, virt_addr, image, file_path))
    thread.daemon = True
    thread.start()
    
    return jsonify({"task_id": task_id, "status": "pending"})

@app.route('/dump-task/<task_id>', methods=['GET'])
def get_dump_status(task_id):
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM dump_tasks WHERE task_id = ?", (task_id,))
    task = c.fetchone()
    conn.close()
    
    if not task:
        return jsonify({"error": "Task not found"}), 404
        
    return jsonify(dict(task))

@app.route('/dump-task/<task_id>/download', methods=['GET'])
def download_dump_result(task_id):
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM dump_tasks WHERE task_id = ?", (task_id,))
    task = c.fetchone()
    conn.close()
    
    if not task:
        return jsonify({"error": "Task not found"}), 404
        
    if task['status'] != 'completed':
        return jsonify({"error": "Task not completed"}), 400
        
    file_path = task['output_path']
    if not file_path or not os.path.exists(file_path):
        return jsonify({"error": "File not found on server"}), 404
        
    return send_file(
        file_path,
        as_attachment=True,
        download_name=os.path.basename(file_path)
    )

@app.route('/results/<uuid>/fs/download', methods=['GET'])
def download_fs_file(uuid):
    key_path = request.args.get('path')
    if not key_path:
        return jsonify({"error": "Missing path"}), 400
        
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT output_dir FROM scans WHERE uuid = ?", (uuid,))
    scan = c.fetchone()
    conn.close()
    
    if not scan:
        return jsonify({"error": "Scan not found"}), 404
        
    output_dir = scan['output_dir']
    extract_dir = os.path.join(output_dir, "recovered_fs")
    
    # Security check: Ensure path is within extract_dir
    safe_path = os.path.normpath(os.path.join(extract_dir, key_path))
    if not safe_path.startswith(extract_dir):
         return jsonify({"error": "Invalid path"}), 403
         
    if not os.path.exists(safe_path):
        return jsonify({"error": "File not found"}), 404
        
    return send_file(safe_path, as_attachment=True)

@app.route('/results/<uuid>/strings', methods=['GET'])
def get_strings_content(uuid):
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 1000, type=int)
    query = request.args.get('q', '')
    
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT output_dir FROM scans WHERE uuid = ?", (uuid,))
    scan = c.fetchone()
    conn.close()
    
    if not scan:
        return jsonify({"error": "Scan not found"}), 404
        
    output_dir = scan['output_dir']
    strings_file = os.path.join(output_dir, "strings_output.txt")
    
    if not os.path.exists(strings_file):
        return jsonify({"error": "Strings output not found"}), 404

    content = []
    total_lines = 0

    if query:
        # Search mode - simple grep (limited to first 1000 matches to avoid overflow)
        try:
            # -i for case insensitive, -n for line numbers, -m for max count
            cmd = ['grep', '-i', '-n', '-m', str(limit), query, strings_file]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            # Format: "line_num:content"
            content = result.stdout.splitlines()
            total_lines = len(content) 
            
        except Exception as e:
            return jsonify({"error": f"Search failed: {str(e)}"}), 500
    else:
        # Pagination mode
        try:
            # Get total lines using wc -l
            wc_cmd = ['wc', '-l', strings_file]
            wc_res = subprocess.run(wc_cmd, stdout=subprocess.PIPE, text=True)
            if wc_res.returncode == 0 and wc_res.stdout:
                total_lines = int(wc_res.stdout.split()[0])
            
            # Use sed to extract range efficiently
            start_line = (page - 1) * limit + 1
            end_line = start_line + limit - 1
            
            sed_cmd = ['sed', '-n', f'{start_line},{end_line}p', strings_file]
            sed_res = subprocess.run(sed_cmd, stdout=subprocess.PIPE, text=True, errors='replace')
            content = sed_res.stdout.splitlines()
            
        except Exception as e:
            return jsonify({"error": f"Failed to read file: {str(e)}"}), 500

    return jsonify({
        "content": content,
        "total": total_lines,
        "page": page,
        "limit": limit
    })

@app.route('/results/<uuid>/strings/download', methods=['GET'])
def download_strings(uuid):
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT output_dir FROM scans WHERE uuid = ?", (uuid,))
    scan = c.fetchone()
    conn.close()
    
    if not scan:
        return jsonify({"error": "Scan not found"}), 404
        
    output_dir = scan['output_dir']
    strings_file = os.path.join(output_dir, "strings_output.txt")
    
    if not os.path.exists(strings_file):
        return jsonify({"error": "Strings output not found"}), 404
        
    return send_file(strings_file, as_attachment=True, download_name=f"strings_{uuid}.txt")

def run_api(runner_cb, debug_mode=False):
    global runner_func
    runner_func = runner_cb
    cleanup_timeouts() # Clean up stale tasks on startup
    app.run(host='0.0.0.0', port=5001, debug=debug_mode)

