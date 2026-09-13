"""DOCX → PDF conversion via unoserver (T018, ADR-0002).

The module talks to a long-running unoserver instance over XML-RPC. unoserver
keeps LibreOffice resident, so steady-state conversion is ~0.3–0.5 s. The first
request after start has to wait for LibreOffice to initialize — clients should
use :func:`wait_for_unoserver_ready` once at boot (e.g. behind ``/health``)
before serving traffic.

Connection model: XML-RPC ``ServerProxy`` is cheap; no pool is needed. We
re-create the proxy on each call and retry on transient socket / Fault errors,
which covers the "lazy reconnect if unoserver was restarted" case.
"""

from __future__ import annotations

import contextlib
import os
import socket
import time
import xmlrpc.client
from dataclasses import dataclass

from markdown_gost.metrics_compat import Histogram

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 2003
DEFAULT_RETRIES = 2
DEFAULT_PING_TIMEOUT = 1.0
DEFAULT_READY_TIMEOUT = 60.0
DEFAULT_READY_INTERVAL = 0.5

PDF_CONVERSION_DURATION = Histogram(
    "md2gost_pdf_conversion_duration_seconds",
    "Time spent converting a DOCX document to PDF via unoserver.",
    buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0),
)


class UnoserverError(RuntimeError):
    """Raised when unoserver is unreachable or returns an error."""


@dataclass(frozen=True)
class UnoserverSettings:
    host: str
    port: int

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"


def get_settings(
    host: str | None = None, port: int | None = None
) -> UnoserverSettings:
    """Resolve unoserver host/port from explicit args or env vars."""
    resolved_host = host or os.environ.get("UNOSERVER_HOST", DEFAULT_HOST)
    if port is not None:
        resolved_port = port
    else:
        resolved_port = int(os.environ.get("UNOSERVER_PORT", str(DEFAULT_PORT)))
    return UnoserverSettings(host=resolved_host, port=resolved_port)


def ping_unoserver(
    host: str | None = None,
    port: int | None = None,
    timeout: float = DEFAULT_PING_TIMEOUT,
) -> bool:
    """Return True if a TCP connection to unoserver succeeds within `timeout`."""
    settings = get_settings(host, port)
    try:
        with socket.create_connection(
            (settings.host, settings.port), timeout=timeout
        ):
            return True
    except OSError:
        return False


def wait_for_unoserver_ready(
    host: str | None = None,
    port: int | None = None,
    timeout: float = DEFAULT_READY_TIMEOUT,
    interval: float = DEFAULT_READY_INTERVAL,
) -> None:
    """Block until unoserver accepts TCP connections or `timeout` elapses.

    Raises :class:`UnoserverError` on timeout. Used by ``/health`` to gate the
    first 200 response on a real unoserver readiness check.
    """
    settings = get_settings(host, port)
    deadline = time.monotonic() + timeout
    last_error: OSError | None = None
    while True:
        try:
            with socket.create_connection(
                (settings.host, settings.port), timeout=DEFAULT_PING_TIMEOUT
            ):
                return
        except OSError as exc:
            last_error = exc
        if time.monotonic() >= deadline:
            raise UnoserverError(
                f"unoserver at {settings.url} not ready within {timeout:.1f}s"
                + (f": {last_error}" if last_error else "")
            )
        time.sleep(interval)


def _convert_once(docx_bytes: bytes, settings: UnoserverSettings) -> bytes:
    proxy = xmlrpc.client.ServerProxy(settings.url, allow_none=True)
    try:
        result = proxy.convert(None, xmlrpc.client.Binary(docx_bytes), None, "pdf", None)
    finally:
        with contextlib.suppress(Exception):
            transport = getattr(proxy, "_ServerProxy__transport", None)
            if transport is not None and hasattr(transport, "close"):
                transport.close()
    if result is None:
        raise UnoserverError("unoserver returned no data")
    if isinstance(result, xmlrpc.client.Binary):
        return result.data
    if isinstance(result, bytes | bytearray):
        return bytes(result)
    raise UnoserverError(f"unexpected unoserver response type: {type(result).__name__}")


def convert_to_pdf(
    docx_bytes: bytes,
    *,
    host: str | None = None,
    port: int | None = None,
    retries: int = DEFAULT_RETRIES,
) -> bytes:
    """Convert a DOCX byte string to PDF via unoserver.

    Retries on transient connection / XML-RPC errors so that a unoserver
    process restart between requests is recovered from automatically. Records
    the wall time in :data:`PDF_CONVERSION_DURATION`.
    """
    if not docx_bytes:
        raise ValueError("docx_bytes is empty")
    settings = get_settings(host, port)
    attempts = max(1, retries + 1)
    last_error: Exception | None = None

    with PDF_CONVERSION_DURATION.time():
        for attempt in range(attempts):
            try:
                pdf_bytes = _convert_once(docx_bytes, settings)
            except (OSError, xmlrpc.client.Fault, xmlrpc.client.ProtocolError) as exc:
                last_error = exc
                if attempt + 1 < attempts:
                    time.sleep(min(0.5 * (attempt + 1), 2.0))
                    continue
                raise UnoserverError(
                    f"unoserver convert failed at {settings.url}: {exc}"
                ) from exc
            else:
                if not pdf_bytes.startswith(b"%PDF-"):
                    raise UnoserverError(
                        "unoserver returned data that is not a PDF "
                        f"(first bytes: {pdf_bytes[:8]!r})"
                    )
                return pdf_bytes

    # Defensive: the loop above either returns or raises.
    assert last_error is not None  # pragma: no cover
    raise UnoserverError(str(last_error))  # pragma: no cover


__all__ = [
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "PDF_CONVERSION_DURATION",
    "UnoserverError",
    "UnoserverSettings",
    "convert_to_pdf",
    "get_settings",
    "ping_unoserver",
    "wait_for_unoserver_ready",
]
