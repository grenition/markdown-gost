"""Storage: локальная ФС по умолчанию; бэкенды-хранилищ подключаются инъекцией.

Библиотека поставляет только :class:`FilesystemStorage`. Объектные хранилища
(S3-совместимые и т.п.) — забота интегрирующего сервиса: реализуйте протокол
:class:`Storage` и передайте реализацию в конвертацию/импорт/превью.
"""

from __future__ import annotations

import os
from pathlib import Path

from .base import NotFoundError, Storage, StorageError, StorageStat
from .fs import FilesystemStorage

__all__ = [
    "FilesystemStorage",
    "NotFoundError",
    "Storage",
    "StorageError",
    "StorageStat",
    "get_storage",
]


def get_storage(default_base_dir: Path | str | None = None) -> Storage:
    """Собрать storage по ENV.

    ``STORAGE_BACKEND=fs`` (по умолчанию): :class:`FilesystemStorage`.
    Корень — ``STORAGE_FS_ROOT`` или ``default_base_dir``.

    Любое другое значение — ошибка: библиотека не поставляет бэкенды
    объектных хранилищ. Интегрирующий сервис реализует протокол
    :class:`Storage` и передаёт реализацию явно.
    """

    backend = os.environ.get("STORAGE_BACKEND", "fs").lower()

    if backend == "fs":
        root = os.environ.get("STORAGE_FS_ROOT") or default_base_dir
        return FilesystemStorage(base_dir=root)

    raise StorageError(
        f"unknown STORAGE_BACKEND: {backend!r}; the library ships filesystem "
        "storage only — inject a custom Storage implementation for object stores"
    )
