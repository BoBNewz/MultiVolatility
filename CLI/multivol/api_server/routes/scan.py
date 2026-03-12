"""Scan orchestration routes: start, status, results, and module execution."""

# pylint: disable=duplicate-code,redefined-outer-name,too-many-lines
import os
import re
import time
import json
import sqlite3
import argparse
import dataclasses
import threading
import subprocess
import shutil
import tempfile
import zipfile
import glob
import logging
import uuid as uuid_mod
from typing import Any, Callable, Optional, TypedDict
import yaml
import docker
from flask import Blueprint, request, jsonify, send_file, Response
from multivol.api_server.database import get_db_connection
from multivol.api_server.utils import clean_and_parse_json, process_recover_fs
from multivol.api_server.config import STORAGE_DIR, BASE_DIR
from multivol.multi_volatility_base import ApiScanConfig

scan_bp = Blueprint("scan_bp", __name__)


class ScanRecord(TypedDict, total=False):
    """Shape of a scan row returned from the database."""

    uuid: str
    status: str
    output_dir: str
    mode: str
    name: str
    config_json: str
    created_at: float
    updated_at: float


def build_fs_tree(base_dir: str) -> list[dict[str, Any]]:  # pylint: disable=too-many-locals
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
            child_path = (
                "/" + os.path.join(rel_dir, d).replace(os.sep, "/") if rel_dir != "." else "/" + d
            )
            child_node = {
                "name": d,
                "path": child_path,
                "type": "directory",
                "children": [],
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
                "size": os.path.getsize(full_path) if os.path.exists(full_path) else 0,
            }
            parent_node["children"].append(file_node)

    return [root]


runner_func: Optional[Callable[[argparse.Namespace], None]] = None  # pylint: disable=invalid-name


def init_runner(runner_cb: Callable[[argparse.Namespace], None]) -> None:
    """Register the analysis runner callback. Must be called before any scan is started.

    The callback receives an ``argparse.Namespace`` built from an
    ``ApiScanConfig`` so that existing runner implementations remain compatible.
    """
    # pylint: disable=global-statement
    global runner_func
    runner_func = runner_cb


def _require_runner() -> bool:
    """Guard for route handlers that need an active runner.

    Returns False (with a logged error) when init_runner() has never been called,
    so callers can immediately return a 503 without checking runner_func directly.
    """
    if runner_func is None:
        logging.error(
            "runner_func is None — scan cannot execute. Call init_runner() before starting scans."
        )
        return False
    return True


def ingest_results_to_db(scan_id: str, output_dir: str) -> None:
    """Sweep output_dir for *_output.json files and persist each into scan_results.

    Idempotent: skips modules already in the database. Called after the background
    scan thread completes, or on manual re-ingestion via the status endpoint.
    """
    logging.debug("Ingesting results for %s from %s", scan_id, output_dir)
    if not os.path.exists(output_dir):
        logging.error("Output dir not found: %s", output_dir)
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
                c.execute(
                    "SELECT id FROM scan_results WHERE scan_id = ? AND module = ?",
                    (scan_id, module_name),
                )
                if c.fetchone():
                    continue

                # Parse or read content
                parsed_data = clean_and_parse_json(f)
                if parsed_data is None:
                    continue
                content_str = json.dumps(parsed_data)

                c.execute(
                    "INSERT INTO scan_results (scan_id, module, content, created_at)"
                    " VALUES (?, ?, ?, ?)",
                    (scan_id, module_name, content_str, time.time()),
                )

                c.execute(
                    """
                    UPDATE scan_module_status
                    SET status = 'COMPLETED',
                        updated_at = ?
                    WHERE scan_id = ? AND module = ?
                    """,
                    (time.time(), scan_id, module_name),
                )
        except Exception:  # pylint: disable=broad-except
            logging.exception("Failed to ingest %s", f)

    conn.commit()
    conn.close()
    logging.debug("Ingestion complete for %s", scan_id)


def _check_concurrency() -> Optional[Response]:
    """Return a 429 Response if a scan is already running/pending, else return None."""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT uuid FROM scans WHERE status IN ('pending', 'running')")
        existing_scan = c.fetchone()
        conn.close()

        if existing_scan:
            return jsonify(
                {"error": "A scan is already in progress. Please wait for it to complete."}
            ), 429
    except Exception as e:  # pylint: disable=broad-except
        logging.exception("Failed to check concurrency")
        # Fail closed for stability.
        return jsonify({"error": f"Database error checking concurrency: {e}"}), 500

    return None


def _build_args_from_request(
    data: dict[str, Any],
) -> tuple[ApiScanConfig, str, str, str]:
    """
    Build an ApiScanConfig from the request payload, generate a scan_id,
    create the output directory, and validate the dump path.

    Returns (config, scan_id, target_os, vol_version).
    Raises ValueError with a user-facing message on input validation failure.
    Raises other exceptions for system-level errors (e.g. makedirs failure).
    """
    # Basic validation
    if "dump" not in data or "mode" not in data:
        raise ValueError("Missing required fields: dump, mode")

    # Determine default image based on mode
    req_mode = data.get("mode", "vol3")
    default_image = "sp00kyskelet0n/volatility3"
    if req_mode == "vol2":
        default_image = "sp00kyskelet0n/volatility2"

    # Validate OS flags before building config (avoids overwriting defaults)
    is_linux = bool(data.get("linux"))
    is_windows = bool(data.get("windows"))

    if is_linux == is_windows:
        raise ValueError(
            "You must specify either 'linux': true or 'windows': true, but not both or neither."
        )

    scan_id = str(uuid_mod.uuid4())

    # Construct output directory with UUID
    req_mode_val = data.get("mode", "vol3")
    base_name = f"volatility2_{scan_id}" if req_mode_val == "vol2" else f"volatility3_{scan_id}"
    final_output_dir = os.path.join(BASE_DIR, "outputs", base_name)

    # Ensure directory exists immediately to prevent "No output dir" errors on early failure
    try:
        os.makedirs(final_output_dir, exist_ok=True)
    except Exception:  # pylint: disable=broad-except
        logging.exception("Failed to create output dir %s", final_output_dir)
        raise

    # Normalize dump path: if it's a bare filename, look it up under storage
    dump = data.get("dump", "")
    if not os.path.isabs(dump) and not dump.startswith("/"):
        dump = os.path.join(STORAGE_DIR, dump)

    if not os.path.exists(dump):
        raise ValueError(f"Dump file not found at {dump}")

    config = ApiScanConfig(
        dump=dump,
        mode=data.get("mode", "vol3"),
        linux=is_linux,
        windows=is_windows,
        output_dir=final_output_dir,
        scan_id=scan_id,
        image=data.get("image", default_image),
        profiles_path=data.get("profiles_path", os.path.join(BASE_DIR, "volatility2_profiles")),
        symbols_path=data.get("symbols_path", os.path.join(BASE_DIR, "volatility3_symbols")),
        cache_path=data.get("cache_path", os.path.join(BASE_DIR, "volatility3_cache")),
        plugins_dir=data.get("plugins_dir", os.path.join(BASE_DIR, "volatility3_plugins")),
        format=data.get("format", "json"),
        commands=data.get("commands"),
        light=bool(data.get("light", False)),
        full=bool(data.get("full", False)),
        profile=data.get("profile"),
        processes=data.get("processes"),
        host_path=data.get("host_path", os.environ.get("HOST_PATH")),
        debug=bool(data.get("debug", True)),
        fetch_symbol=is_linux and bool(data.get("fetch_symbol", True)),
        custom_symbol=data.get("custom_symbol"),
    )

    target_os = "windows" if config.windows else ("linux" if config.linux else "unknown")
    vol_version = config.mode

    return config, scan_id, target_os, vol_version


def _load_command_list(args_obj: ApiScanConfig, target_os: str) -> list[str]:
    """
    Determine which plugin commands to run from the args or a YAML plugin list.
    Mutates args_obj.commands to the resolved comma-joined list when populated.
    Returns the list of command strings (may be empty on error).
    """
    try:
        command_list = []
        if args_obj.commands:
            command_list = args_obj.commands.split(",")
        else:
            scan_type = "light" if args_obj.light else "full"
            yaml_name = f"{args_obj.mode}_{target_os}.{scan_type}.yaml"
            yaml_path = os.path.join(BASE_DIR, "multivol", "plugins_list", yaml_name)
            if os.path.exists(yaml_path):
                with open(yaml_path, "r", encoding="utf-8") as f:
                    yaml_data = yaml.safe_load(f)
                    command_list = yaml_data.get("modules", [])
            else:
                logging.warning("Plugin list not found: %s", yaml_path)

        # Inject explicit commands into args for the CLI runner
        if command_list:
            args_obj.commands = ",".join(command_list)

    except Exception:  # pylint: disable=broad-except
        logging.exception("Failed to determine commands")
        command_list = []

    return command_list


def _insert_scan_record(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    args_obj: ApiScanConfig,
    scan_id: str,
    command_list: list[str],
    case_name: Optional[str],
    vol_version: str,
    target_os: str,
    data: dict[str, Any],
) -> None:
    """Insert the scan row and pre-populate per-module status rows."""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO scans"
        " (uuid, status, mode, os, volatility_version, dump_path, output_dir,"
        " created_at, image, name, config_json)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            scan_id,
            "pending",
            "light" if args_obj.light else "full",
            target_os,
            vol_version,
            args_obj.dump,
            args_obj.output_dir,
            time.time(),
            args_obj.image,
            case_name,
            json.dumps(data),
        ),
    )

    if command_list:
        for cmd in command_list:
            c.execute(
                "INSERT INTO scan_module_status"
                " (scan_id, module, status, updated_at) VALUES (?, ?, 'PENDING', ?)",
                (scan_id, cmd, time.time()),
            )

    conn.commit()
    conn.close()


def _run_scan_background(s_id: str, config: ApiScanConfig) -> None:
    """Background thread body: run the scan, ingest results, and update DB status."""
    conn = get_db_connection()
    c = conn.cursor()

    try:
        c.execute("UPDATE scans SET status = 'running' WHERE uuid = ?", (s_id,))
        conn.commit()

        if _require_runner():
            args = argparse.Namespace(**dataclasses.asdict(config))
            runner_func(args)

        # Process RecoverFs if present (extract tarball)
        process_recover_fs(config.output_dir)

        # Ingest results to DB
        ingest_results_to_db(s_id, config.output_dir)

        # Sweep: mark any still-pending modules as FAILED (container crash / no output)
        c.execute(
            "UPDATE scan_module_status SET status = 'FAILED',"
            " error_message = 'Module failed to produce output',"
            " updated_at = ? WHERE scan_id = ? AND status IN ('PENDING', 'RUNNING')",
            (time.time(), s_id),
        )
        conn.commit()

        c.execute("UPDATE scans SET status = 'completed' WHERE uuid = ?", (s_id,))
        conn.commit()
    except Exception as e:  # pylint: disable=broad-except
        logging.exception("Scan failed for %s", s_id)
        c.execute(
            "UPDATE scans SET status = 'failed', error = ? WHERE uuid = ?",
            (str(e), s_id),
        )
        conn.commit()
    finally:
        conn.close()


@scan_bp.route("/scan", methods=["POST"])
def scan() -> Response:
    """Start a new scan from the posted configuration."""
    concurrency_response = _check_concurrency()
    if concurrency_response is not None:
        return concurrency_response

    data = request.get_json() or {}

    try:
        config, scan_id, target_os, vol_version = _build_args_from_request(data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:  # pylint: disable=broad-except
        logging.exception("Failed to set up scan")
        return jsonify({"error": f"Failed to set up scan: {e}"}), 500

    case_name = data.get("name")
    command_list = _load_command_list(config, target_os)
    _insert_scan_record(config, scan_id, command_list, case_name, vol_version, target_os, data)

    thread = threading.Thread(target=_run_scan_background, args=(scan_id, config), daemon=True)
    thread.start()

    return jsonify({"scan_id": scan_id, "status": "pending", "output_dir": config.output_dir})


@scan_bp.route("/scans/<scan_id>/status", methods=["GET"])
def get_status(scan_id: str) -> Response:
    """Return current status and metadata for a scan."""
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM scans WHERE uuid = ?", (scan_id,))
    row = c.fetchone()
    conn.close()

    if row:
        return jsonify(dict(row))
    return jsonify({"error": "Scan not found"}), 404


@scan_bp.route("/scans/<uuid>/log", methods=["GET"])
def get_scan_log(uuid: str) -> Response:
    """Return the scan log file content."""
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT output_dir FROM scans WHERE uuid = ?", (uuid,))
    scan = c.fetchone()
    conn.close()

    if not scan:
        return jsonify({"error": "Scan not found"}), 404

    log_file = os.path.join(scan["output_dir"], "scan.log")
    if os.path.exists(log_file):
        with open(log_file, "r", encoding="utf-8") as f:
            return jsonify({"log": f.read()})
    return jsonify({"error": "Log file not created yet or not found"}), 404


@scan_bp.route("/scans/<uuid>/modules", methods=["POST"])
def update_scan_module_status(uuid: str) -> Response:
    """Update the status of an individual scan module."""
    data = request.get_json() or {}
    module = data.get("module")
    status = data.get("status")
    error = data.get("error")

    if not module or not status:
        return jsonify({"error": "Missing module or status"}), 400

    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute(
            "SELECT 1 FROM scan_module_status WHERE scan_id = ? AND module = ?",
            (uuid, module),
        )
        exists = c.fetchone()

        if exists:
            c.execute(
                "UPDATE scan_module_status"
                " SET status = ?, error_message = ?, updated_at = ?"
                " WHERE scan_id = ? AND module = ?",
                (status, error, time.time(), uuid, module),
            )
        else:
            c.execute(
                "INSERT INTO scan_module_status"
                " (scan_id, module, status, error_message, updated_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (uuid, module, status, error, time.time()),
            )

        conn.commit()
        return jsonify({"status": "success"})
    except Exception as e:  # pylint: disable=broad-except
        logging.exception("Failed to log module status")
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


def _find_container(docker_client: Any, uuid: str, module_name: str) -> Optional[Any]:
    """Locate a running or exited Docker container for this scan+module pair.

    Tries both ``vol3_`` and ``vol2_`` name prefixes to handle mixed-version
    scans. Returns None when no matching container is found (already removed).
    """
    sanitized_name = re.sub(r"[^a-zA-Z0-9_.-]", "", module_name)
    for prefix in ("vol3", "vol2"):
        try:
            return docker_client.containers.get(f"{prefix}_{uuid[:8]}_{sanitized_name}")
        except docker.errors.NotFound:
            pass  # Container already gone — nothing to remove
    return None


def _ingest_module_output(c: sqlite3.Cursor, uuid: str, module_name: str, output_dir: str) -> None:
    """Persist a single module's output into scan_results, skipping duplicates.

    Reads ``<module>_output.json``, parses it, and writes to the DB only when
    no existing row for (scan_id, module) exists, keeping ingestion idempotent.
    """
    output_file = os.path.join(output_dir, f"{module_name}_output.json")
    if not os.path.exists(output_file):
        return
    try:
        parsed_data = clean_and_parse_json(output_file)
        content_str = json.dumps(parsed_data) if parsed_data is not None else "{}"
        c.execute(
            "SELECT id FROM scan_results WHERE scan_id = ? AND module = ?",
            (uuid, module_name),
        )
        if not c.fetchone():
            c.execute(
                "INSERT INTO scan_results (scan_id, module, content, created_at)"
                " VALUES (?, ?, ?, ?)",
                (uuid, module_name, content_str, time.time()),
            )
    except Exception:  # pylint: disable=broad-except
        logging.exception("Failed to ingest %s for scan %s", module_name, uuid)


def _handle_exited_container(
    c: sqlite3.Cursor,
    uuid: str,
    module_name: str,
    output_dir: Optional[str],
    container: Any,
) -> None:
    """Handle a container that has exited: ingest output, mark COMPLETED, remove container."""
    if module_name == "linux.pagecache.RecoverFs" and output_dir:
        process_recover_fs(output_dir)
    if output_dir:
        _ingest_module_output(c, uuid, module_name, output_dir)
    c.execute(
        "UPDATE scan_module_status SET status = 'COMPLETED',"
        " updated_at = ? WHERE scan_id = ? AND module = ?",
        (time.time(), uuid, module_name),
    )
    try:
        container.remove()
    except docker.errors.APIError as rm_err:
        logging.debug("Container removal skipped (already gone or API error): %s", rm_err)


def _refresh_module_from_docker(
    c: sqlite3.Cursor,
    docker_client: Any,
    uuid: str,
    mod_dict: dict,
    output_dir: Optional[str],
) -> None:
    """Update mod_dict status by inspecting the corresponding Docker container."""
    module_name = mod_dict["module"]
    try:
        container = _find_container(docker_client, uuid, module_name)
        if container is None:
            return
        if container.status == "running":
            mod_dict["status"] = "RUNNING"
            c.execute(
                "UPDATE scan_module_status SET status = 'RUNNING',"
                " updated_at = ? WHERE scan_id = ? AND module = ?",
                (time.time(), uuid, module_name),
            )
        elif container.status == "exited":
            _handle_exited_container(c, uuid, module_name, output_dir, container)
            mod_dict["status"] = "COMPLETED"
    except Exception:  # pylint: disable=broad-except
        logging.exception("Exception checking container for module %s", module_name)


def _status_list_from_results(c: sqlite3.Cursor, uuid: str) -> list[dict]:
    """Build a status list from scan_results when no scan_module_status rows exist."""
    c.execute("SELECT module FROM scan_results WHERE scan_id = ?", (uuid,))
    return [
        {"module": r["module"], "status": "COMPLETED", "error_message": None} for r in c.fetchall()
    ]


def _status_list_from_output_dir(output_dir: str) -> list[dict]:
    """Infer completed modules by scanning output JSON files on disk."""
    status_list = []
    for jf in glob.glob(os.path.join(output_dir, "*_output.json")):
        basename = os.path.basename(jf)
        if basename.endswith("_output.json"):
            status_list.append(
                {
                    "module": basename[: -len("_output.json")],
                    "status": "COMPLETED",
                    "error_message": None,
                }
            )
    return status_list


def _append_strings_module(status_list: list[dict], output_dir: str) -> None:
    """Add a 'strings' entry if the strings output file exists and isn't already listed."""
    strings_path = os.path.join(output_dir, "strings_output.txt")
    if os.path.exists(strings_path) and not any(m["module"] == "strings" for m in status_list):
        status_list.append({"module": "strings", "status": "COMPLETED"})


@scan_bp.route("/scans/<uuid>/modules", methods=["GET"])
def get_scan_modules_status(uuid: str) -> Response:
    """Get status of all modules for a scan, with live Docker refresh."""
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    try:
        c.execute("SELECT output_dir FROM scans WHERE uuid = ?", (uuid,))
        scan_row = c.fetchone()
        output_dir = scan_row["output_dir"] if scan_row else None

        c.execute(
            "SELECT module, status, error_message FROM scan_module_status WHERE scan_id = ?",
            (uuid,),
        )
        rows = c.fetchall()

        if rows:
            docker_client = None
            status_list = []
            for row in rows:
                mod_dict = dict(row)
                if mod_dict["status"] in ("PENDING", "RUNNING"):
                    if docker_client is None:
                        docker_client = docker.from_env()
                    _refresh_module_from_docker(c, docker_client, uuid, mod_dict, output_dir)
                status_list.append(mod_dict)
            conn.commit()
        else:
            status_list = _status_list_from_results(c, uuid)

        if not status_list and output_dir and os.path.isdir(output_dir):
            status_list = _status_list_from_output_dir(output_dir)

        if output_dir:
            _append_strings_module(status_list, output_dir)

        return jsonify(status_list)

    except Exception as e:  # pylint: disable=broad-except
        logging.exception("Failed to fetch module status for scan %s", uuid)
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


def _paginate_data(
    data: list[Any] | dict[str, Any], limit: int, offset: int
) -> list[Any] | dict[str, Any]:
    """Slice a list result by offset/limit; dicts are returned unchanged."""
    if isinstance(data, list) and limit > 0:
        return data[offset : offset + limit]
    return data


def _parse_int_param(value: str | None, default: int) -> int:
    try:
        return int(value) if value is not None else default
    except ValueError:
        return default


def _get_recoverfs_result(c: sqlite3.Cursor, uuid: str) -> Response:
    """Return the RecoverFs filesystem tree for the given scan."""
    c.execute("SELECT output_dir FROM scans WHERE uuid = ?", (uuid,))
    scan = c.fetchone()
    if not scan:
        return jsonify({"error": "Scan not found"}), 404
    extract_dir = os.path.join(scan["output_dir"], "recovered_fs")
    if os.path.exists(extract_dir):
        return jsonify(build_fs_tree(extract_dir))
    return jsonify({"error": "RecoverFs output directory not found"}), 404


def _get_all_module_results(output_dir: str, paginate_data: Callable) -> Response:
    """Collect and return results for every module output file in output_dir."""
    results = {}
    for f in glob.glob(os.path.join(output_dir, "*_output.json")):
        filename = os.path.basename(f)
        if filename.endswith("_output.json"):
            module_name = filename[:-12]
            parsed_data = clean_and_parse_json(f)
            if parsed_data is not None:
                results[module_name] = paginate_data(parsed_data)
    return jsonify(results)


def _get_single_module_result(
    output_dir: str, module_param: str, paginate_data: Callable
) -> Response:
    """Return results for a specific module from its output file on disk."""
    target_file = os.path.join(output_dir, f"{module_param}_output.json")
    if not os.path.exists(target_file):
        return jsonify({"error": f"Module {module_param} output not found"}), 404
    parsed_data = clean_and_parse_json(target_file)
    if parsed_data is None:
        return jsonify({"error": f"Failed to parse JSON for {module_param}"}), 500
    return jsonify(paginate_data(parsed_data))


@scan_bp.route("/results/<uuid>", methods=["GET"])
def get_scan_results(uuid: str) -> Response:  # pylint: disable=too-many-return-statements
    """Return parsed results for a module in a scan."""
    module_param = request.args.get("module")
    if not module_param:
        return jsonify({"error": "Missing 'module' query parameter"}), 400

    limit = _parse_int_param(request.args.get("limit"), 0)
    offset = _parse_int_param(request.args.get("offset"), 0)

    def paginate(data: list[Any] | dict[str, Any]) -> list[Any] | dict[str, Any]:
        return _paginate_data(data, limit, offset)

    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    if module_param == "linux.pagecache.RecoverFs":
        result = _get_recoverfs_result(c, uuid)
        conn.close()
        return result

    c.execute(
        "SELECT content FROM scan_results WHERE scan_id = ? AND module = ?",
        (uuid, module_param),
    )
    row = c.fetchone()
    if row:
        conn.close()
        try:
            data = json.loads(row["content"])
            return jsonify(paginate(data))
        except (json.JSONDecodeError, KeyError):
            return jsonify({"error": "Failed to parse stored content", "raw": row["content"]}), 500

    c.execute("SELECT output_dir FROM scans WHERE uuid = ?", (uuid,))
    scan = c.fetchone()
    conn.close()

    if not scan:
        return jsonify({"error": "Scan not found"}), 404

    output_dir = scan["output_dir"]
    if not output_dir or not os.path.exists(output_dir):
        return jsonify({"error": "Output directory not found"}), 404

    if module_param == "all":
        return _get_all_module_results(output_dir, paginate)
    return _get_single_module_result(output_dir, module_param, paginate)


@scan_bp.route("/scans", methods=["GET"])
def list_scans() -> Response:
    """List all scans ordered by creation time."""
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM scans ORDER BY created_at DESC")
    rows = c.fetchall()

    scans_list = []
    for row in rows:
        scan_dict = dict(row)
        scan_uuid = scan_dict["uuid"]

        c.execute(
            "SELECT COUNT(*) FROM scan_results WHERE scan_id = ?"
            " AND content NOT LIKE '%\"error\": \"Invalid JSON output\"%'",
            (scan_uuid,),
        )
        db_count = c.fetchone()[0]

        scan_dict["modules"] = db_count

        if scan_dict["status"] == "completed" and db_count == 0:
            scan_dict["status"] = "failed"
            scan_dict["error"] = "No valid JSON results parsed"

        scan_dict["findings"] = 0
        scans_list.append(scan_dict)

    conn.close()
    return jsonify(scans_list)


@scan_bp.route("/scans/<uuid>", methods=["PUT"])
def rename_scan(uuid: str) -> Response:
    """Update the display name of a scan."""
    data = request.get_json() or {}
    new_name = data.get("name")
    if not new_name:
        return jsonify({"error": "Name is required"}), 400

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE scans SET name = ? WHERE uuid = ?", (new_name, uuid))
    conn.commit()
    conn.close()
    return jsonify({"status": "updated"})


@scan_bp.route("/scans/<uuid>", methods=["DELETE"])
def delete_scan(uuid: str) -> Response:
    """Delete a scan record and its output directory."""
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Get output dir to cleanup
    c.execute("SELECT output_dir FROM scans WHERE uuid = ?", (uuid,))
    row = c.fetchone()

    if row and row["output_dir"] and os.path.exists(row["output_dir"]):
        try:
            shutil.rmtree(row["output_dir"])
        except Exception:  # pylint: disable=broad-except
            logging.exception("Error deleting output dir %s", row["output_dir"])

    # Delete related records first (foreign key constraints)
    c.execute("DELETE FROM scan_module_status WHERE scan_id = ?", (uuid,))
    c.execute("DELETE FROM scan_results WHERE scan_id = ?", (uuid,))
    c.execute("DELETE FROM scans WHERE uuid = ?", (uuid,))
    conn.commit()
    conn.close()
    return jsonify({"status": "deleted"})


@scan_bp.route("/scans/<uuid>/download", methods=["GET"])
def download_scan_zip(uuid: str) -> Response:  # pylint: disable=too-many-locals
    """Download all scan results as a ZIP archive."""
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT output_dir, name FROM scans WHERE uuid = ?", (uuid,))
    row = c.fetchone()
    conn.close()

    if not row:
        return jsonify({"error": "Scan not found"}), 404

    output_dir = row["output_dir"]
    scan_name = row["name"] or f"scan_{uuid[:8]}"

    if not output_dir or not os.path.exists(output_dir):
        return jsonify({"error": "Output directory not found or empty"}), 404

    # Create temp zip file
    tmp_dir = tempfile.gettempdir()
    zip_filename = f"{scan_name.replace(' ', '_')}_{uuid[:8]}_results.zip"
    zip_filepath = os.path.join(tmp_dir, zip_filename)

    try:
        with zipfile.ZipFile(zip_filepath, "w", zipfile.ZIP_DEFLATED) as zipf:
            # Walk output directory
            for root, _, files in os.walk(output_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    # Add file to zip archive with relative path to avoid absolute paths inside zip
                    arcname = os.path.relpath(file_path, os.path.dirname(output_dir))
                    zipf.write(file_path, arcname)

        return send_file(zip_filepath, as_attachment=True, download_name=zip_filename)
    except Exception:  # pylint: disable=broad-except
        logging.exception("ZIP creation failed for scan %s", uuid)
        return jsonify({"error": "Failed to generate ZIP archive"}), 500


def _store_plugin_result(scan_id: str, module: str, output_dir: str) -> None:
    """Persist a plugin's JSON output file into the scan_results table (upsert-style)."""
    fpath = os.path.join(output_dir, f"{module}_output.json")
    if not os.path.exists(fpath):
        return
    parsed_data = clean_and_parse_json(fpath)
    content_str = json.dumps(parsed_data) if parsed_data is not None else "{}"
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT id FROM scan_results WHERE scan_id = ? AND module = ?",
        (scan_id, module),
    )
    if not c.fetchone():
        c.execute(
            "INSERT INTO scan_results (scan_id, module, content, created_at) VALUES (?, ?, ?, ?)",
            (scan_id, module, content_str, time.time()),
        )
    conn.commit()
    conn.close()


def _fetch_scan(uuid: str) -> Optional[sqlite3.Row]:
    """Return the scan row for *uuid*, or None when the scan does not exist."""
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM scans WHERE uuid = ?", (uuid,))
    scan = c.fetchone()
    conn.close()
    return scan


def _upsert_module_status(uuid: str, module: str, status: str) -> None:
    """Insert or update a scan_module_status row for the given scan and module."""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            "SELECT id FROM scan_module_status WHERE scan_id = ? AND module = ?",
            (uuid, module),
        )
        if c.fetchone():
            c.execute(
                "UPDATE scan_module_status"
                " SET status = ?, updated_at = ? WHERE scan_id = ? AND module = ?",
                (status, time.time(), uuid, module),
            )
        else:
            c.execute(
                "INSERT INTO scan_module_status"
                " (scan_id, module, status, updated_at) VALUES (?, ?, ?, ?)",
                (uuid, module, status, time.time()),
            )
        conn.commit()
        conn.close()
    except Exception:  # pylint: disable=broad-except
        logging.exception("Failed to upsert module status for scan %s, module %s", uuid, module)


def _background_single_plugin(s_id: str, cfg: ApiScanConfig) -> None:
    """Execute one plugin in a background thread, storing the result and updating status."""
    try:
        if _require_runner():
            args = argparse.Namespace(**dataclasses.asdict(cfg))
            runner_func(args)  # type: ignore[misc]
        _store_plugin_result(s_id, cfg.commands, cfg.output_dir)
    except Exception:  # pylint: disable=broad-except
        logging.exception(
            "Manual plugin execution failed for scan %s, module %s", s_id, cfg.commands
        )
        conn_err = get_db_connection()
        try:
            conn_err.execute(
                "UPDATE scan_module_status SET status = 'FAILED',"
                " error_message = 'Execution error',"
                " updated_at = ? WHERE scan_id = ? AND module = ?",
                (time.time(), s_id, cfg.commands),
            )
            conn_err.commit()
        finally:
            conn_err.close()


@scan_bp.route("/scans/<uuid>/execute", methods=["POST"])
def execute_plugin(uuid: str) -> Response:
    """Execute a single Volatility plugin for an existing scan."""
    data = request.get_json() or {}
    module = data.get("module")
    if not module:
        return jsonify({"error": "Missing 'module' parameter"}), 400

    scan = _fetch_scan(uuid)
    if not scan:
        return jsonify({"error": "Scan not found"}), 404

    config = ApiScanConfig(
        profiles_path=os.path.join(BASE_DIR, "volatility2_profiles"),
        symbols_path=os.path.join(BASE_DIR, "volatility3_symbols"),
        cache_path=os.path.join(BASE_DIR, "volatility3_cache"),
        plugins_dir=os.path.join(BASE_DIR, "volatility3_plugins"),
        format="json",
        commands=module,
        light=False,
        full=False,
        linux=scan["os"] == "linux",
        windows=scan["os"] == "windows",
        mode=scan["volatility_version"],
        profile=None,
        processes=1,
        host_path=os.environ.get("HOST_PATH"),
        debug=True,  # Volatility verbosity flag, not Flask debug
        fetch_symbol=scan["os"] == "linux",
        custom_symbol=None,
        dump=scan["dump_path"],
        image=scan["image"],
        output_dir=scan["output_dir"],
        scan_id=uuid,
    )

    _upsert_module_status(uuid, module, "RUNNING")

    thread = threading.Thread(target=_background_single_plugin, args=(uuid, config))
    thread.daemon = True
    thread.start()

    return jsonify({"status": "started", "module": module})


@scan_bp.route("/stats", methods=["GET"])
def get_stats() -> Response:
    """Return aggregate statistics about scans, evidences, and symbols."""
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
        for _, _, files in os.walk(symbols_path):
            total_symbols += len(files)

    return jsonify(
        {
            "total_cases": total_cases,
            "processing": running_cases,
            "total_evidences": total_evidences,
            "total_symbols": total_symbols,
        }
    )


@scan_bp.route("/results/<uuid>/fs/list", methods=["GET"])
def list_fs_files(uuid: str) -> Response:
    """List all recovered filesystem files for a scan."""
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT output_dir FROM scans WHERE uuid = ?", (uuid,))
    scan = c.fetchone()
    conn.close()

    if not scan:
        return jsonify({"error": "Scan not found"}), 404

    output_dir = scan["output_dir"]
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


@scan_bp.route("/results/<uuid>/fs/view", methods=["GET"])
def view_fs_file(uuid: str) -> Response:  # pylint: disable=too-many-locals,too-many-return-statements
    """View contents of a recovered filesystem file with pagination and search."""
    key_path = request.args.get("path")
    page = request.args.get("page", 1, type=int)
    limit = request.args.get("limit", 1000, type=int)
    query = request.args.get("q", "")

    if not key_path:
        return jsonify({"error": "Missing path"}), 400
    key_path = key_path.lstrip("/")

    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT output_dir FROM scans WHERE uuid = ?", (uuid,))
    scan = c.fetchone()
    conn.close()

    if not scan:
        return jsonify({"error": "Scan not found"}), 404

    output_dir = scan["output_dir"]
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
            cmd = ["grep", "-i", "-n", "-m", str(limit), query, safe_path]
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                errors="replace",
                timeout=30,
                check=False,
            )  # nosec B603 B607
            content = result.stdout.splitlines()
            total_lines = len(content)
        except Exception as e:  # pylint: disable=broad-except
            return jsonify({"error": f"Search failed: {str(e)}"}), 500
    else:
        try:
            wc_cmd = ["wc", "-l", safe_path]
            wc_res = subprocess.run(
                wc_cmd,
                stdout=subprocess.PIPE,
                text=True,
                errors="replace",
                timeout=30,
                check=False,
            )  # nosec B603 B607
            if wc_res.returncode == 0 and wc_res.stdout:
                total_lines = int(wc_res.stdout.split()[0])

            start_line = (page - 1) * limit + 1
            end_line = start_line + limit - 1

            sed_cmd = ["sed", "-n", f"{start_line},{end_line}p", safe_path]
            sed_res = subprocess.run(
                sed_cmd,
                stdout=subprocess.PIPE,
                text=True,
                errors="replace",
                timeout=30,
                check=False,
            )  # nosec B603 B607
            content = sed_res.stdout.splitlines()
        except Exception as e:  # pylint: disable=broad-except
            return jsonify({"error": f"Failed to read file: {str(e)}"}), 500

    return jsonify({"content": content, "total": total_lines, "page": page, "limit": limit})


@scan_bp.route("/results/<uuid>/fs/download", methods=["GET"])
def download_fs_file(uuid: str) -> Response:
    """Download a recovered filesystem file by path."""
    key_path = request.args.get("path")
    if not key_path:
        return jsonify({"error": "Missing path"}), 400
    key_path = key_path.lstrip("/")

    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT output_dir FROM scans WHERE uuid = ?", (uuid,))
    scan = c.fetchone()
    conn.close()

    if not scan:
        return jsonify({"error": "Scan not found"}), 404

    output_dir = scan["output_dir"]
    extract_dir = os.path.join(output_dir, "recovered_fs")

    safe_path = os.path.normpath(os.path.join(extract_dir, key_path))
    if not safe_path.startswith(extract_dir):
        return jsonify({"error": "Invalid path"}), 403

    if not os.path.exists(safe_path):
        return jsonify({"error": "File not found"}), 404

    return send_file(safe_path, as_attachment=True)


@scan_bp.route("/results/<uuid>/strings", methods=["GET"])
def get_strings_content(uuid: str) -> Response:  # pylint: disable=too-many-locals,too-many-return-statements
    """Return strings output with pagination, search, and context support."""
    page = request.args.get("page", 1, type=int)
    limit = request.args.get("limit", 1000, type=int)
    query = request.args.get("q", "")
    context = request.args.get("context", 0, type=int)
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

    output_dir = scan["output_dir"]
    strings_file = os.path.join(output_dir, "strings_output.txt")

    if not os.path.exists(strings_file):
        return jsonify({"error": "Strings output not found"}), 404

    content = []
    total_lines = 0

    if query:
        try:
            cmd = ["grep", "-i", "-n"]
            if context > 0:
                cmd += ["-C", str(context)]
            cmd += ["-m", str(limit), query, strings_file]
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=30,
                check=False,
            )  # nosec B603 B607
            content = result.stdout.splitlines()
            total_lines = len(content)
        except Exception as e:  # pylint: disable=broad-except
            return jsonify({"error": f"Search failed: {str(e)}"}), 500
    else:
        try:
            wc_cmd = ["wc", "-l", strings_file]
            wc_res = subprocess.run(
                wc_cmd, stdout=subprocess.PIPE, text=True, timeout=30, check=False
            )  # nosec B603 B607
            if wc_res.returncode == 0 and wc_res.stdout:
                total_lines = int(wc_res.stdout.split()[0])

            start_line = (page - 1) * limit + 1
            end_line = start_line + limit - 1

            sed_cmd = ["sed", "-n", f"{start_line},{end_line}p", strings_file]
            sed_res = subprocess.run(
                sed_cmd,
                stdout=subprocess.PIPE,
                text=True,
                errors="replace",
                timeout=30,
                check=False,
            )  # nosec B603 B607
            content = sed_res.stdout.splitlines()
        except Exception as e:  # pylint: disable=broad-except
            return jsonify({"error": f"Failed to read file: {str(e)}"}), 500

    return jsonify(
        {
            "content": content,
            "total": total_lines,
            "page": page,
            "limit": limit,
            "context": context,
        }
    )


@scan_bp.route("/results/<uuid>/strings/download", methods=["GET"])
def download_strings(uuid: str) -> Response:
    """Download the strings output file for a scan."""
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT output_dir FROM scans WHERE uuid = ?", (uuid,))
    scan = c.fetchone()
    conn.close()

    if not scan:
        return jsonify({"error": "Scan not found"}), 404

    output_dir = scan["output_dir"]
    strings_file = os.path.join(output_dir, "strings_output.txt")

    if not os.path.exists(strings_file):
        return jsonify({"error": "Strings output not found"}), 404

    return send_file(strings_file, as_attachment=True, download_name=f"strings_{uuid}.txt")
