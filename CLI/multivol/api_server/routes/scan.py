import os
import time
import json
import sqlite3
import argparse
import threading
import subprocess
import uuid
import glob
import docker
from flask import Blueprint, request, jsonify, send_file
from ..database import get_db_connection
from ..utils import clean_and_parse_json, process_recover_fs
from ..config import STORAGE_DIR, BASE_DIR

scan_bp = Blueprint('scan_bp', __name__)

def build_fs_tree(base_dir):
    """
    Walk the recovered_fs/ directory and build a nested tree structure:
    [{"name": "/", "path": "/", "type": "directory", "children": [...]}]
    """
    root = {"name": "/", "path": "/", "type": "directory", "children": []}
    nodes_by_path = {"/": root}

    for dirpath, dirnames, filenames in os.walk(base_dir):
        rel_dir = os.path.relpath(dirpath, base_dir)
        if rel_dir == ".":
            parent_node = root
        else:
            parent_path = "/" + rel_dir.replace(os.sep, "/")
            parent_node = nodes_by_path.get(parent_path, root)

        # Sort for consistent order
        dirnames.sort()
        filenames.sort()

        for d in dirnames:
            child_path = "/" + os.path.join(rel_dir, d).replace(os.sep, "/") if rel_dir != "." else "/" + d
            child_node = {
                "name": d,
                "path": child_path,
                "type": "directory",
                "children": []
            }
            parent_node["children"].append(child_node)
            nodes_by_path[child_path] = child_node

        for f in filenames:
            file_rel = os.path.join(rel_dir, f).replace(os.sep, "/") if rel_dir != "." else f
            file_path = "/" + file_rel
            full_path = os.path.join(dirpath, f)
            file_node = {
                "name": f,
                "path": file_path,
                "type": "file",
                "size": os.path.getsize(full_path) if os.path.exists(full_path) else 0
            }
            parent_node["children"].append(file_node)

    return [root]

runner_func = None # Needs to be initialized via init_runner
def init_runner(runner_cb):
    global runner_func
    runner_func = runner_cb               

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

@scan_bp.route('/scan', methods=['POST'])
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
        "profiles_path": os.path.join(BASE_DIR, "volatility2_profiles"),
        "symbols_path": os.path.join(BASE_DIR, "volatility3_symbols"),
        "cache_path": os.path.join(BASE_DIR, "volatility3_cache"),
        "plugins_dir": os.path.join(BASE_DIR, "volatility3_plugins"),
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
    final_output_dir = os.path.join(BASE_DIR, "outputs", base_name)
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
        if args_obj.commands:
            command_list = args_obj.commands.split(",")
        else:
            import yaml
            scan_type = "light" if args_obj.light else "full"
            yaml_name = f"{args_obj.mode}_{target_os}.{scan_type}.yaml"
            yaml_path = os.path.join(BASE_DIR, "multivol", "plugins_list", yaml_name)
            if os.path.exists(yaml_path):
                with open(yaml_path, "r", encoding="utf-8") as f:
                    yaml_data = yaml.safe_load(f)
                    command_list = yaml_data.get("modules", [])
            else:
                print(f"[WARNING] Plugin list not found: {yaml_path}")
        
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

@scan_bp.route('/status/<scan_id>', methods=['GET'])
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

@scan_bp.route('/scans/<uuid>/log', methods=['GET'])
def get_scan_log(uuid):
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT output_dir FROM scans WHERE uuid = ?", (uuid,))
    scan = c.fetchone()
    conn.close()
    
    if not scan:
         return jsonify({"error": "Scan not found"}), 404
         
    log_file = os.path.join(scan['output_dir'], "scan.log")
    if os.path.exists(log_file):
        with open(log_file, 'r') as f:
            return f.read()
    return "Log file not created yet or not found.", 404

@scan_bp.route('/scan/<uuid>/modules', methods=['POST'])
def update_scan_module_status(uuid):
    data = request.json
    module = data.get('module')
    status = data.get('status')
    error = data.get('error')
    
    if not module or not status:
        return jsonify({"error": "Missing module or status"}), 400

    conn = get_db_connection()
    c = conn.cursor()
    try:
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

@scan_bp.route('/scan/<uuid>/modules', methods=['GET'])
def get_scan_modules_status(uuid):
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    try:
        c.execute("SELECT output_dir FROM scans WHERE uuid = ?", (uuid,))
        scan_row = c.fetchone()
        output_dir = scan_row['output_dir'] if scan_row else None
        
        c.execute("SELECT module, status, error_message FROM scan_module_status WHERE scan_id = ?", (uuid,))
        rows = c.fetchall()
        
        status_list = []
        docker_client = None
        
        if rows:
            for row in rows:
                mod_dict = dict(row)
                module_name = mod_dict['module']
                
                if mod_dict['status'] in ['PENDING', 'RUNNING']:
                    import re as re_module
                    sanitized_name = re_module.sub(r'[^a-zA-Z0-9_.-]', '', module_name)
                    container_names = [f"vol3_{uuid[:8]}_{sanitized_name}", f"vol2_{uuid[:8]}_{sanitized_name}"]
                    
                    try:
                        if docker_client is None:
                            docker_client = docker.from_env()
                        
                        container = None
                        for c_name in container_names:
                            try:
                                container = docker_client.containers.get(c_name)
                                break
                            except:
                                pass
                                
                        if container:
                            container_status = container.status
                            
                            if container_status == 'running':
                                mod_dict['status'] = 'RUNNING'
                                c.execute("UPDATE scan_module_status SET status = 'RUNNING', updated_at = ? WHERE scan_id = ? AND module = ?",
                                          (time.time(), uuid, module_name))
                            elif container_status == 'exited':
                                if module_name == "linux.pagecache.RecoverFs" and output_dir:
                                     process_recover_fs(output_dir)

                                if output_dir:
                                    output_file = os.path.join(output_dir, f"{module_name}_output.json")
                                    if os.path.exists(output_file):
                                        try:
                                            parsed_data = clean_and_parse_json(output_file)
                                            content_str = json.dumps(parsed_data) if parsed_data else "{}"
                                            c.execute("SELECT id FROM scan_results WHERE scan_id = ? AND module = ?", (uuid, module_name))
                                            if not c.fetchone():
                                                c.execute("INSERT INTO scan_results (scan_id, module, content, created_at) VALUES (?, ?, ?, ?)",
                                                          (uuid, module_name, content_str, time.time()))
                                        except Exception as e:
                                            print(f"[ERROR] Failed to ingest {module_name}: {e}")
                                            import traceback
                                            traceback.print_exc()
                                
                                mod_dict['status'] = 'COMPLETED'
                                c.execute("UPDATE scan_module_status SET status = 'COMPLETED', updated_at = ? WHERE scan_id = ? AND module = ?",
                                          (time.time(), uuid, module_name))
                                
                                try:
                                    container.remove()
                                except Exception as rm_err:
                                    pass
                                    
                    except Exception as e:
                        print(f"[ERROR] Exception checking container {container_names}: {e}")
                        import traceback
                        traceback.print_exc()
                
                status_list.append(mod_dict)
            
            conn.commit()
        else:
            c.execute("SELECT module FROM scan_results WHERE scan_id = ?", (uuid,))
            result_rows = c.fetchall()
            for r in result_rows:
                status_list.append({
                    "module": r['module'], 
                    "status": "COMPLETED", 
                    "error_message": None
                })
        
        if len(status_list) == 0 and output_dir and os.path.isdir(output_dir):
            json_files = glob.glob(os.path.join(output_dir, "*_output.json"))
            for jf in json_files:
                basename = os.path.basename(jf)
                if basename.endswith("_output.json"):
                    module_name = basename[:-len("_output.json")]
                    status_list.append({
                        "module": module_name,
                        "status": "COMPLETED",
                        "error_message": None
                    })

        if output_dir:
            strings_path = os.path.join(output_dir, "strings_output.txt")
            if os.path.exists(strings_path):
                if not any(m['module'] == 'strings' for m in status_list):
                    status_list.append({"module": "strings", "status": "COMPLETED"})

        return jsonify(status_list)

    except Exception as e:
        print(f"[ERROR] Fetching module status: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@scan_bp.route('/results/<uuid>', methods=['GET'])
def get_scan_results(uuid):
    module_param = request.args.get('module')
    if not module_param:
        return jsonify({"error": "Missing 'module' query parameter"}), 400
        
    try:
        limit = int(request.args.get('limit', 0))
    except ValueError:
        limit = 0
        
    try:
        offset = int(request.args.get('offset', 0))
    except ValueError:
        offset = 0

    def paginate_data(data):
        if isinstance(data, list) and limit > 0:
            return data[offset : offset + limit]
        return data

    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # RecoverFs: dynamically build tree from the recovered_fs/ directory on disk
    if module_param == 'linux.pagecache.RecoverFs':
        c.execute("SELECT output_dir FROM scans WHERE uuid = ?", (uuid,))
        scan = c.fetchone()
        conn.close()
        if not scan:
            return jsonify({"error": "Scan not found"}), 404
        extract_dir = os.path.join(scan['output_dir'], "recovered_fs")
        if os.path.exists(extract_dir):
            return jsonify(build_fs_tree(extract_dir))
        return jsonify({"error": "RecoverFs output directory not found"}), 404

    c.execute("SELECT content FROM scan_results WHERE scan_id = ? AND module = ?", (uuid, module_param))
    row = c.fetchone()
    if row:
        conn.close()
        try:
            data = json.loads(row['content'])
            return jsonify(paginate_data(data))
        except:
            return jsonify({"error": "Failed to parse stored content", "raw": row['content']}), 500

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
                    results[module_name] = paginate_data(parsed_data)
        return jsonify(results)
    else:
        target_file = os.path.join(output_dir, f"{module_param}_output.json")
        if not os.path.exists(target_file):
            return jsonify({"error": f"Module {module_param} output not found"}), 404
            
        parsed_data = clean_and_parse_json(target_file)
        if parsed_data is None:
             return jsonify({"error": f"Failed to parse JSON for {module_param}"}), 500
             
        return jsonify(paginate_data(parsed_data))

@scan_bp.route('/scans', methods=['GET'])
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
        
        c.execute("SELECT COUNT(*) FROM scan_results WHERE scan_id = ? AND content NOT LIKE '%\"error\": \"Invalid JSON output\"%'", (scan_uuid,))
        db_count = c.fetchone()[0]
        
        scan_dict['modules'] = db_count
        
        if scan_dict['status'] == 'completed' and db_count == 0:
            scan_dict['status'] = 'failed'
            scan_dict['error'] = 'No valid JSON results parsed'

        scan_dict['findings'] = 0 
        scans_list.append(scan_dict)
    
    conn.close()
    return jsonify(scans_list)

@scan_bp.route('/scans/<uuid>', methods=['PUT'])
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

@scan_bp.route('/scans/<uuid>', methods=['DELETE'])
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

@scan_bp.route('/scans/<uuid>/download', methods=['GET'])
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

    if not output_dir or not os.path.exists(output_dir):
         return jsonify({"error": "Output directory not found or empty"}), 404
         
    import tempfile
    import zipfile
    
    # Create temp zip file
    tmp_dir = tempfile.gettempdir()
    zip_filename = f"{scan_name.replace(' ', '_')}_{uuid[:8]}_results.zip"
    zip_filepath = os.path.join(tmp_dir, zip_filename)
    
    try:
        with zipfile.ZipFile(zip_filepath, 'w', zipfile.ZIP_DEFLATED) as zipf:
             # Walk output directory
             for root, dirs, files in os.walk(output_dir):
                 for file in files:
                     file_path = os.path.join(root, file)
                     # Add file to zip archive with relative path to avoid absolute paths inside zip
                     arcname = os.path.relpath(file_path, os.path.dirname(output_dir))
                     zipf.write(file_path, arcname)
                     
        return send_file(zip_filepath, as_attachment=True, download_name=zip_filename)
    except Exception as e:
         print(f"[ERROR] ZIP creation failed: {e}")
         return jsonify({"error": "Failed to generate ZIP archive"}), 500

@scan_bp.route('/scans/<uuid>/execute', methods=['POST'])
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

    default_args = {
        "profiles_path": os.path.join(BASE_DIR, "volatility2_profiles"),
        "symbols_path": os.path.join(BASE_DIR, "volatility3_symbols"),
        "cache_path": os.path.join(BASE_DIR, "volatility3_cache"),
        "plugins_dir": os.path.join(BASE_DIR, "volatility3_plugins"),
        "format": "json",
        "commands": module,
        "light": False,
        "full": False,
        "linux": False,
        "windows": False,
        "mode": scan['volatility_version'],
        "profile": None,
        "processes": 1, 
        "host_path": os.environ.get("HOST_PATH"),
        "debug": True,
        "fetch_symbol": False,
        "custom_symbol": None,
        "dump": scan['dump_path'],
        "image": scan['image'],
        "output_dir": scan['output_dir']
    }

    if scan['os'] == 'linux':
        default_args['linux'] = True
        default_args['fetch_symbol'] = True
    elif scan['os'] == 'windows':
        default_args['windows'] = True
    
    args_obj = argparse.Namespace(**default_args)
    args_obj.scan_id = uuid

    def background_single_run(s_id, args):
        try:
             if runner_func:
                 runner_func(args)
             
             # Need a quick local ingest instead of the huge helper due to scope changes.
             # Actually I'd rather move ingestion to utils entirely but I'll write logic to load JSON and write DB block.
             fpath = os.path.join(args.output_dir, f"{args.commands}_output.json")
             if os.path.exists(fpath):
                 parsed_data = clean_and_parse_json(fpath)
                 content_str = json.dumps(parsed_data) if parsed_data else "{}"

                 conn_bg = get_db_connection()
                 c_bg = conn_bg.cursor()
                 c_bg.execute("SELECT id FROM scan_results WHERE scan_id = ? AND module = ?", (s_id, args.commands))
                 if not c_bg.fetchone():
                     c_bg.execute("INSERT INTO scan_results (scan_id, module, content, created_at) VALUES (?, ?, ?, ?)",
                                  (s_id, args.commands, content_str, time.time()))
                 conn_bg.commit()
                 conn_bg.close()
        except Exception as e:
            print(f"[ERROR] Manual plugin execution failed: {e}")

    try:
        conn = get_db_connection()
        c = conn.cursor()
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

@scan_bp.route('/stats', methods=['GET'])
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
    
    symbols_path = os.path.join(BASE_DIR, "volatility3_symbols")
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

@scan_bp.route('/results/<uuid>/fs/list', methods=['GET'])
def list_fs_files(uuid):
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

    if not os.path.exists(extract_dir):
        return jsonify({"files": []}), 200

    file_list = []
    for root, _, files in os.walk(extract_dir):
        for f in files:
            # We want the relative path from the `recovered_fs` root
            full_path = os.path.join(root, f)
            rel_path = os.path.relpath(full_path, extract_dir)
            file_list.append(rel_path)

    return jsonify({"files": file_list})

@scan_bp.route('/results/<uuid>/fs/view', methods=['GET'])
def view_fs_file(uuid):
    key_path = request.args.get('path')
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 1000, type=int)
    query = request.args.get('q', '')

    if not key_path:
        return jsonify({"error": "Missing path"}), 400
    key_path = key_path.lstrip('/')

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

    safe_path = os.path.normpath(os.path.join(extract_dir, key_path))
    if not safe_path.startswith(extract_dir):
         return jsonify({"error": "Invalid path"}), 403

    if not os.path.exists(safe_path):
        return jsonify({"error": "File not found"}), 404

    content = []
    total_lines = 0

    if query:
        try:
            cmd = ['grep', '-i', '-n', '-m', str(limit), query, safe_path]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors='replace')
            content = result.stdout.splitlines()
            total_lines = len(content)
        except Exception as e:
            return jsonify({"error": f"Search failed: {str(e)}"}), 500
    else:
        try:
            wc_cmd = ['wc', '-l', safe_path]
            wc_res = subprocess.run(wc_cmd, stdout=subprocess.PIPE, text=True, errors='replace')
            if wc_res.returncode == 0 and wc_res.stdout:
                total_lines = int(wc_res.stdout.split()[0])

            start_line = (page - 1) * limit + 1
            end_line = start_line + limit - 1

            sed_cmd = ['sed', '-n', f'{start_line},{end_line}p', safe_path]
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

@scan_bp.route('/results/<uuid>/fs/download', methods=['GET'])
def download_fs_file(uuid):
    key_path = request.args.get('path')
    if not key_path:
        return jsonify({"error": "Missing path"}), 400
    key_path = key_path.lstrip('/')
        
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
    
    safe_path = os.path.normpath(os.path.join(extract_dir, key_path))
    if not safe_path.startswith(extract_dir):
         return jsonify({"error": "Invalid path"}), 403
         
    if not os.path.exists(safe_path):
        return jsonify({"error": "File not found"}), 404
        
    return send_file(safe_path, as_attachment=True)

@scan_bp.route('/results/<uuid>/strings', methods=['GET'])
def get_strings_content(uuid):
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 1000, type=int)
    query = request.args.get('q', '')
    context = request.args.get('context', 0, type=int)
    # Cap context lines at 100 to prevent excessive output
    context = min(max(context, 0), 100)
    
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
        try:
            cmd = ['grep', '-i', '-n']
            if context > 0:
                cmd += ['-C', str(context)]
            cmd += ['-m', str(limit), query, strings_file]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            content = result.stdout.splitlines()
            total_lines = len(content) 
        except Exception as e:
            return jsonify({"error": f"Search failed: {str(e)}"}), 500
    else:
        try:
            wc_cmd = ['wc', '-l', strings_file]
            wc_res = subprocess.run(wc_cmd, stdout=subprocess.PIPE, text=True)
            if wc_res.returncode == 0 and wc_res.stdout:
                total_lines = int(wc_res.stdout.split()[0])
            
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
        "limit": limit,
        "context": context
    })

@scan_bp.route('/results/<uuid>/strings/download', methods=['GET'])
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
