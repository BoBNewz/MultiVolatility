import os
import sqlite3
import time
import shutil
import uuid
import json
import threading
import docker
import re
from flask import Blueprint, request, jsonify, send_file
from ..database import get_db_connection
from ..utils import resolve_host_path
from ..config import STORAGE_DIR

dump_bp = Blueprint('dump_bp', __name__)

dump_tasks = {}

def background_dump_task(task_id, scan, virt_addr, image_tag, file_path=None):
    """
    Executes a Volatility3 dump command.
    """
    print(f"[{task_id}] DEBUG: Starting background dump task for scan: {scan['uuid']}")
    dump_tasks[task_id] = {'status': 'running'}
    
    try:
        uploaded_path = scan['dump_path']
        if not os.path.isabs(uploaded_path) and not uploaded_path.startswith('/'):
            uploaded_path = os.path.join(STORAGE_DIR, uploaded_path)
            
        dump_filename = os.path.basename(uploaded_path)
        cmd = ["vol", "-v", "-f", f"/dump_dir/{dump_filename}", "-o", "/output"]

        config = {}
        if 'config_json' in scan.keys() and scan['config_json']:
             try:
                 config = json.loads(scan['config_json'])
             except:
                 pass

        if scan['os'] == 'linux' and config.get('fetch_symbol'):
             cmd.extend(["--remote-isf-url", "https://github.com/Abyss-W4tcher/volatility3-symbols/raw/master/banners/banners.json"])
             
        cmd.extend(["-s", "/symbols"])

        if scan['os'] == 'linux':
             if not file_path:
                 raise Exception("File Path is required for Linux dumps")
             cmd.extend(["linux.pagecache.Files", "--find", file_path, "--dump"])
        else:
            cmd.append("windows.dumpfiles.DumpFiles")
            addr_val = int(virt_addr)
            if addr_val < 0x80000000:
                cmd.append("--physaddr")
            else:
                cmd.append("--virtaddr")
            cmd.append(hex(addr_val))

        case_name = scan['name']
        case_extract_dir = os.path.join(STORAGE_DIR, f"{case_name}_extracted")
        if not os.path.exists(case_extract_dir):
            os.makedirs(case_extract_dir)

        task_out_dir = os.path.join(STORAGE_DIR, f"task_{task_id}")
        if not os.path.exists(task_out_dir):
           os.makedirs(task_out_dir)

        symbols_path = os.path.join(STORAGE_DIR, 'symbols')
        cache_path = os.path.join(STORAGE_DIR, 'cache')
        os.makedirs(symbols_path, exist_ok=True)
        os.makedirs(cache_path, exist_ok=True)

        volumes = {
            resolve_host_path(os.path.dirname(uploaded_path)): {'bind': '/dump_dir', 'mode': 'ro'},
            resolve_host_path(task_out_dir): {'bind': '/output', 'mode': 'rw'},
            resolve_host_path(symbols_path): {'bind': '/symbols', 'mode': 'rw'},
            resolve_host_path(cache_path): {'bind': '/root/.cache/volatility3', 'mode': 'rw'}
        }

        safe_scan_id = re.sub(r'[^a-zA-Z0-9]', '', scan['uuid'])[:8]
        container_name = f"vol3_dump_{safe_scan_id}_{task_id}"

        try:
            client = docker.from_env()
            container = client.containers.run(
                image=image_tag,
                name=container_name,
                command=cmd,
                volumes=volumes,
                remove=True,
                detach=False,
                stderr=True,
                stdout=True
            )
            output_str = container.decode('utf-8', errors='replace') if container else ""
        except docker.errors.ImageNotFound:
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
            raise Exception(f"Docker execution failed: {e}")

        files = os.listdir(task_out_dir)
        if not files:
            raise Exception(f"No file extracted by Volatility plugin. Dump command executed but output dir is empty.")
        
        created_files = []
        for f in files:
            src = os.path.join(task_out_dir, f)
            dst = os.path.join(case_extract_dir, f)
            shutil.move(src, dst)
            created_files.append(f)
            
        os.rmdir(task_out_dir)

        dump_tasks[task_id]['status'] = 'completed'
        dump_tasks[task_id]['output_path'] = f"/evidence/{created_files[0]}/download"

    except Exception as e:
        dump_tasks[task_id]['status'] = 'failed'
        dump_tasks[task_id]['error'] = str(e)
    finally:
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

@dump_bp.route('/scan/<scan_id>/dump-file', methods=['POST'])
def dump_file_from_memory(scan_id):
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('SELECT * FROM scans WHERE uuid = ?', (scan_id,))
    scan = c.fetchone()

    if not scan:
        conn.close()
        return jsonify({'error': 'Scan not found'}), 404

    data = request.json
    default_image = "sp00kyskelet0n/volatility3" if scan['volatility_version'] != "2" else "sp00kyskelet0n/volatility2"

    virt_addr = data.get('virt_addr')
    image = data.get('image') or scan['image'] or default_image
    file_path = data.get('file_path')
    
    if not virt_addr and not file_path:
        conn.close()
        return jsonify({'error': 'Virtual address or File Path required'}), 400

    task_id = str(uuid.uuid4())
    c.execute("INSERT INTO dump_tasks (task_id, scan_id, status, created_at) VALUES (?, ?, ?, ?)",
              (task_id, scan_id, "pending", time.time()))
    conn.commit()
    conn.close()
    
    scan_dict = dict(scan)

    thread = threading.Thread(target=background_dump_task, args=(task_id, scan_dict, virt_addr, image, file_path))
    thread.daemon = True
    thread.start()
    
    return jsonify({"task_id": task_id, "status": "pending"})

@dump_bp.route('/dump-task/<task_id>', methods=['GET'])
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

@dump_bp.route('/dump-task/<task_id>/download', methods=['GET'])
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
