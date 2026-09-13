"""S3-совместимая реализация :class:`Storage`.

Хранилище конфигурируется одним бакетом; ``src`` в markdown — это просто
ключ объекта внутри бакета (например, ``images/cover.png``).

``boto3`` импортируется лениво, чтобы пакет работал без SDK, если S3 не
используется.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .base import NotFoundError, StorageError, StorageStat


class S3Storage:
    """Читает объекты из заранее настроенного бакета."""

    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        region: str | None = None,
        addressing_style: str | None = None,
        client: Any | None = None,
    ) -> None:
        self._bucket = bucket
        if client is not None:
            self._client = client
        else:
            try:
                import boto3  # type: ignore[import-untyped]
                from botocore.config import Config  # type: ignore[import-untyped]
            except ImportError as exc:
                raise StorageError(
                    "boto3 is required for S3Storage; install with `poetry add boto3`"
                ) from exc
            # botocore ≥1.36 changed default checksum behavior to `when_supported`,
            # которое добавляет `x-amz-content-sha256` / trailing checksum к каждому
            # PutObject. Это ломает совместимость с рядом S3-провайдеров (часть
            # российских хостеров, прокси, старые версии MinIO) — они отвечают
            # `XAmzContentSHA256Mismatch`. Возвращаем pre-1.36 поведение —
            # checksum считается только когда AWS его реально требует.
            config_kwargs: dict[str, object] = {
                "request_checksum_calculation": "when_required",
                "response_checksum_validation": "when_required",
            }
            if addressing_style:
                config_kwargs["s3"] = {"addressing_style": addressing_style}
            config = Config(**config_kwargs)
            self._client = boto3.client(
                "s3",
                endpoint_url=endpoint_url,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                region_name=region,
                config=config,
            )

    @property
    def bucket(self) -> str:
        return self._bucket

    def fetch(self, src: str) -> bytes:
        data, _response = self._fetch(src)
        return data

    def fetch_limited(self, src: str, max_bytes: int) -> bytes:
        data, _response = self._fetch(src, max_bytes=max_bytes)
        return data

    def fetch_limited_with_stat(
        self, src: str, max_bytes: int
    ) -> tuple[bytes, StorageStat]:
        data, response = self._fetch(src, max_bytes=max_bytes)
        return data, _stat_from_response(response)

    def _fetch(
        self, src: str, *, max_bytes: int | None = None
    ) -> tuple[bytes, dict[str, Any]]:
        key = src.lstrip("/")
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
        except Exception as exc:
            if _is_not_found_error(exc):
                raise NotFoundError(
                    f"s3 object not found: {self._bucket}/{key}"
                ) from exc
            raise StorageError(f"cannot read {src!r}: {exc}") from exc
        body = response["Body"]
        try:
            try:
                if max_bytes is None:
                    return bytes(body.read()), response
                chunks: list[bytes] = []
                remaining = max_bytes + 1
                while remaining:
                    chunk = bytes(body.read(remaining))
                    if not chunk:
                        break
                    if len(chunk) > remaining:
                        raise StorageError(
                            f"s3 object exceeds {max_bytes} bytes: {src!r}"
                        )
                    chunks.append(chunk)
                    remaining -= len(chunk)
                data = b"".join(chunks)
                if len(data) > max_bytes:
                    raise StorageError(
                        f"s3 object exceeds {max_bytes} bytes: {src!r}"
                    )
                return data, response
            finally:
                close = getattr(body, "close", None)
                if callable(close):
                    close()
        except StorageError:
            raise
        except Exception as exc:
            raise StorageError(f"cannot read {src!r}: {exc}") from exc

    def exists(self, src: str) -> bool:
        key = src.lstrip("/")
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
        except Exception as exc:
            if _is_not_found_error(exc):
                return False
            raise StorageError(f"cannot stat {src!r}: {exc}") from exc
        return True

    def stat(self, src: str) -> StorageStat:
        key = src.lstrip("/")
        try:
            response = self._client.head_object(Bucket=self._bucket, Key=key)
        except Exception as exc:
            if _is_not_found_error(exc):
                raise NotFoundError(
                    f"s3 object not found: {self._bucket}/{key}"
                ) from exc
            raise StorageError(f"cannot stat {src!r}: {exc}") from exc
        return _stat_from_response(response)

    def put(self, key: str, data: bytes) -> None:
        target = key.lstrip("/")
        try:
            self._client.put_object(Bucket=self._bucket, Key=target, Body=data)
        except Exception as exc:
            raise StorageError(f"cannot write {key!r}: {exc}") from exc


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _stat_from_response(response: dict[str, Any]) -> StorageStat:
    return StorageStat(
        etag=_string_or_none(response.get("ETag")),
        last_modified=_datetime_or_none(response.get("LastModified")),
        content_length=_int_or_none(response.get("ContentLength")),
        content_type=_string_or_none(response.get("ContentType")),
        version=_string_or_none(response.get("VersionId")),
    )


def _datetime_or_none(value: object) -> datetime | None:
    return value if isinstance(value, datetime) else None


def _int_or_none(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _is_not_found_error(exc: BaseException) -> bool:
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        error = response.get("Error") or {}
        code = str(error.get("Code", ""))
        if code in {"NoSuchKey", "NoSuchBucket", "404", "NotFound"}:
            return True
        status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if status == 404:
            return True
    return False
