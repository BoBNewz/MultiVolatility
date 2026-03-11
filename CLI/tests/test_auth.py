"""Tests for authorization logic in auth.py and auth_middleware.py."""
import pytest
from multivol.api_server.auth_middleware import _PUBLIC_PATHS


def test_health_check_bypasses_auth(client):
    """The /health endpoint should not require authorization."""
    resp = client.get("/health")
    assert resp.status_code == 200


def test_protected_endpoint_requires_auth(client):
    """/files should reject unauthenticated requests with 401."""
    resp = client.get("/files")
    assert resp.status_code == 401


def test_protected_endpoint_accepts_valid_token(client, auth_headers):
    """/files should not return 401 when a valid token is provided."""
    resp = client.get("/files", headers=auth_headers)
    assert resp.status_code != 401


def test_invalid_token_rejected(client):
    """A wrong token should be rejected."""
    resp = client.get("/files", headers={"Authorization": "Bearer wrong_token"})
    assert resp.status_code == 401


def test_public_paths_is_list():
    """_PUBLIC_PATHS contains health and auth paths that bypass auth."""
    assert isinstance(_PUBLIC_PATHS, (list, set, frozenset))
    assert any("/health" in p for p in _PUBLIC_PATHS)
    assert any("/auth" in p for p in _PUBLIC_PATHS)
