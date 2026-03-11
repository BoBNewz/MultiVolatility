"""Tests for CLI/multivol/api_server/utils.py"""
import json
import os


def test_get_file_hash_returns_sha256(tmp_path):
    from multivol.api_server.utils import get_file_hash

    f = tmp_path / "sample.bin"
    f.write_bytes(b"hello world")
    result = get_file_hash(str(f))
    # Result is a 64-character hex SHA-256 digest
    assert len(result) == 64
    assert all(c in "0123456789abcdef" for c in result)


def test_get_file_hash_returns_none_on_missing_file():
    from multivol.api_server.utils import get_file_hash

    result = get_file_hash("/nonexistent/path/file.bin")
    assert result is None


def test_clean_and_parse_json_list(tmp_path):
    from multivol.api_server.utils import clean_and_parse_json

    data = [{"plugin": "pslist", "pid": 1}]
    f = tmp_path / "output.json"
    f.write_text(json.dumps(data))
    result = clean_and_parse_json(str(f))
    assert result == data


def test_clean_and_parse_json_object(tmp_path):
    from multivol.api_server.utils import clean_and_parse_json

    data = {"key": "value"}
    f = tmp_path / "output.json"
    f.write_text(json.dumps(data))
    result = clean_and_parse_json(str(f))
    assert result == data


def test_clean_and_parse_json_missing_file():
    from multivol.api_server.utils import clean_and_parse_json

    result = clean_and_parse_json("/nonexistent/file.json")
    assert result is None


def test_resolve_host_path_no_host_env(monkeypatch):
    """When HOST_PATH is unset, resolve_host_path returns the original path."""
    from multivol.api_server.utils import resolve_host_path

    monkeypatch.delenv("HOST_PATH", raising=False)
    path = "/some/container/path"
    result = resolve_host_path(path)
    assert result == path


def test_resolve_host_path_with_host_env(monkeypatch, tmp_path):
    """When HOST_PATH is set, resolve_host_path translates container paths."""
    from multivol.api_server.utils import resolve_host_path
    import multivol.api_server.config as cfg

    host_dir = str(tmp_path / "host")
    monkeypatch.setenv("HOST_PATH", host_dir)
    monkeypatch.setattr(cfg, "BASE_DIR", "/app")

    result = resolve_host_path("/app/outputs/scan_123")
    assert result == os.path.join(host_dir, "outputs/scan_123")
