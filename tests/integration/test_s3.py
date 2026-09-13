"""Интеграционные тесты ``S3Storage`` против MinIO.

Запускается, только если в окружении заданы ``S3_ENDPOINT``, ``S3_ACCESS_KEY``
и ``S3_SECRET_KEY`` (MinIO из ``docker-compose``). Иначе — skip.
"""

from __future__ import annotations

import os
import uuid

import pytest

from markdown_gost.storage.base import NotFoundError
from markdown_gost.storage.s3 import S3Storage

pytestmark = pytest.mark.integration


def _env_or_skip(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        pytest.skip(f"{name} not set; skipping S3 integration test")
    return value


@pytest.fixture(scope="module")
def s3_bucket() -> str:
    return os.environ.get("S3_BUCKET", "markdown-gost")


@pytest.fixture(scope="module")
def s3_client(s3_bucket: str):
    endpoint = _env_or_skip("S3_ENDPOINT")
    access = _env_or_skip("S3_ACCESS_KEY")
    secret = _env_or_skip("S3_SECRET_KEY")
    region = os.environ.get("S3_REGION") or "us-east-1"
    boto3 = pytest.importorskip("boto3")
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access,
        aws_secret_access_key=secret,
        region_name=region,
    )
    try:
        client.head_bucket(Bucket=s3_bucket)
    except Exception:
        try:
            client.create_bucket(Bucket=s3_bucket)
        except Exception as exc:
            pytest.skip(f"cannot prepare bucket {s3_bucket!r}: {exc}")
    return client


@pytest.fixture
def s3_storage(s3_client, s3_bucket: str) -> S3Storage:
    return S3Storage(bucket=s3_bucket, client=s3_client)


def _put(client, bucket: str, key: str, data: bytes) -> None:
    client.put_object(Bucket=bucket, Key=key, Body=data)


def test_fetch_uploaded_object(s3_client, s3_bucket: str, s3_storage: S3Storage):
    key = f"md2gost-test/{uuid.uuid4().hex}.bin"
    payload = b"integration-payload"
    _put(s3_client, s3_bucket, key, payload)
    try:
        assert s3_storage.fetch(key) == payload
    finally:
        s3_client.delete_object(Bucket=s3_bucket, Key=key)


def test_fetch_limited_with_stat_returns_same_response_metadata(
    s3_client, s3_bucket: str, s3_storage: S3Storage
):
    key = f"md2gost-test/{uuid.uuid4().hex}.png"
    payload = b"integration-payload"
    s3_client.put_object(
        Bucket=s3_bucket,
        Key=key,
        Body=payload,
        ContentType="image/png",
    )
    try:
        data, stat = s3_storage.fetch_limited_with_stat(key, len(payload))

        assert data == payload
        assert stat.etag is not None
        assert stat.last_modified is not None
        assert stat.content_length == len(payload)
        assert stat.content_type == "image/png"
    finally:
        s3_client.delete_object(Bucket=s3_bucket, Key=key)


def test_fetch_missing_raises_not_found(s3_storage: S3Storage):
    key = f"md2gost-test/{uuid.uuid4().hex}-missing"
    with pytest.raises(NotFoundError):
        s3_storage.fetch(key)


def test_exists_roundtrip(s3_client, s3_bucket: str, s3_storage: S3Storage):
    key = f"md2gost-test/{uuid.uuid4().hex}.bin"
    assert s3_storage.exists(key) is False
    _put(s3_client, s3_bucket, key, b"x")
    try:
        assert s3_storage.exists(key) is True
    finally:
        s3_client.delete_object(Bucket=s3_bucket, Key=key)
