"""Tests for files routes (multivol/api_server/routes/files.py)."""
import pytest


class TestListEvidences:
    def test_returns_200(self, client, auth_headers):
        resp = client.get("/evidences", headers=auth_headers)
        assert resp.status_code == 200

    def test_returns_list(self, client, auth_headers):
        resp = client.get("/evidences", headers=auth_headers)
        data = resp.get_json()
        assert isinstance(data, list)

    def test_no_auth_returns_401(self, client):
        resp = client.get("/evidences")
        assert resp.status_code == 401

    def test_wrong_token_returns_401(self, client):
        resp = client.get("/evidences", headers={"Authorization": "Bearer bad_token"})
        assert resp.status_code == 401


class TestListSymbols:
    def test_returns_200(self, client, auth_headers):
        resp = client.get("/symbols", headers=auth_headers)
        assert resp.status_code == 200

    def test_returns_list(self, client, auth_headers):
        resp = client.get("/symbols", headers=auth_headers)
        data = resp.get_json()
        assert isinstance(data, list)

    def test_no_auth_returns_401(self, client):
        resp = client.get("/symbols")
        assert resp.status_code == 401
