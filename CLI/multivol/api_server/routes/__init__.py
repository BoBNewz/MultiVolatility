from flask import Blueprint

# Initialize the main API blueprint
api_blueprint = Blueprint('api', __name__)

# Import route definers to register them
from multivol.api_server.routes.files import files_bp
from multivol.api_server.routes.docker import docker_bp
from multivol.api_server.routes.scan import scan_bp
from multivol.api_server.routes.dump import dump_bp
from multivol.api_server.routes.memprocfs import memprocfs_bp