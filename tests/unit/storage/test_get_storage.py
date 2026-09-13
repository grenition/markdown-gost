"""Юнит-тесты фабрики ``get_storage`` (T019)."""

from __future__ import annotations

from pathlib import Path

import pytest

from markdown_gost.storage import (
    FilesystemStorage,
    StorageError,
    get_storage,
)

_ENV_VARS = (
    "STORAGE_BACKEND",
    "STORAGE_FS_ROOT",
)


def _clear(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _ENV_VARS:
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


def test_object_store_backends_are_not_builtin(monkeypatch: pytest.MonkeyPatch):
    _clear(monkeypatch)
    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    with pytest.raises(StorageError, match="inject a custom Storage"):
        get_storage()


def test_unknown_backend_raises(monkeypatch: pytest.MonkeyPatch):
    _clear(monkeypatch)
    monkeypatch.setenv("STORAGE_BACKEND", "redis")
    with pytest.raises(StorageError):
        get_storage()
