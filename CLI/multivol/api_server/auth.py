from flask import request, jsonify
import logging
from multivol.api_server.config import API_TOKEN

def check_authorization():
    # Allow OPTIONS requests for CORS or login endpoint
    if request.method == 'OPTIONS' or request.path == '/auth/login':
        return None

    auth_header = request.headers.get("Authorization")
    token_query = request.args.get("token")

    provided_token = None

    if auth_header and auth_header.startswith("Bearer "):
        provided_token = auth_header.split(" ")[1]
    elif token_query:
        provided_token = token_query

    if not provided_token or provided_token != API_TOKEN:
        logging.warning(f"Unauthorized access attempt to {request.path}")
        return jsonify({"error": "Unauthorized"}), 401

    return None
