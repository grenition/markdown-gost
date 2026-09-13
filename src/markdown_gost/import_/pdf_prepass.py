"""PDF → DOCX prepass via unoserver (T041, ADR-0006).

PDF input is supported by routing the file through unoserver's LibreOffice
converter to obtain a DOCX, which we then feed into the existing docx import
pipeline. LibreOffice's PDF reader does no OCR — scanned PDFs come back
empty or near-empty. We do not raise on that; the caller decides what to
emit.

The timeout is separate from ``PANDOC_TIMEOUT_SECONDS``: large PDFs can take
substantially longer than a docx → markdown pass, so we expose a dedicated
``PDF_PREPASS_TIMEOUT_SECONDS`` env (default 60s).
"""

from __future__ import annotations

import contextlib
import http.client
import logging
import os
import tempfile
import time
import xmlrpc.client
from pathlib import Path

from markdown_gost.output.pdf_writer import UnoserverError, UnoserverSettings, get_settings

DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_RETRIES = 1

# LibreOffice opens PDFs as Draw documents by default — that has no export
# path to writer_MS_Word_2007 (docx). Force the Writer-side PDF import filter
# so the in-memory document is a TextDocument we can export to docx.
PDF_INPUT_FILTER = "writer_pdf_import"

_LOGGER = logging.getLogger("markdown_gost.import.pdf_prepass")


def _timeout_seconds() -> float:
    raw = os.environ.get("PDF_PREPASS_TIMEOUT_SECONDS")
    if not raw:
        return float(DEFAULT_TIMEOUT_SECONDS)
    try:
        value = float(raw)
    except ValueError:
        return float(DEFAULT_TIMEOUT_SECONDS)
    return max(1.0, value)


class _TimedTransport(xmlrpc.client.Transport):
    """xmlrpc Transport that pins a per-connection socket timeout."""

    def __init__(self, timeout: float) -> None:
        super().__init__()
        self._timeout = timeout

    def make_connection(
        self, host: tuple[str, dict[str, str]] | str
    ) -> http.client.HTTPConnection:
        conn = super().make_connection(host)
        conn.timeout = self._timeout
        return conn


def _convert_once(
    pdf_bytes: bytes, settings: UnoserverSettings, timeout: float
) -> bytes:
    proxy = xmlrpc.client.ServerProxy(
        settings.url, allow_none=True, transport=_TimedTransport(timeout)
    )
    try:
        # unoserver.server.convert positional signature:
        #   (inpath, indata, outpath, convert_to, filtername,
        #    filter_options, update_index, infiltername, password)
        # XML-RPC has no kwargs — we must pass positionals up to infiltername.
        result = proxy.convert(
            None,
            xmlrpc.client.Binary(pdf_bytes),
            None,
            "docx",
            None,
            [],
            True,
            PDF_INPUT_FILTER,
        )
    finally:
        with contextlib.suppress(Exception):
            transport = getattr(proxy, "_ServerProxy__transport", None)
            if transport is not None and hasattr(transport, "close"):
                transport.close()
    if result is None:
        raise UnoserverError("unoserver returned no data for pdf→docx")
    if isinstance(result, xmlrpc.client.Binary):
        return result.data
    if isinstance(result, bytes | bytearray):
        return bytes(result)
    raise UnoserverError(
        f"unexpected unoserver response type: {type(result).__name__}"
    )


def pdf_to_docx(
    pdf_path: Path,
    *,
    host: str | None = None,
    port: int | None = None,
    retries: int = DEFAULT_RETRIES,
    timeout: float | None = None,
) -> Path:
    """Convert ``pdf_path`` to a temporary DOCX file via unoserver.

    Returns the path of the produced DOCX. The caller owns the file and
    must unlink it (or its containing directory) when done.

    Raises :class:`FileNotFoundError` if the input is missing,
    :class:`UnoserverError` on transport or conversion failure (incl.
    timeout).
    """
    if not pdf_path.is_file():
        raise FileNotFoundError(pdf_path)

    pdf_bytes = pdf_path.read_bytes()
    if not pdf_bytes:
        raise UnoserverError(f"pdf is empty: {pdf_path}")

    resolved_timeout = timeout if timeout is not None else _timeout_seconds()
    settings = get_settings(host, port)
    attempts = max(1, retries + 1)

    size_mb = len(pdf_bytes) / (1024 * 1024)
    _LOGGER.info(
        "converting pdf to docx (size=%.2f MB, path=%s)", size_mb, pdf_path
    )

    docx_bytes: bytes | None = None
    for attempt in range(attempts):
        try:
            docx_bytes = _convert_once(pdf_bytes, settings, resolved_timeout)
            break
        except (OSError, xmlrpc.client.Fault, xmlrpc.client.ProtocolError) as exc:
            if attempt + 1 < attempts:
                time.sleep(min(0.5 * (attempt + 1), 2.0))
                continue
            raise UnoserverError(
                f"unoserver pdf→docx failed at {settings.url}: {exc}"
            ) from exc

    assert docx_bytes is not None  # pragma: no cover  # loop returns or raises
    if not docx_bytes.startswith(b"PK"):
        raise UnoserverError(
            "unoserver returned data that is not a docx "
            f"(first bytes: {docx_bytes[:8]!r})"
        )

    tmp_dir = tempfile.mkdtemp(prefix="markdown-gost-pdf-prepass-")
    out_path = Path(tmp_dir) / (pdf_path.stem + ".docx")
    out_path.write_bytes(docx_bytes)
    return out_path


__all__ = [
    "DEFAULT_RETRIES",
    "DEFAULT_TIMEOUT_SECONDS",
    "pdf_to_docx",
]
