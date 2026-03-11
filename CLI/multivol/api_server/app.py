"""Flask application factory and server entry point."""

from __future__ import annotations

import argparse
import os
import time
import logging
import sys
from typing import Callable

from flask import Flask, jsonify, Response
from flask_cors import CORS
from multivol.api_server.auth_middleware import check_authorization
from multivol.api_server.utils import cleanup_timeouts
from multivol.api_server.database import init_db
from multivol.api_server.config import ensure_dirs

# Import Blueprints
from multivol.api_server.routes.files import files_bp
from multivol.api_server.routes.docker import docker_bp
from multivol.api_server.routes.scan import scan_bp, init_runner
from multivol.api_server.routes.dump import dump_bp
from multivol.api_server.routes.memprocfs import memprocfs_bp
from multivol.api_server.routes.auth import auth_bp

app = Flask(__name__)
# Enable CORS — allow origins from CORS_ORIGINS env var (comma-separated),
# default open for local dev
_cors_origins = os.environ.get("CORS_ORIGINS", "*")
if _cors_origins != "*":
    _cors_origins = [o.strip() for o in _cors_origins.split(",")]
CORS(
    app,
    resources={
        r"/*": {
            "origins": _cors_origins,
            "allow_headers": ["Authorization", "Content-Type"],
        }
    },
)


@app.route("/health", methods=["GET"])
def health_check() -> Response:
    """Return service liveness status and current timestamp."""
    return jsonify({"status": "ok", "timestamp": time.time()})


app.before_request(check_authorization)

# Register Blueprints
app.register_blueprint(files_bp)
app.register_blueprint(docker_bp)
app.register_blueprint(scan_bp)
app.register_blueprint(dump_bp)
app.register_blueprint(memprocfs_bp)
app.register_blueprint(auth_bp)


def run_api(runner_cb: Callable[[argparse.Namespace], None], debug_mode: bool = False) -> None:
    """Start the API server. Binds runner_cb as the scan executor for /scan routes."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stderr)],
    )

    ensure_dirs()
    try:
        init_db()
        logging.info("Database initialized.")
    except Exception as e:  # pylint: disable=broad-except
        logging.critical("Failed to initialize database: %s", e)
        raise

    init_runner(runner_cb)
    cleanup_timeouts()  # Clean up stale tasks on startup

    if debug_mode:
        logging.info("Starting Flask in DEBUG mode...")
        app.run(host="0.0.0.0", port=5001, debug=True)  # nosec B201
    else:
        from waitress import serve  # pylint: disable=import-outside-toplevel

        logging.info(
            "Starting production server (waitress) on port 5001 with 50GB and 24h timeout..."
        )
        serve(
            app,
            host="0.0.0.0",
            port=5001,
            threads=10,
            max_request_body_size=53687091200,
            channel_timeout=86400,
        )  # nosec B104
        # 50GB limit, 24h timeout
