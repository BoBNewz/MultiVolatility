VOLATILITY3_SYMBOLS_BANNER_URL = "https://github.com/Abyss-W4tcher/volatility3-symbols/raw/master/banners/banners.json"
import os
import sqlite3
import time
import shutil
import uuid
import json
import threading
import docker
import re
import logging
from typing import Any, TypedDict
from flask import Blueprint, request, jsonify, send_file, Response
from multivol.api_server.database import get_db_connection
from multivol.api_server.utils import resolve_host_path
from multivol.api_server.config import STORAGE_DIR

dump_bp = Blueprint('dump_bp', __name__)


class DumpTask(TypedDict, total=False):
    """Shape of a dump task record stored in dump_tasks."""
    status: str
    output_dir: str
    files: list[str]
    error: str
    started_at: float
    completed_at: float


dump_tasks: dict[str, DumpTask] = {}
dump_tasks_lock = threading.Lock()

def _build_vol_dump_command(scan: dict[str, Any], virt_addr: str | int, file_path: str | None, config: dict[str, Any]) -> list[str]:
    """Build the Volatility command list for a memory dump task."""
    uploaded_path = scan['dump_path']
    if not os.path.isabs(uploaded_path) and not uploaded_path.startswith('/'):
        uploaded_path = os.path.join(STORAGE_DIR, uploaded_path)
    dump_filename = os.path.basename(uploaded_path)

    cmd = ["vol", "-v", "-f", f"/dump_dir/{dump_filename}", "-o", "/output"]
    if scan['os'] == 'linux' and config.get('fetch_symbol'):
        cmd.extend(["--remote-isf-url",
                    VOLATILITY3_SYMBOLS_BANNER_URL])
    cmd.extend(["-s", "/symbols"])

    if scan['os'] == 'linux':
        if not file_path:
            raise ValueError("file_path is required for Linux dumps")
        cmd.extend(["linux.pagecache.Files", "--find", file_path, "--dump"])
    else:
        cmd.append("windows.dumpfiles.DumpFiles")
        addr_val = int(virt_addr)
        cmd.append("--physaddr" if addr_val < 0x80000000 else "--virtaddr")
        cmd.append(hex(addr_val))
    return cmd


def _run_docker_vol(client: docker.DockerClient, image_tag: str, container_name: str, cmd: list[str], volumes: dict[str, Any]) -> str:
    """Run a Volatility Docker container, auto-pulling the image if missing. Returns decoded stdout."""
    run_kwargs = dict(image=image_tag, name=container_name, command=cmd,
                      volumes=volumes, remove=True, detach=False, stderr=True, stdout=True)
    try:
        output = client.containers.run(**run_kwargs)
    except docker.errors.ImageNotFound:
        client.images.pull(image_tag)
        output = client.containers.run(**run_kwargs)
    return output.decode('utf-8', errors='replace') if output else ""


def _move_task_output(task_out_dir: str, case_extract_dir: str) -> list[str]:
    """Move all files from task_out_dir to case_extract_dir. Returns list of moved filenames."""
    files = os.listdir(task_out_dir)
    if not files:
        raise RuntimeError("Volatility plugin produced no output files")
    created = []
    for f in files:
        shutil.move(os.path.join(task_out_dir, f), os.path.join(case_extract_dir, f))
        created.append(f)
    os.rmdir(task_out_dir)
    return created


def background_dump_task(task_id: str, scan: dict[str, Any], virt_addr: str | int, image_tag: str, file_path: str | None = None) -> None:
    """Run a Volatility3 memory dump in a background thread, writing output to task_id's entry."""
    logging.debug("[%s] Starting background dump task for scan: %s", task_id, scan['uuid'])
    with dump_tasks_lock:
        dump_tasks[task_id] = {'status': 'running'}

    created_files: list[str] = []
    case_extract_dir: str = ""
    try:
        config: dict[str, Any] = {}
        if scan.get('config_json'):
            try:
                config = json.loads(scan['config_json'])
            except Exception:
                logging.warning("Failed to parse config_json for scan %s", scan.get('uuid', '?'), exc_info=True)

        cmd = _build_vol_dump_command(scan, virt_addr, file_path, config)

        case_extract_dir = os.path.join(STORAGE_DIR, f"{scan['name']}_extracted")
        os.makedirs(case_extract_dir, exist_ok=True)
        task_out_dir = os.path.join(STORAGE_DIR, f"task_{task_id}")
        os.makedirs(task_out_dir, exist_ok=True)

        symbols_path = os.path.join(STORAGE_DIR, 'symbols')
        cache_path = os.path.join(STORAGE_DIR, 'cache')
        os.makedirs(symbols_path, exist_ok=True)
        os.makedirs(cache_path, exist_ok=True)

        uploaded_path = scan['dump_path']
        if not os.path.isabs(uploaded_path):
            uploaded_path = os.path.join(STORAGE_DIR, uploaded_path)
        volumes = {
            resolve_host_path(os.path.dirname(uploaded_path)): {'bind': '/dump_dir', 'mode': 'ro'},
            resolve_host_path(task_out_dir):                   {'bind': '/output',   'mode': 'rw'},
            resolve_host_path(symbols_path):                   {'bind': '/symbols',  'mode': 'rw'},
            resolve_host_path(cache_path):                     {'bind': '/root/.cache/volatility3', 'mode': 'rw'},
        }

        safe_id = re.sub(r'[^a-zA-Z0-9]', '', scan['uuid'])[:8]
        client = docker.from_env()
        _run_docker_vol(client, image_tag, f"vol3_dump_{safe_id}_{task_id}", cmd, volumes)

        created_files = _move_task_output(task_out_dir, case_extract_dir)
        with dump_tasks_lock:
            dump_tasks[task_id]['status'] = 'completed'
            dump_tasks[task_id]['output_path'] = f"/evidence/{created_files[0]}/download"

    except Exception as e:
        with dump_tasks_lock:
            dump_tasks[task_id]['status'] = 'failed'
            dump_tasks[task_id]['error'] = str(e)
    finally:
        with dump_tasks_lock:
            task_status = dump_tasks[task_id]['status']
            task_error = dump_tasks[task_id].get('error', 'Unknown error')
        conn = get_db_connection()
        c = conn.cursor()
        if task_status == 'completed' and created_files:
            output_path = os.path.join(case_extract_dir, created_files[0])
            c.execute("UPDATE dump_tasks SET status = 'completed', output_path = ? WHERE task_id = ?",
                      (output_path, task_id))
        else:
            c.execute("UPDATE dump_tasks SET status = 'failed', error = ? WHERE task_id = ?",
                      (task_error, task_id))
        conn.commit()
        conn.close()

@dump_bp.route('/scans/<scan_id>/dump-file', methods=['POST'])
def dump_file_from_memory(scan_id: str) -> Response:
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('SELECT * FROM scans WHERE uuid = ?', (scan_id,))
    scan = c.fetchone()

    if not scan:
        conn.close()
        return jsonify({'error': 'Scan not found'}), 404

    data = request.get_json() or {}
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

@dump_bp.route('/dump-tasks/<task_id>', methods=['GET'])
def get_dump_status(task_id: str) -> Response:
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM dump_tasks WHERE task_id = ?", (task_id,))
    task = c.fetchone()
    conn.close()
    
    if not task:
        return jsonify({"error": "Task not found"}), 404
        
    return jsonify(dict(task))

@dump_bp.route('/dump-tasks/<task_id>/download', methods=['GET'])
def download_dump_result(task_id: str) -> Response:
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
