"""Storage интерфейс для подгрузки бинарных ресурсов (картинок).

Два режима использования:

- CLI/локально — :class:`FilesystemStorage`, ``src`` в markdown — путь
  относительно директории ``.md`` (или абсолютный путь).
- Сервис/хостинг — собственная реализация протокола :class:`Storage`
  (например, поверх S3-совместимого хранилища), ``src`` в markdown —
  ключ объекта в настроенном бакете.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable


class StorageError(RuntimeError):
    """Базовая ошибка storage: ресурс не найден / битая ссылка / I/O."""


class NotFoundError(StorageError):
    """Ресурс по ``src`` не найден."""


@dataclass(frozen=True)
class StorageStat:
    """Cache-relevant metadata for a binary storage object."""

    etag: str | None = None
    last_modified: datetime | None = None
    content_length: int | None = None
    content_type: str | None = None
    version: str | None = None


@runtime_checkable
class Storage(Protocol):
    """Источник бинарных данных, разрешаемый по строковой ссылке."""

    def fetch(self, src: str) -> bytes:  # pragma: no cover - Protocol
        """Прочитать содержимое. Бросает :class:`StorageError`."""
        ...

    def fetch_limited(
        self, src: str, max_bytes: int
    ) -> bytes:  # pragma: no cover - Protocol
        """Прочитать не больше ``max_bytes`` или бросить :class:`StorageError`."""
        ...

    def fetch_limited_with_stat(
        self, src: str, max_bytes: int
    ) -> tuple[bytes, StorageStat]:  # pragma: no cover - Protocol
        """Bounded read with metadata from the same storage response."""
        ...

    def exists(self, src: str) -> bool:  # pragma: no cover - Protocol
        """Существует ли ``src``. На отсутствии возвращает ``False``."""
        ...

    def stat(self, src: str) -> StorageStat:  # pragma: no cover - Protocol
        """Вернуть cache metadata. Бросает :class:`StorageError`."""
        ...

    def put(self, key: str, data: bytes) -> None:  # pragma: no cover - Protocol
        """Записать ``data`` под ключом ``key``. Бросает :class:`StorageError`."""
        ...
