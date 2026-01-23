from flask import Flask, request, jsonify, abort
import argparse
import os
import docker
import threading
import uuid
import time
import sqlite3
import json
import glob
import hashlib
from werkzeug.utils import secure_filename
from flask import Flask, request, jsonify, abort, send_from_directory, send_file
from flask_cors import CORS
import zipfile
import io

app = Flask(__name__)
# Increase max upload size to 16GB (or appropriate limit for dumps)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 * 1024 
CORS(app, resources={r"/*": {"origins": "*"}}) # Explicitly allow all origins

STORAGE_DIR = os.environ.get("STORAGE_DIR", os.path.join(os.getcwd(), "storage"))
if not os.path.exists(STORAGE_DIR):
    os.makedirs(STORAGE_DIR)

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
    if request.remote_addr not in allowed_ips:
        abort(403, description="Access forbidden: Only localhost connections allowed, please set DISABLE_LOCALHOST_ONLY=1 to disable this check.")

def init_db():
    conn = sqlite3.connect('scans.db')
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

    conn.commit()
    conn.close()

init_db()

# ... (rest of imports/helpers)

@app.route('/scans/<uuid>', methods=['PUT'])
def rename_scan(uuid):
    data = request.json
    new_name = data.get('name')
    if not new_name:
        return jsonify({"error": "Name is required"}), 400
        
    conn = sqlite3.connect('scans.db')
    c = conn.cursor()
    c.execute("UPDATE scans SET name = ? WHERE uuid = ?", (new_name, uuid))
    conn.commit()
    conn.close()
    return jsonify({"status": "updated"})

@app.route('/scans/<uuid>', methods=['DELETE'])
def delete_scan(uuid):
    conn = sqlite3.connect('scans.db')
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
            
    c.execute("DELETE FROM scan_results WHERE scan_id = ?", (uuid,))
    c.execute("DELETE FROM scans WHERE uuid = ?", (uuid,))
    conn.commit()
    conn.close()
    return jsonify({"status": "deleted"})

@app.route('/scans/<uuid>/download', methods=['GET'])
def download_scan_zip(uuid):
    conn = sqlite3.connect('scans.db')
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
                 # Also exclude if it's just an empty object or error? User said "working one"
                 # Let's trust our clean_and_parse_json returns valid structure or error dict.
                 # If it's a real tool error that returns valid JSON, we might keep it.
                 # User said: "parse as working json". clean_and_parse_json handles the "parse" part.
                 # User said: "Only keep the working modules".
                 
                 # Add to zip
                 arcname = os.path.basename(f)
                 # We can store the cleaned content or the original file. 
                 # User said "parsed as working json" which implies validity. 
                 # Storing the original file is safer for exact reproduction, but clean_and_parse fixes junk.
                 # Let's write the CLEANED content to ensure it's valid JSON for the user.
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

    conn = sqlite3.connect('scans.db')
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

@app.route('/scan', methods=['POST'])
def scan():
    data = request.json
    
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
        "host_path": os.environ.get("HOST_PATH") # Added for DooD support via Env
    }
    
    args_dict = default_args.copy()
    args_dict.update(data)
    
    # Basic Validation
    if "dump" not in data or "image" not in data or "mode" not in data:
         return jsonify({"error": "Missing required fields: dump, image, mode"}), 400

    # Ensure mutual exclusion for OS flags
    is_linux = bool(data.get("linux"))
    is_windows = bool(data.get("windows"))
    
    if is_linux == is_windows:
        return jsonify({"error": "You must specify either 'linux': true or 'windows': true, but not both or neither."}), 400

    args_obj = argparse.Namespace(**args_dict)
    
    scan_id = str(uuid.uuid4())
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

    conn = sqlite3.connect('scans.db')
    c = conn.cursor()
    c.execute("INSERT INTO scans (uuid, status, mode, os, volatility_version, dump_path, output_dir, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
              (scan_id, "pending", "light" if args_obj.light else "full", target_os, vol_version, args_obj.dump, final_output_dir, time.time()))
    conn.commit()
    conn.close()

    def background_scan(s_id, args):
        conn = sqlite3.connect('scans.db')
        c = conn.cursor()
        
        try:
            c.execute("UPDATE scans SET status = 'running' WHERE uuid = ?", (s_id,))
            conn.commit()
            
            # Execute the runner
            if runner_func:
                runner_func(args)
            
            # Ingest results to DB
            ingest_results_to_db(s_id, args.output_dir)
            
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
    conn = sqlite3.connect('scans.db')
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

@app.route('/results/<uuid>/modules', methods=['GET'])
def get_scan_modules(uuid):
    conn = sqlite3.connect('scans.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # Check if we have results in DB
    c.execute("SELECT module, content FROM scan_results WHERE scan_id = ?", (uuid,))
    rows = c.fetchall()
    
    if rows:
        modules = []
        for row in rows:
            try:
                # content is stored as JSON string
                # We do a quick check to see if it's our known error structure
                # Parsing huge JSONs just to check error might be slow, but safe
                data = json.loads(row['content'])
                if isinstance(data, dict) and data.get("error") == "Invalid JSON output":
                    continue
                modules.append(row['module'])
            except:
                continue
        conn.close()
        return jsonify({"modules": modules})
    
    # Fallback to filesystem if DB empty
    c.execute("SELECT output_dir FROM scans WHERE uuid = ?", (uuid,))
    scan = c.fetchone()
    conn.close()
    
    if not scan:
         return jsonify({"error": "Scan not found"}), 404
    
    output_dir = scan['output_dir']
    if output_dir and os.path.exists(output_dir):
        json_files = glob.glob(os.path.join(output_dir, "*_output.json"))
        modules = []
        for f in json_files:
            filename = os.path.basename(f)
            if filename.endswith("_output.json"):
                # Validate content
                parsed_data = clean_and_parse_json(f)
                if parsed_data and isinstance(parsed_data, dict) and parsed_data.get("error") == "Invalid JSON output":
                    continue
                    
                module_name = filename[:-12]
                modules.append(module_name)
        return jsonify({"modules": modules})
        
    return jsonify({"modules": []})

@app.route('/results/<uuid>', methods=['GET'])
def get_scan_results(uuid):
    module_param = request.args.get('module')
    if not module_param:
        return jsonify({"error": "Missing 'module' query parameter"}), 400
        
    conn = sqlite3.connect('scans.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # try DB first
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
    conn = sqlite3.connect('scans.db')
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
        # Removing filesystem fallback for module counting to be consistent with "valid parsable json" rule.
        
        scan_dict['findings'] = 0 
        scans_list.append(scan_dict)


    
    conn.close()
    return jsonify(scans_list)

@app.route('/stats', methods=['GET'])
def get_stats():
    conn = sqlite3.connect('scans.db')
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
    # List files in /storage directly as source of truth for evidences
    try:
        files = os.listdir(STORAGE_DIR)
        valid_files = [f for f in files if os.path.isfile(os.path.join(STORAGE_DIR, f)) and not f.endswith('.sha256')]
    except FileNotFoundError:
        valid_files = []

    evidences = []
    for f in valid_files:
        path = os.path.join(STORAGE_DIR, f)
        evidences.append({
            "id": f, # Use filename as ID for frontend actions
            "name": f,
            "size": os.path.getsize(path), 
            "type": "Memory Dump",
            "hash": get_file_hash(path), 
            "uploaded": time.strftime('%Y-%m-%d', time.localtime(os.path.getmtime(path)))
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
    filename = secure_filename(filename)
    path = os.path.join(STORAGE_DIR, filename)
    if os.path.exists(path):
        try:
            os.remove(path)
            # Remove sidecar hash if exists
            if os.path.exists(path + ".sha256"):
                os.remove(path + ".sha256")
            return jsonify({"status": "deleted"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return jsonify({"error": "File not found"}), 404

@app.route('/evidence/<filename>/download', methods=['GET'])
def download_evidence(filename):
    filename = secure_filename(filename)
    return send_from_directory(STORAGE_DIR, filename, as_attachment=True)


def cleanup_timeouts():
    """Marks scans running for > 1 hour as failed (timeout)."""
    try:
        conn = sqlite3.connect('scans.db')
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

def run_api(runner_cb, debug_mode=False):
    global runner_func
    runner_func = runner_cb
    cleanup_timeouts() # Clean up stale tasks on startup
    app.run(host='0.0.0.0', port=5001, debug=debug_mode)
