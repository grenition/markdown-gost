"""Юнит-тесты ``FilesystemStorage`` (T019)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from markdown_gost.storage.base import NotFoundError
from markdown_gost.storage.fs import FilesystemStorage


def test_fetch_relative_with_base_dir(tmp_path: Path):
    (tmp_path / "img.png").write_bytes(b"\x89PNGfake")
    s = FilesystemStorage(base_dir=tmp_path)
    assert s.fetch("img.png") == b"\x89PNGfake"


def test_fetch_relative_subdir(tmp_path: Path):
    sub = tmp_path / "assets"
    sub.mkdir()
    (sub / "a.png").write_bytes(b"x")
    s = FilesystemStorage(base_dir=tmp_path)
    assert s.fetch("assets/a.png") == b"x"


def test_fetch_absolute_path(tmp_path: Path):
    file = tmp_path / "abs.bin"
    file.write_bytes(b"data")
    s = FilesystemStorage(base_dir=tmp_path / "other")
    assert s.fetch(str(file)) == b"data"


def test_missing_file_raises_not_found(tmp_path: Path):
    s = FilesystemStorage(base_dir=tmp_path)
    with pytest.raises(NotFoundError):
        s.fetch("missing.png")


def test_exists_true_for_present_file(tmp_path: Path):
    (tmp_path / "x.bin").write_bytes(b"x")
    s = FilesystemStorage(base_dir=tmp_path)
    assert s.exists("x.bin") is True


def test_exists_false_for_missing_file(tmp_path: Path):
    s = FilesystemStorage(base_dir=tmp_path)
    assert s.exists("nope.bin") is False


def test_exists_false_for_directory(tmp_path: Path):
    (tmp_path / "sub").mkdir()
    s = FilesystemStorage(base_dir=tmp_path)
    assert s.exists("sub") is False


def test_no_base_dir_uses_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "y.bin").write_bytes(b"y")
    monkeypatch.chdir(tmp_path)
    s = FilesystemStorage()
    assert s.fetch("y.bin") == b"y"


def test_stat_returns_cache_metadata(tmp_path: Path) -> None:
    (tmp_path / "img.png").write_bytes(b"\x89PNGfake")
    s = FilesystemStorage(base_dir=tmp_path)

    stat = s.stat("img.png")

    assert stat.etag is not None
    assert stat.etag.startswith('W/"')
    assert stat.last_modified is not None
    assert stat.content_length == 8
    assert stat.content_type == "image/png"


def test_same_size_same_mtime_replacement_has_distinct_identity(tmp_path: Path) -> None:
    first = tmp_path / "first.bmp"
    second = tmp_path / "second.bmp"
    first.write_bytes(b"first")
    second.write_bytes(b"other")
    timestamp = 1_700_000_000_000_000_000
    os.utime(first, ns=(timestamp, timestamp))
    os.utime(second, ns=(timestamp, timestamp))
    storage = FilesystemStorage(base_dir=tmp_path)

    first_stat = storage.stat("first.bmp")
    second.replace(first)
    _data, second_stat = storage.fetch_limited_with_stat("first.bmp", 5)

    assert first_stat != second_stat


def test_stat_missing_file_raises_not_found(tmp_path: Path) -> None:
    s = FilesystemStorage(base_dir=tmp_path)
    with pytest.raises(NotFoundError):
        s.stat("missing.png")
