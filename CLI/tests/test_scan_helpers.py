"""Tests for pure helper functions in routes/scan.py."""


def test_paginate_data_list_returns_slice():
    from multivol.api_server.routes.scan import _paginate_data

    data = list(range(10))
    assert _paginate_data(data, limit=3, offset=0) == [0, 1, 2]
    assert _paginate_data(data, limit=3, offset=3) == [3, 4, 5]
    assert _paginate_data(data, limit=100, offset=8) == [8, 9]


def test_paginate_data_dict_returned_unchanged():
    from multivol.api_server.routes.scan import _paginate_data

    data = {"key": "value"}
    assert _paginate_data(data, limit=5, offset=0) is data


def test_paginate_data_zero_limit_returns_all():
    from multivol.api_server.routes.scan import _paginate_data

    data = [1, 2, 3]
    assert _paginate_data(data, limit=0, offset=0) == [1, 2, 3]


def test_build_fs_tree_empty_dir(tmp_path):
    from multivol.api_server.routes.scan import build_fs_tree

    result = build_fs_tree(str(tmp_path))
    assert isinstance(result, list)
    assert len(result) == 1
    root = result[0]
    assert root["name"] == "/"
    assert root["type"] == "directory"
    assert root["children"] == []


def test_build_fs_tree_with_files(tmp_path):
    from multivol.api_server.routes.scan import build_fs_tree

    (tmp_path / "file_a.txt").write_text("hello")
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    (subdir / "file_b.txt").write_text("world")

    result = build_fs_tree(str(tmp_path))
    root = result[0]
    names = {child["name"] for child in root["children"]}
    assert "file_a.txt" in names
    assert "subdir" in names

    # subdir should contain file_b.txt
    subdir_node = next(c for c in root["children"] if c["name"] == "subdir")
    assert subdir_node["type"] == "directory"
    child_names = {c["name"] for c in subdir_node["children"]}
    assert "file_b.txt" in child_names


def test_build_fs_tree_file_has_size(tmp_path):
    from multivol.api_server.routes.scan import build_fs_tree

    content = b"hello world"
    (tmp_path / "sample.bin").write_bytes(content)

    result = build_fs_tree(str(tmp_path))
    root = result[0]
    file_node = next(c for c in root["children"] if c["name"] == "sample.bin")
    assert file_node["size"] == len(content)
