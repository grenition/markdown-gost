"""Storage: либо локальная ФС, либо S3 — выбирается ENV ``STORAGE_BACKEND``."""

from __future__ import annotations

import os
from pathlib import Path

from .base import NotFoundError, Storage, StorageError, StorageStat
from .fs import FilesystemStorage
from .s3 import S3Storage

__all__ = [
    "FilesystemStorage",
    "NotFoundError",
    "S3Storage",
    "Storage",
    "StorageError",
    "StorageStat",
    "get_storage",
]


def get_storage(default_base_dir: Path | str | None = None) -> Storage:
    """Собрать storage по ENV.

    - ``STORAGE_BACKEND=fs`` (по умолчанию): :class:`FilesystemStorage`.
      Корень — ``STORAGE_FS_ROOT`` или ``default_base_dir``.
    - ``STORAGE_BACKEND=s3``: :class:`S3Storage`. Требует ``S3_BUCKET``,
      ``S3_ENDPOINT``, ``S3_ACCESS_KEY``, ``S3_SECRET_KEY``;
      ``S3_REGION`` — опционально.
    """

    backend = os.environ.get("STORAGE_BACKEND", "fs").lower()

    if backend == "fs":
        root = os.environ.get("STORAGE_FS_ROOT") or default_base_dir
        return FilesystemStorage(base_dir=root)

    if backend == "s3":
        try:
            bucket = os.environ["S3_BUCKET"]
            endpoint = os.environ["S3_ENDPOINT"]
            access = os.environ["S3_ACCESS_KEY"]
            secret = os.environ["S3_SECRET_KEY"]
        except KeyError as exc:
            raise StorageError(
                "STORAGE_BACKEND=s3 requires S3_BUCKET, S3_ENDPOINT, "
                "S3_ACCESS_KEY, S3_SECRET_KEY"
            ) from exc
        force_path = os.environ.get("S3_FORCE_PATH_STYLE", "").strip().lower()
        addressing_style = "path" if force_path in {"1", "true", "yes", "on"} else None
        return S3Storage(
            bucket=bucket,
            endpoint_url=endpoint,
            access_key=access,
            secret_key=secret,
            region=os.environ.get("S3_REGION"),
            addressing_style=addressing_style,
        )

    raise StorageError(f"unknown STORAGE_BACKEND: {backend!r}")
