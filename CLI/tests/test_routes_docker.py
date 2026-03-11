"""Tests for docker routes (multivol/api_server/routes/docker.py)."""


class TestListImages:
    def test_returns_200_or_500(self, client, auth_headers):
        """Returns 200 with images or 500 when Docker is unavailable."""
        resp = client.get("/images", headers=auth_headers)
        assert resp.status_code in (200, 500)

    def test_200_response_has_images_key(self, client, auth_headers):
        """On success, response contains an 'images' key with a list."""
        resp = client.get("/images", headers=auth_headers)
        if resp.status_code == 200:
            data = resp.get_json()
            assert "images" in data
            assert isinstance(data["images"], list)

    def test_no_auth_returns_401(self, client):
        resp = client.get("/images")
        assert resp.status_code == 401


class TestListPlugins:
    def test_requires_image_param(self, client, auth_headers):
        """Missing 'image' query param returns 400."""
        resp = client.get("/volatility3/plugins", headers=auth_headers)
        assert resp.status_code == 400

    def test_no_auth_returns_401(self, client):
        resp = client.get("/volatility3/plugins")
        assert resp.status_code == 401
