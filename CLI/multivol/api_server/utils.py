"""Shared utility functions for hashing, JSON parsing, and filesystem helpers."""
import os
import hashlib
import time
import json
import logging
import subprocess
from typing import Any, Optional
import multivol.api_server.config as _config
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
        if container_path.startswith(_config.BASE_DIR):
            rel_path = os.path.relpath(container_path, _config.BASE_DIR)
            return os.path.join(host_base, rel_path)

        if 'storage' in container_path:
            rel_path = container_path[container_path.find('storage'):]
            return os.path.join(host_base, rel_path)
    except OSError:  # pylint: disable=broad-except
        logging.warning("resolve_host_path fallback triggered", exc_info=True)
    return container_path

def calculate_sha256(filepath: str) -> str:
    """Stream-hash a file in 4 KiB blocks to keep memory usage bounded.

    Raises ``OSError`` if the file cannot be opened; does not return on failure.
    """
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
            with open(hash_file, 'r', encoding="utf-8") as f:
                return f.read().strip()
        except OSError as e:
            logging.warning("Could not read cached hash for %s: %s", filepath, e)

    try:
        file_hash = calculate_sha256(filepath)
    except OSError as e:
        logging.warning("Could not hash file %s: %s", filepath, e)
        return None

    try:
        with open(hash_file, 'w', encoding="utf-8") as f:
            f.write(file_hash)
    except OSError as e:
        logging.warning("Could not write hash cache for %s: %s", filepath, e)
    return file_hash

def clean_and_parse_json(filepath: str) -> list[Any] | dict[str, Any] | None:
    """Parse JSON from a Volatility output file.

    Returns the parsed ``list`` or ``dict`` on success, or ``None`` when the
    file is missing, unreadable, or does not contain valid JSON.  Callers
    should check for ``None`` before using the result.
    """
    if not os.path.exists(filepath):
        logging.warning("clean_and_parse_json: file not found: %s", filepath)
        return None

    try:
        with open(filepath, 'r', encoding="utf-8") as f:
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
                pass  # Primary parse failed; try fallback below

        if parsed_data is None:
            lines = content.splitlines()
            if len(lines) > 1:
                try:
                    parsed_data = json.loads('\n'.join(lines[1:]))
                except json.JSONDecodeError:
                    pass  # Both parse attempts failed; fall through to None return

        if parsed_data is not None:
            return parsed_data

        logging.warning("clean_and_parse_json: invalid JSON in %s", filepath)
        return None

    except OSError:
        logging.exception("clean_and_parse_json: error reading %s", filepath)
        return None

def _build_extracted_files_map(output_dir: str) -> dict[str, str]:
    """Index files extracted by Volatility's RecoverFs by their decimal inode number.

    Returns a mapping of ``str(inode)`` → filename so tree nodes can link to
    downloadable files without iterating the directory on every request.
    """
    result = {}
    for filename in os.listdir(output_dir):
        if filename.startswith("file."):
            parts = filename.split('.')
            if len(parts) >= 2 and parts[1].isdigit():
                result[str(int(parts[1]))] = filename
    return result


def _build_fs_tree(data: list[Any], output_dir: str, extracted_files: dict[str, str]) -> dict[str, Any]:  # pylint: disable=too-many-locals
    """Convert a flat RecoverFs node list into a nested JSON-serialisable directory tree.

    Each node in *data* is a Volatility output row with ``FilePath`` and
    ``Inode`` fields. Nodes are inserted in path order; the returned root dict
    is suitable for direct serialisation in the ``/results/<uuid>/fs/list`` endpoint.
    """
    tree: dict[str, Any] = {"name": "/", "path": "/", "type": "directory", "children": []}

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

            is_leaf = i == len(parts) - 1
            new_node: dict[str, Any] = {"name": part, "path": current_path,
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
        subprocess.run(["tar", "-xzf", tar_path, "-C", extract_dir], check=True, timeout=120)
    except Exception:  # pylint: disable=broad-except
        logging.exception("Failed to extract recovered_fs.tar.gz in %s", output_dir)


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
        if data is None or not isinstance(data, list):
            return

        extracted_files = _build_extracted_files_map(output_dir)
        tree = _build_fs_tree(data, output_dir, extracted_files)

        with open(json_path, 'w', encoding="utf-8") as f:
            json.dump([tree], f, indent=2)

        logging.debug("process_recover_fs completed for %s", output_dir)

    except Exception:  # pylint: disable=broad-except
        logging.exception("Failed to process RecoverFs for %s", output_dir)

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
            logging.info("Cleaning up %s stale scans...", len(stale_scans))
            c.execute("UPDATE scans SET status='failed', error='Timeout (>1h)' WHERE status='running' AND created_at < ?", (one_hour_ago,))
            conn.commit()

        conn.close()
    except Exception:  # pylint: disable=broad-except
        logging.exception("Error cleaning up timeouts")
