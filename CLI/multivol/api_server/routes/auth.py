from flask import Blueprint, request, jsonify
import logging
from multivol.api_server.config import get_app_password, get_api_token

auth_bp = Blueprint('auth_bp', __name__)

@auth_bp.route('/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid request"}), 400
        
    password = data.get('password')
    if password == get_app_password():
        logging.info("Successful login attempt.")
        return jsonify({
            "success": True,
            "token": get_api_token()
        })
    
    logging.warning("Failed login attempt with invalid password.")
    return jsonify({"success": False, "error": "Invalid password"}), 401
