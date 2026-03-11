"""Request authentication middleware for the Flask API."""
import logging
from typing import Optional, Tuple, Union
from flask import request, jsonify, Response
from multivol.api_server.config import get_api_token

# Paths that do not require authentication
_PUBLIC_PATHS = {
    '/auth/login',  # credential exchange — no token yet
    '/health',      # liveness probe for load balancers — no auth context needed
}

# Return type: None means "allow the request", a Response/tuple means "reject it".
_AuthResult = Optional[Union[Response, Tuple[Response, int]]]


def check_authorization() -> _AuthResult:
    """Flask before_request hook that enforces token authentication.

    Returns ``None`` to allow the request to proceed, or a ``(Response, status)``
    tuple to reject it. Callers (Flask internals) handle both return shapes
    correctly — this is the standard Flask before_request contract.
    """
    # Allow CORS preflight requests
    if request.method == 'OPTIONS':
        return '', 200

    if request.path in _PUBLIC_PATHS:
        return None

    auth_header = request.headers.get("Authorization")
    token_query = request.args.get("token")

    provided_token = None
    if auth_header and auth_header.startswith("Bearer "):
        provided_token = auth_header.split(" ")[1]
    elif token_query:
        provided_token = token_query

    if not provided_token or provided_token != get_api_token():
        logging.warning("Unauthorized access attempt to %s", request.path)
        return jsonify({"error": "Unauthorized"}), 401

    return None
