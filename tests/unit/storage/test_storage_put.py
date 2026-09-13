"""Unit tests for ``Storage.put`` on both filesystem and S3 backends (T034)."""

from __future__ import annotations

from pathlib import Path

import pytest

from markdown_gost.storage.base import StorageError
from markdown_gost.storage.fs import FilesystemStorage
from markdown_gost.storage.s3 import S3Storage


class _StubClient:
    def __init__(self) -> None:
        self.puts: list[tuple[str, str, bytes]] = []

    def put_object(self, *, Bucket: str, Key: str, Body: bytes) -> dict[str, object]:  # noqa: N803
        self.puts.append((Bucket, Key, Body))
        return {}


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


def test_s3_put_uses_client(tmp_path: Path) -> None:
    client = _StubClient()
    s = S3Storage(bucket="b", client=client)
    s.put("dir/x.png", b"payload")
    assert client.puts == [("b", "dir/x.png", b"payload")]


def test_s3_put_strips_leading_slash(tmp_path: Path) -> None:
    client = _StubClient()
    s = S3Storage(bucket="b", client=client)
    s.put("/dir/y.png", b"y")
    assert client.puts == [("b", "dir/y.png", b"y")]


def test_s3_put_client_error_wrapped() -> None:
    class _Broken:
        def put_object(self, **_: object) -> dict[str, object]:
            raise RuntimeError("network kaput")

    s = S3Storage(bucket="b", client=_Broken())
    with pytest.raises(StorageError):
        s.put("k", b"x")
