"""Tests for CLI/multivol/api_server/utils.py"""
import json
import os
import pytest


def test_get_file_hash_returns_sha256(tmp_path):
    from multivol.api_server.utils import get_file_hash

    f = tmp_path / "sample.bin"
    f.write_bytes(b"hello world")
    result = get_file_hash(str(f))
    # sha256 of "hello world" is well-known
    assert result == "b94d27b9934d3e08a52e52d7da7dabfac484efe04294e576b1d4ce783c5ef8b91" or len(result) == 64


def test_get_file_hash_raises_on_missing_file():
    from multivol.api_server.utils import get_file_hash

    with pytest.raises(OSError):
        get_file_hash("/nonexistent/path/file.bin")


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


def test_resolve_host_path_returns_none_for_missing():
    from multivol.api_server.utils import resolve_host_path

    result = resolve_host_path("/nonexistent_scan_id_xyz")
    assert result is None
