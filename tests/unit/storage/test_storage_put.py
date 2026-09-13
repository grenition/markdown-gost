"""Unit tests for ``Storage.put`` on the filesystem backend (T034)."""

from __future__ import annotations

from pathlib import Path

import pytest

from markdown_gost.storage.base import StorageError
from markdown_gost.storage.fs import FilesystemStorage


def test_fs_put_writes_relative_path(tmp_path: Path) -> None:
    s = FilesystemStorage(base_dir=tmp_path)
    s.put("a.bin", b"hello")
    assert (tmp_path / "a.bin").read_bytes() == b"hello"


def test_fs_put_creates_intermediate_dirs(tmp_path: Path) -> None:
    s = FilesystemStorage(base_dir=tmp_path)
    s.put("nested/deep/x.png", b"\x89PNG")
    assert (tmp_path / "nested" / "deep" / "x.png").read_bytes() == b"\x89PNG"


def test_fs_put_absolute_path(tmp_path: Path) -> None:
    s = FilesystemStorage(base_dir=tmp_path / "other")
    target = tmp_path / "abs.bin"
    s.put(str(target), b"data")
    assert target.read_bytes() == b"data"


def test_fs_put_failure_raises_storage_error(tmp_path: Path) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_bytes(b"file-not-dir")
    s = FilesystemStorage(base_dir=tmp_path)
    with pytest.raises(StorageError):
        s.put("blocker/child.bin", b"x")
