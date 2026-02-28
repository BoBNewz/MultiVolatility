import os
from flask import Flask
from flask_cors import CORS
from .database import init_db
from .auth import check_authorization
from .utils import cleanup_timeouts

# Import Blueprints
from .routes.files import files_bp
from .routes.docker import docker_bp
from .routes.scan import scan_bp, init_runner
from .routes.dump import dump_bp
from .routes.memprocfs import memprocfs_bp
from .routes.auth import auth_bp

app = Flask(__name__)
CORS(app) # Enable CORS for all routes

@app.route('/health', methods=['GET'])
def health_check():
    import time
    from flask import jsonify
    return jsonify({"status": "ok", "timestamp": time.time()})

app.before_request(check_authorization)

# Register Blueprints
app.register_blueprint(files_bp)
app.register_blueprint(docker_bp)
app.register_blueprint(scan_bp)
app.register_blueprint(dump_bp)
app.register_blueprint(memprocfs_bp)
app.register_blueprint(auth_bp)

# Init Database
try:
    init_db()
    print("[INFO] Database initialized.")
except Exception as e:
    print(f"[ERROR] Failed to init DB: {e}")


def run_api(runner_cb, debug_mode=False):
    """
    Main entry point for starting the API server from CLI.
    """
    init_runner(runner_cb)
    cleanup_timeouts() # Clean up stale tasks on startup
    app.run(host='0.0.0.0', port=5001, debug=debug_mode)
