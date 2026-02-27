from flask import Blueprint

# Initialize the main API blueprint
api_blueprint = Blueprint('api', __name__)

# Import route definers to register them
from .files import files_bp
from .docker import docker_bp
from .scan import scan_bp
from .dump import dump_bp