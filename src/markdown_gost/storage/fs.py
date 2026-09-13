"""Файловая реализация :class:`Storage`.

Относительные пути резолвятся от ``base_dir`` (обычно — директория исходного
``.md``). Абсолютные пути берутся как есть.
"""

from __future__ import annotations

import mimetypes
import os
from datetime import UTC, datetime
from pathlib import Path

from .base import NotFoundError, StorageError, StorageStat


class FilesystemStorage:
    """Чтение бинарей с локальной ФС."""

    def __init__(self, base_dir: Path | str | None = None) -> None:
        self._base_dir: Path | None = (
            Path(base_dir) if base_dir is not None else None
        )

    @property
    def base_dir(self) -> Path | None:
        return self._base_dir

    def _resolve(self, src: str) -> Path:
        path = Path(src)
        if path.is_absolute() or self._base_dir is None:
            return path
        return self._base_dir / path

    def fetch(self, src: str) -> bytes:
        path = self._resolve(src)
        try:
            return path.read_bytes()
        except FileNotFoundError as exc:
            raise NotFoundError(f"file not found: {src!r} (resolved: {path})") from exc
        except OSError as exc:
            raise StorageError(f"cannot read {src!r}: {exc}") from exc

    def fetch_limited(self, src: str, max_bytes: int) -> bytes:
        data, _stat = self.fetch_limited_with_stat(src, max_bytes)
        return data

    def fetch_limited_with_stat(
        self, src: str, max_bytes: int
    ) -> tuple[bytes, StorageStat]:
        path = self._resolve(src)
        try:
            with path.open("rb") as stream:
                data = stream.read(max_bytes + 1)
                stat = os.fstat(stream.fileno())
        except FileNotFoundError as exc:
            raise NotFoundError(f"file not found: {src!r} (resolved: {path})") from exc
        except OSError as exc:
            raise StorageError(f"cannot read {src!r}: {exc}") from exc
        if len(data) > max_bytes:
            raise StorageError(f"file exceeds {max_bytes} bytes: {src!r}")
        return data, _storage_stat(path, stat)

    def exists(self, src: str) -> bool:
        return self._resolve(src).is_file()

    def stat(self, src: str) -> StorageStat:
        path = self._resolve(src)
        try:
            stat = path.stat()
        except FileNotFoundError as exc:
            raise NotFoundError(f"file not found: {src!r} (resolved: {path})") from exc
        except OSError as exc:
            raise StorageError(f"cannot stat {src!r}: {exc}") from exc
        if not path.is_file():
            raise NotFoundError(f"file not found: {src!r} (resolved: {path})")
        return _storage_stat(path, stat)

    def put(self, key: str, data: bytes) -> None:
        path = self._resolve(key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        except OSError as exc:
            raise StorageError(f"cannot write {key!r}: {exc}") from exc


def _storage_stat(path: Path, stat: os.stat_result) -> StorageStat:
    content_type, _encoding = mimetypes.guess_type(path.name)
    return StorageStat(
        etag=f'W/"{stat.st_mtime_ns:x}-{stat.st_size:x}"',
        last_modified=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
        content_length=stat.st_size,
        content_type=content_type,
        version=f"{stat.st_dev:x}-{stat.st_ino:x}-{stat.st_ctime_ns:x}",
    )
