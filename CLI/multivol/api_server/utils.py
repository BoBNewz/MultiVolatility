import os
import hashlib
import time
import json
import sqlite3
import logging
import subprocess
from typing import Optional, Union
from multivol.api_server.database import get_db_connection

def resolve_host_path(container_path: str, host_path_override: Optional[str] = None) -> str:
    """Translate a container-side path to the host path.

    Uses *host_path_override* when provided; otherwise falls back to the
    ``HOST_PATH`` environment variable. Returns *container_path* unchanged
    when no host base is available (e.g. single-host deployments).
    """
    host_base = host_path_override or os.environ.get("HOST_PATH")
    if not host_base:
        return container_path

    try:
        from multivol.api_server.config import BASE_DIR

        if container_path.startswith(BASE_DIR):
            rel_path = os.path.relpath(container_path, BASE_DIR)
            return os.path.join(host_base, rel_path)

        if 'storage' in container_path:
            rel_path = container_path[container_path.find('storage'):]
            return os.path.join(host_base, rel_path)
    except Exception as e:
        logging.warning(f"resolve_host_path fallback triggered: {e}")
    return container_path

def calculate_sha256(filepath: str) -> str:
    """Calculate the SHA-256 hash of a file and return it as a hex string."""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def get_file_hash(filepath: str) -> Optional[str]:
    """Return the SHA-256 hex digest for filepath, using a cached .sha256 sidecar file.

    Returns None (with a warning log) if the file cannot be read, so callers
    in HTTP handlers don't need try/except for missing files.
    """
    hash_file = filepath + ".sha256"
    if os.path.exists(hash_file):
        try:
            with open(hash_file, 'r') as f:
                return f.read().strip()
        except OSError as e:
            logging.warning("Could not read cached hash for %s: %s", filepath, e)

    try:
        file_hash = calculate_sha256(filepath)
    except OSError as e:
        logging.warning("Could not hash file %s: %s", filepath, e)
        return None

    try:
        with open(hash_file, 'w') as f:
            f.write(file_hash)
    except OSError as e:
        logging.warning("Could not write hash cache for %s: %s", filepath, e)
    return file_hash

def clean_and_parse_json(filepath: str) -> Union[list, dict]:
    """Parse JSON from a Volatility output file.

    Always returns a ``list`` or ``dict``. On parse failure or missing file,
    returns ``{"error": "...", "raw_output": "..."}``.
    """
    if not os.path.exists(filepath):
        logging.warning(f"File not found: {filepath}")
        return {"error": "File not found", "raw_output": ""}

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
            except json.JSONDecodeError:
                pass  # Try fallback below
        
        if parsed_data is None:
             lines = content.splitlines()
             if len(lines) > 1:
                 try:
                    parsed_data = json.loads('\n'.join(lines[1:]))
                 except json.JSONDecodeError:
                    pass
        
        if parsed_data is not None:
            return parsed_data
            
        # Fallback: Return raw content as error object if not valid JSON
        # This handles Volatility error messages stored in .json files
        return {"error": "Invalid JSON output", "raw_output": content}

    except Exception as e:
        return {"error": f"Error reading file: {str(e)}"}

def _build_extracted_files_map(output_dir: str) -> dict:
    """Map decimal inode strings to their extracted filename under output_dir."""
    result = {}
    for filename in os.listdir(output_dir):
        if filename.startswith("file."):
            parts = filename.split('.')
            if len(parts) >= 2 and parts[1].isdigit():
                result[str(int(parts[1]))] = filename
    return result


def _build_fs_tree(data: list, output_dir: str, extracted_files: dict) -> dict:
    """Build a JSON-serialisable directory tree from RecoverFs node list."""
    tree: dict = {"name": "/", "path": "/", "type": "directory", "children": []}

    for item in data:
        file_path = item.get("FilePath")
        if not file_path or file_path == "/":
            continue

        parts = file_path.strip("/").split("/")
        current_node = tree
        current_path = ""

        for i, part in enumerate(parts):
            current_path = f"{current_path}/{part}" if current_path else f"/{part}"

            found = next((c for c in current_node.get("children", []) if c["name"] == part), None)
            if found:
                current_node = found
                continue

            is_leaf = (i == len(parts) - 1)
            new_node: dict = {"name": part, "path": current_path,
                              "type": "file" if is_leaf else "directory"}

            if is_leaf:
                inode_id = str(item.get("Inode"))
                new_node["inode"] = item.get("Inode")
                if inode_id in extracted_files:
                    fname = extracted_files[inode_id]
                    new_node["extracted_file"] = fname
                    full_path = os.path.join(output_dir, fname)
                    if os.path.exists(full_path):
                        new_node["size"] = os.path.getsize(full_path)
            else:
                new_node["children"] = []

            current_node.setdefault("children", []).append(new_node)
            current_node = new_node

    return tree


def _extract_recoverfs_tarball(output_dir: str) -> None:
    """Extract recovered_fs.tar.gz so the APIs can serve its contents."""
    tar_path = os.path.join(output_dir, "recovered_fs.tar.gz")
    extract_dir = os.path.join(output_dir, "recovered_fs")
    if not os.path.exists(tar_path) or os.path.exists(extract_dir):
        return
    try:
        os.makedirs(extract_dir, exist_ok=True)
        subprocess.run(["tar", "-xzf", tar_path, "-C", extract_dir], check=True)
    except Exception as e:
        logging.error(f"Failed to extract recovered_fs.tar.gz: {e}")


def process_recover_fs(output_dir: str) -> None:
    """
    Reads the unstructured output of linux.pagecache.RecoverFs and
    builds a structured JSON tree representing the file system.
    Also extracts recovered_fs.tar.gz so files are readable by MCP.
    """
    json_path = os.path.join(output_dir, "linux.pagecache.RecoverFs_output.json")
    if not os.path.exists(json_path):
        return

    _extract_recoverfs_tarball(output_dir)

    try:
        data = clean_and_parse_json(json_path)
        if not data or isinstance(data, dict):
            return

        extracted_files = _build_extracted_files_map(output_dir)
        tree = _build_fs_tree(data, output_dir, extracted_files)

        with open(json_path, 'w') as f:
            json.dump([tree], f, indent=2)

        logging.debug(f"process_recover_fs completed for {output_dir}")

    except Exception:
        logging.error(f"Failed to process RecoverFs for {output_dir}", exc_info=True)

def cleanup_timeouts() -> None:
    """Marks scans running for > 1 hour as failed (timeout)."""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        one_hour_ago = time.time() - 3600
        
        # Find tasks that are 'running' and older than 1 hour
        c.execute("SELECT uuid FROM scans WHERE status='running' AND created_at < ?", (one_hour_ago,))
        stale_scans = c.fetchall()
        
        if stale_scans:
            logging.info(f"Cleaning up {len(stale_scans)} stale scans...")
            c.execute("UPDATE scans SET status='failed', error='Timeout (>1h)' WHERE status='running' AND created_at < ?", (one_hour_ago,))
            conn.commit()
            
        conn.close()
    except Exception as e:
        logging.error(f"Error cleaning up timeouts: {e}")
