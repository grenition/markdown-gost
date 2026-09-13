"""Place media extracted by pandoc and return the markdown link string.

T043 switched the naming scheme: every image is identified by a flat 32-hex
content hash, written *without an extension* and without the original archive
name. The platform side (T034) validates storage keys against
``^[0-9a-f]{32}$`` and rejected the previous ``img-N.<ext>`` names; the hash
buys natural deduplication too (re-importing the same source yields the same
keys, so autosave doesn't accumulate duplicates).

Two backends mirror the rest of the codebase:

- :class:`LocalImageHandler` writes bytes to a directory on disk and yields
  paths the CLI can resolve relative to the produced markdown.
- :class:`StorageImageHandler` uploads bytes through the configured
  :class:`~markdown_gost.storage.Storage` and yields the resulting storage key the
  API caller can fetch back.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from markdown_gost.storage import Storage


@dataclass(frozen=True)
class PlacedImage:
    """Result of placing an image: the 32-hex id and the full link/key."""

    image_id: str
    link: str


_ID_LENGTH = 32


def _content_id(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:_ID_LENGTH]


class ImageHandler(ABC):
    @abstractmethod
    def place(self, src_path: Path) -> PlacedImage:
        """Place ``src_path`` and return the id + markdown link to write back."""


class LocalImageHandler(ImageHandler):
    def __init__(self, target_dir: Path, link_prefix: str = "") -> None:
        self._target_dir = target_dir
        self._link_prefix = link_prefix.rstrip("/")

    def place(self, src_path: Path) -> PlacedImage:
        data = src_path.read_bytes()
        image_id = _content_id(data)
        self._target_dir.mkdir(parents=True, exist_ok=True)
        (self._target_dir / image_id).write_bytes(data)
        link = f"{self._link_prefix}/{image_id}" if self._link_prefix else image_id
        return PlacedImage(image_id=image_id, link=link)


class StorageImageHandler(ImageHandler):
    def __init__(self, storage: Storage, prefix: str) -> None:
        self._storage = storage
        self._prefix = prefix.strip("/")

    def place(self, src_path: Path) -> PlacedImage:
        data = src_path.read_bytes()
        image_id = _content_id(data)
        key = f"{self._prefix}/{image_id}" if self._prefix else image_id
        self._storage.put(key, data)
        return PlacedImage(image_id=image_id, link=key)


__all__ = [
    "ImageHandler",
    "LocalImageHandler",
    "PlacedImage",
    "StorageImageHandler",
]
