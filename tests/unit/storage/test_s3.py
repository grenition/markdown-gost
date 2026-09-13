"""Юнит-тесты ``S3Storage`` со стаб-клиентом (T019).

Полноценная проверка против реального S3 — в ``tests/integration/test_s3.py``.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime

import pytest

from markdown_gost.storage.base import NotFoundError, StorageError
from markdown_gost.storage.s3 import S3Storage


class _ClientError(Exception):
    """Минимальная имитация ``botocore.exceptions.ClientError``."""

    def __init__(self, status: int, code: str) -> None:
        super().__init__(f"{code} ({status})")
        self.response = {
            "Error": {"Code": code},
            "ResponseMetadata": {"HTTPStatusCode": status},
        }


class _StubClient:
    def __init__(
        self,
        mapping: dict[tuple[str, str], bytes],
        *,
        head_metadata: dict[tuple[str, str], dict[str, object]] | None = None,
        get_metadata: dict[tuple[str, str], dict[str, object]] | None = None,
    ) -> None:
        self._mapping = mapping
        self._head_metadata = head_metadata or {}
        self._get_metadata = get_metadata or {}
        self.get_calls: list[tuple[str, str]] = []
        self.head_calls: list[tuple[str, str]] = []

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, object]:  # noqa: N803
        self.get_calls.append((Bucket, Key))
        if (Bucket, Key) not in self._mapping:
            raise _ClientError(404, "NoSuchKey")
        response = dict(self._get_metadata.get((Bucket, Key), {}))
        response["Body"] = io.BytesIO(self._mapping[(Bucket, Key)])
        return response

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, object]:  # noqa: N803
        self.head_calls.append((Bucket, Key))
        if (Bucket, Key) not in self._mapping:
            raise _ClientError(404, "404")
        return self._head_metadata.get((Bucket, Key), {})


def test_fetch_returns_bytes():
    client = _StubClient({("b", "img.png"): b"data"})
    s = S3Storage(bucket="b", client=client)
    assert s.fetch("img.png") == b"data"
    assert client.get_calls == [("b", "img.png")]


def test_fetch_limited_rejects_oversized_body() -> None:
    storage = S3Storage(bucket="b", client=_StubClient({("b", "img.png"): b"data"}))

    with pytest.raises(StorageError):
        storage.fetch_limited("img.png", 3)


def test_fetch_limited_with_stat_uses_get_response_metadata() -> None:
    modified = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
    metadata = {
        "ETag": '"etag"',
        "LastModified": modified,
        "ContentLength": 4,
        "ContentType": "image/png",
        "VersionId": "version-1",
    }
    storage = S3Storage(
        bucket="b",
        client=_StubClient(
            {("b", "img.png"): b"data"},
            get_metadata={("b", "img.png"): metadata},
        ),
    )

    data, stat = storage.fetch_limited_with_stat("img.png", 4)

    assert data == b"data"
    assert stat.etag == '"etag"'
    assert stat.last_modified == modified
    assert stat.content_length == 4
    assert stat.content_type == "image/png"
    assert stat.version == "version-1"


def test_fetch_limited_wraps_body_read_failure() -> None:
    class _BrokenBody:
        def read(self, _: int) -> bytes:
            raise OSError("stream failed")

        def close(self) -> None:
            pass

    class _BrokenClient:
        def get_object(self, **_: object) -> dict[str, object]:
            return {"Body": _BrokenBody()}

    storage = S3Storage(bucket="b", client=_BrokenClient())

    with pytest.raises(StorageError):
        storage.fetch_limited("img.png", 3)


def test_fetch_limited_rejects_body_ignoring_read_limit() -> None:
    class _GreedyBody:
        def read(self, _: int) -> bytes:
            return b"oversized"

        def close(self) -> None:
            pass

    class _GreedyClient:
        def get_object(self, **_: object) -> dict[str, object]:
            return {"Body": _GreedyBody()}

    storage = S3Storage(bucket="b", client=_GreedyClient())

    with pytest.raises(StorageError):
        storage.fetch_limited("img.png", 3)


def test_fetch_strips_leading_slash():
    client = _StubClient({("b", "dir/x"): b"y"})
    s = S3Storage(bucket="b", client=client)
    assert s.fetch("/dir/x") == b"y"


def test_fetch_missing_raises_not_found():
    s = S3Storage(bucket="b", client=_StubClient({}))
    with pytest.raises(NotFoundError):
        s.fetch("img.png")


def test_exists_true():
    s = S3Storage(bucket="b", client=_StubClient({("b", "k"): b"x"}))
    assert s.exists("k") is True


def test_exists_false():
    s = S3Storage(bucket="b", client=_StubClient({}))
    assert s.exists("k") is False


def test_stat_returns_head_object_metadata() -> None:
    modified = datetime(2026, 7, 8, 10, 20, 30, tzinfo=UTC)
    client = _StubClient(
        {("b", "img.png"): b"data"},
        head_metadata={
            ("b", "img.png"): {
                "ETag": '"abc123"',
                "LastModified": modified,
                "ContentLength": 4,
                "ContentType": "image/png",
            }
        },
    )
    s = S3Storage(bucket="b", client=client)

    stat = s.stat("/img.png")

    assert client.head_calls == [("b", "img.png")]
    assert stat.etag == '"abc123"'
    assert stat.last_modified == modified
    assert stat.content_length == 4
    assert stat.content_type == "image/png"


def test_stat_missing_raises_not_found() -> None:
    s = S3Storage(bucket="b", client=_StubClient({}))
    with pytest.raises(NotFoundError):
        s.stat("missing.png")


def test_addressing_style_propagates_to_boto3(monkeypatch):
    calls: dict[str, object] = {}

    class _FakeConfig:
        def __init__(self, **kwargs: object) -> None:
            calls["config_kwargs"] = kwargs

    class _FakeBoto3:
        @staticmethod
        def client(service: str, **kwargs: object):
            calls["service"] = service
            calls["client_kwargs"] = kwargs
            return object()

    import sys
    import types

    botocore_mod = types.ModuleType("botocore")
    botocore_config_mod = types.ModuleType("botocore.config")
    botocore_config_mod.Config = _FakeConfig  # type: ignore[attr-defined]
    botocore_mod.config = botocore_config_mod  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "boto3", _FakeBoto3())
    monkeypatch.setitem(sys.modules, "botocore", botocore_mod)
    monkeypatch.setitem(sys.modules, "botocore.config", botocore_config_mod)

    S3Storage(
        bucket="b",
        endpoint_url="http://s3.example",
        access_key="a",
        secret_key="s",
        region="us-east-1",
        addressing_style="path",
    )

    assert calls["service"] == "s3"
    assert calls["config_kwargs"] == {
        "request_checksum_calculation": "when_required",
        "response_checksum_validation": "when_required",
        "s3": {"addressing_style": "path"},
    }
    client_kwargs = calls["client_kwargs"]
    assert isinstance(client_kwargs, dict)
    assert isinstance(client_kwargs["config"], _FakeConfig)


def test_checksum_calculation_when_required_without_addressing_style(monkeypatch):
    """botocore ≥1.36 default ломает совместимость с не-AWS S3 (XAmzContentSHA256Mismatch).

    Без явного addressing_style клиент всё равно должен получить
    `request_checksum_calculation="when_required"` и
    `response_checksum_validation="when_required"`.
    """

    calls: dict[str, object] = {}

    class _FakeConfig:
        def __init__(self, **kwargs: object) -> None:
            calls["config_kwargs"] = kwargs

    class _FakeBoto3:
        @staticmethod
        def client(service: str, **kwargs: object):
            calls["client_kwargs"] = kwargs
            return object()

    import sys
    import types

    botocore_config_mod = types.ModuleType("botocore.config")
    botocore_config_mod.Config = _FakeConfig  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "boto3", _FakeBoto3())
    monkeypatch.setitem(sys.modules, "botocore.config", botocore_config_mod)

    S3Storage(
        bucket="b",
        endpoint_url="http://s3.example",
        access_key="a",
        secret_key="s",
    )

    assert calls["config_kwargs"] == {
        "request_checksum_calculation": "when_required",
        "response_checksum_validation": "when_required",
    }
    assert "s3" not in calls["config_kwargs"]


def test_get_storage_enables_path_style_from_env(monkeypatch):
    captured: dict[str, object] = {}

    from markdown_gost import storage as storage_pkg

    def _fake_init(self, **kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        self._bucket = kwargs["bucket"]

    monkeypatch.setattr(storage_pkg.S3Storage, "__init__", _fake_init)
    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    monkeypatch.setenv("S3_BUCKET", "b")
    monkeypatch.setenv("S3_ENDPOINT", "http://s3.example")
    monkeypatch.setenv("S3_ACCESS_KEY", "a")
    monkeypatch.setenv("S3_SECRET_KEY", "s")
    monkeypatch.setenv("S3_FORCE_PATH_STYLE", "true")

    storage_pkg.get_storage()

    assert captured["addressing_style"] == "path"


def test_get_storage_no_addressing_style_when_env_unset(monkeypatch):
    captured: dict[str, object] = {}

    from markdown_gost import storage as storage_pkg

    def _fake_init(self, **kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        self._bucket = kwargs["bucket"]

    monkeypatch.setattr(storage_pkg.S3Storage, "__init__", _fake_init)
    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    monkeypatch.setenv("S3_BUCKET", "b")
    monkeypatch.setenv("S3_ENDPOINT", "http://s3.example")
    monkeypatch.setenv("S3_ACCESS_KEY", "a")
    monkeypatch.setenv("S3_SECRET_KEY", "s")
    monkeypatch.delenv("S3_FORCE_PATH_STYLE", raising=False)

    storage_pkg.get_storage()

    assert captured["addressing_style"] is None


def test_unknown_error_propagates_as_storage_error():
    class _Broken:
        def get_object(self, **_: object) -> dict[str, object]:
            raise RuntimeError("network kaput")

        def head_object(self, **_: object) -> dict[str, object]:
            raise RuntimeError("network kaput")

    s = S3Storage(bucket="b", client=_Broken())
    with pytest.raises(StorageError):
        s.fetch("k")
