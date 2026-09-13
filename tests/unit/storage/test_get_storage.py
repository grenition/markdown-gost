"""Юнит-тесты фабрики ``get_storage`` (T019)."""

from __future__ import annotations

from pathlib import Path

import pytest

from markdown_gost.storage import (
    FilesystemStorage,
    S3Storage,
    StorageError,
    get_storage,
)

_S3_VARS = (
    "STORAGE_BACKEND",
    "STORAGE_FS_ROOT",
    "S3_BUCKET",
    "S3_ENDPOINT",
    "S3_ACCESS_KEY",
    "S3_SECRET_KEY",
    "S3_REGION",
)


def _clear(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _S3_VARS:
        monkeypatch.delenv(var, raising=False)


def test_default_is_fs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _clear(monkeypatch)
    storage = get_storage(default_base_dir=tmp_path)
    assert isinstance(storage, FilesystemStorage)
    assert storage.base_dir == tmp_path


def test_storage_fs_root_overrides_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _clear(monkeypatch)
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.setenv("STORAGE_FS_ROOT", str(other))
    storage = get_storage(default_base_dir=tmp_path)
    assert isinstance(storage, FilesystemStorage)
    assert storage.base_dir == other


def test_s3_backend(monkeypatch: pytest.MonkeyPatch):
    _clear(monkeypatch)
    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    monkeypatch.setenv("S3_BUCKET", "markdown-gost")
    monkeypatch.setenv("S3_ENDPOINT", "http://localhost:9000")
    monkeypatch.setenv("S3_ACCESS_KEY", "k")
    monkeypatch.setenv("S3_SECRET_KEY", "s")
    storage = get_storage()
    assert isinstance(storage, S3Storage)
    assert storage.bucket == "markdown-gost"


def test_s3_without_required_env_raises(monkeypatch: pytest.MonkeyPatch):
    _clear(monkeypatch)
    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    with pytest.raises(StorageError):
        get_storage()


def test_unknown_backend_raises(monkeypatch: pytest.MonkeyPatch):
    _clear(monkeypatch)
    monkeypatch.setenv("STORAGE_BACKEND", "redis")
    with pytest.raises(StorageError):
        get_storage()
