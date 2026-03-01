from flask import Blueprint, request, jsonify
import logging
from multivol.api_server.config import APP_PASSWORD, API_TOKEN

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid request"}), 400
        
    password = data.get('password')
    if password == APP_PASSWORD:
        logging.info("Successful login attempt.")
        # We return the API_TOKEN to the frontend so it can use it for subsequent requests
        return jsonify({
            "success": True, 
            "token": API_TOKEN
        })
    
    logging.warning(f"Failed login attempt with password: {password}")
    return jsonify({"success": False, "error": "Invalid password"}), 401
