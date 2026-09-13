"""Unit tests for the import image handlers (T034 + T043).

Per-index ``img-N.<ext>`` names were replaced with flat content-addressable
32-hex ids: no extension or original archive name is exposed, and storage keys
are validated against ``^[0-9a-f]{32}$``.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from markdown_gost.import_.image_handler import (
    LocalImageHandler,
    PlacedImage,
    StorageImageHandler,
)

_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def _expected_id(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:32]


def test_local_handler_writes_flat_id_and_returns_prefixed_link(
    tmp_path: Path,
) -> None:
    src = tmp_path / "image1.png"
    src.write_bytes(b"\x89PNG-1")
    target_dir = tmp_path / "out_files"
    handler = LocalImageHandler(target_dir=target_dir, link_prefix="out_files")

    placed = handler.place(src)

    assert isinstance(placed, PlacedImage)
    assert _ID_RE.match(placed.image_id)
    assert placed.image_id == _expected_id(b"\x89PNG-1")
    assert placed.link == f"out_files/{placed.image_id}"
    # File is written under the id only — no extension, no original name.
    assert (target_dir / placed.image_id).read_bytes() == b"\x89PNG-1"
    assert not any(p.suffix for p in target_dir.iterdir())


def test_local_handler_different_bytes_yield_different_ids(tmp_path: Path) -> None:
    a = tmp_path / "a.png"
    a.write_bytes(b"a")
    b = tmp_path / "b.jpg"
    b.write_bytes(b"b")
    target_dir = tmp_path / "files"
    handler = LocalImageHandler(target_dir=target_dir, link_prefix="files")

    first = handler.place(a)
    second = handler.place(b)

    assert first.image_id != second.image_id
    assert first.link == f"files/{first.image_id}"
    assert second.link == f"files/{second.image_id}"
    assert (target_dir / first.image_id).exists()
    assert (target_dir / second.image_id).exists()


def test_local_handler_same_bytes_same_id(tmp_path: Path) -> None:
    a = tmp_path / "first.png"
    b = tmp_path / "second.jpg"
    a.write_bytes(b"identical")
    b.write_bytes(b"identical")
    handler = LocalImageHandler(target_dir=tmp_path / "out", link_prefix="out")

    first = handler.place(a)
    second = handler.place(b)

    assert first.image_id == second.image_id
    assert first.link == second.link


def test_local_handler_empty_prefix_returns_bare_id(tmp_path: Path) -> None:
    src = tmp_path / "x.png"
    src.write_bytes(b"x")
    handler = LocalImageHandler(target_dir=tmp_path / "imgs", link_prefix="")

    placed = handler.place(src)
    assert placed.link == placed.image_id
    assert _ID_RE.match(placed.link)


def test_local_handler_strips_trailing_slash_from_prefix(tmp_path: Path) -> None:
    src = tmp_path / "x.png"
    src.write_bytes(b"x")
    handler = LocalImageHandler(target_dir=tmp_path / "imgs", link_prefix="imgs/")

    placed = handler.place(src)
    assert placed.link == f"imgs/{placed.image_id}"


def test_storage_handler_uploads_with_prefix_and_flat_id(tmp_path: Path) -> None:
    src = tmp_path / "image.jpg"
    src.write_bytes(b"\xff\xd8\xff")

    class _StubStorage:
        def __init__(self) -> None:
            self.puts: list[tuple[str, bytes]] = []

        def put(self, key: str, data: bytes) -> None:
            self.puts.append((key, data))

        def fetch(self, src: str) -> bytes:  # pragma: no cover
            raise NotImplementedError

        def exists(self, src: str) -> bool:  # pragma: no cover
            return False

    storage = _StubStorage()
    handler = StorageImageHandler(storage=storage, prefix="job-42/images")

    placed = handler.place(src)

    assert _ID_RE.match(placed.image_id)
    assert placed.image_id == _expected_id(b"\xff\xd8\xff")
    assert placed.link == f"job-42/images/{placed.image_id}"
    assert storage.puts == [(placed.link, b"\xff\xd8\xff")]


def test_storage_handler_empty_prefix_keeps_bare_id(tmp_path: Path) -> None:
    src = tmp_path / "image.png"
    src.write_bytes(b"x")

    class _StubStorage:
        def __init__(self) -> None:
            self.puts: list[tuple[str, bytes]] = []

        def put(self, key: str, data: bytes) -> None:
            self.puts.append((key, data))

        def fetch(self, src: str) -> bytes:  # pragma: no cover
            raise NotImplementedError

        def exists(self, src: str) -> bool:  # pragma: no cover
            return False

    storage = _StubStorage()
    handler = StorageImageHandler(storage=storage, prefix="")

    placed = handler.place(src)
    assert placed.link == placed.image_id
    assert storage.puts == [(placed.image_id, b"x")]


def test_storage_handler_strips_slashes_from_prefix(tmp_path: Path) -> None:
    src = tmp_path / "image.png"
    src.write_bytes(b"x")

    class _StubStorage:
        def __init__(self) -> None:
            self.puts: list[tuple[str, bytes]] = []

        def put(self, key: str, data: bytes) -> None:
            self.puts.append((key, data))

        def fetch(self, src: str) -> bytes:  # pragma: no cover
            raise NotImplementedError

        def exists(self, src: str) -> bool:  # pragma: no cover
            return False

    storage = _StubStorage()
    handler = StorageImageHandler(storage=storage, prefix="/a/b/")

    placed = handler.place(src)
    assert placed.link == f"a/b/{placed.image_id}"
    assert storage.puts == [(placed.link, b"x")]
