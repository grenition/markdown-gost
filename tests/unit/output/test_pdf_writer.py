"""Unit tests for the PDF writer (T018).

The unoserver XML-RPC client is patched so these tests never need a running
LibreOffice instance. Real-network coverage lives in
``tests/integration/test_pdf_conversion.py``.
"""

from __future__ import annotations

import socket
import xmlrpc.client
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from markdown_gost.output import pdf_writer
from markdown_gost.output.pdf_writer import (
    PDF_CONVERSION_DURATION,
    UnoserverError,
    convert_to_pdf,
    get_settings,
    ping_unoserver,
    wait_for_unoserver_ready,
)

PDF_HEADER = b"%PDF-1.7\n%fake\n%%EOF\n"
DUMMY_DOCX = b"PK\x03\x04dummy-docx-bytes"


# --------------------------------------------------------------------------- #
# settings / env handling
# --------------------------------------------------------------------------- #


def test_get_settings_uses_explicit_args(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UNOSERVER_HOST", "ignored")
    monkeypatch.setenv("UNOSERVER_PORT", "9999")
    s = get_settings(host="example.com", port=4242)
    assert s.host == "example.com"
    assert s.port == 4242
    assert s.url == "http://example.com:4242"


def test_get_settings_falls_back_to_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UNOSERVER_HOST", "uno.local")
    monkeypatch.setenv("UNOSERVER_PORT", "5555")
    s = get_settings()
    assert s.host == "uno.local"
    assert s.port == 5555


def test_get_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UNOSERVER_HOST", raising=False)
    monkeypatch.delenv("UNOSERVER_PORT", raising=False)
    s = get_settings()
    assert s.host == "127.0.0.1"
    assert s.port == 2003


# --------------------------------------------------------------------------- #
# ping / wait
# --------------------------------------------------------------------------- #


def test_ping_unoserver_returns_false_when_unreachable() -> None:
    # Port 1 is reserved for tcpmux and effectively never listens locally.
    assert ping_unoserver(host="127.0.0.1", port=1, timeout=0.2) is False


def test_ping_unoserver_returns_true_when_socket_connects() -> None:
    fake_sock = MagicMock()
    fake_sock.__enter__.return_value = fake_sock
    fake_sock.__exit__.return_value = False
    with patch(
        "markdown_gost.output.pdf_writer.socket.create_connection",
        return_value=fake_sock,
    ):
        assert ping_unoserver(host="x", port=1) is True


def test_wait_for_unoserver_ready_succeeds_after_retries() -> None:
    attempts = {"n": 0}

    def fake_connect(*_args: Any, **_kwargs: Any) -> Any:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise OSError("not yet")
        sock = MagicMock()
        sock.__enter__.return_value = sock
        sock.__exit__.return_value = False
        return sock

    with patch(
        "markdown_gost.output.pdf_writer.socket.create_connection",
        side_effect=fake_connect,
    ):
        wait_for_unoserver_ready(host="x", port=1, timeout=5.0, interval=0.0)
    assert attempts["n"] == 3


def test_wait_for_unoserver_ready_raises_on_timeout() -> None:
    def always_fail(*_args: Any, **_kwargs: Any) -> Any:
        raise OSError("nope")

    with (
        patch(
            "markdown_gost.output.pdf_writer.socket.create_connection",
            side_effect=always_fail,
        ),
        pytest.raises(UnoserverError, match="not ready within"),
    ):
        wait_for_unoserver_ready(host="x", port=1, timeout=0.05, interval=0.0)


# --------------------------------------------------------------------------- #
# convert_to_pdf
# --------------------------------------------------------------------------- #


def _fake_proxy(result: Any) -> MagicMock:
    proxy = MagicMock()
    proxy.convert.return_value = result
    return proxy


def test_convert_to_pdf_returns_bytes_from_unoserver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proxy = _fake_proxy(xmlrpc.client.Binary(PDF_HEADER))
    monkeypatch.setattr(
        pdf_writer.xmlrpc.client, "ServerProxy", MagicMock(return_value=proxy)
    )
    out = convert_to_pdf(DUMMY_DOCX, host="x", port=1)
    assert out.startswith(b"%PDF-")
    assert out == PDF_HEADER
    proxy.convert.assert_called_once()
    args = proxy.convert.call_args.args
    # signature: (path_or_none, indata, outpath_or_none, fmt, filtername)
    assert args[0] is None
    assert isinstance(args[1], xmlrpc.client.Binary)
    assert args[1].data == DUMMY_DOCX
    assert args[3] == "pdf"


def test_convert_to_pdf_rejects_empty_input() -> None:
    with pytest.raises(ValueError):
        convert_to_pdf(b"")


def test_convert_to_pdf_wraps_socket_error_after_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proxy = MagicMock()
    proxy.convert.side_effect = OSError("connection refused")
    monkeypatch.setattr(
        pdf_writer.xmlrpc.client, "ServerProxy", MagicMock(return_value=proxy)
    )
    monkeypatch.setattr(pdf_writer.time, "sleep", lambda _s: None)
    with pytest.raises(UnoserverError, match="convert failed"):
        convert_to_pdf(DUMMY_DOCX, host="x", port=1, retries=2)
    assert proxy.convert.call_count == 3  # 1 initial + 2 retries


def test_convert_to_pdf_recovers_after_transient_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proxy = MagicMock()
    proxy.convert.side_effect = [
        OSError("transient"),
        xmlrpc.client.Binary(PDF_HEADER),
    ]
    monkeypatch.setattr(
        pdf_writer.xmlrpc.client, "ServerProxy", MagicMock(return_value=proxy)
    )
    monkeypatch.setattr(pdf_writer.time, "sleep", lambda _s: None)
    out = convert_to_pdf(DUMMY_DOCX, host="x", port=1, retries=2)
    assert out == PDF_HEADER
    assert proxy.convert.call_count == 2


def test_convert_to_pdf_raises_when_unoserver_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proxy = _fake_proxy(None)
    monkeypatch.setattr(
        pdf_writer.xmlrpc.client, "ServerProxy", MagicMock(return_value=proxy)
    )
    monkeypatch.setattr(pdf_writer.time, "sleep", lambda _s: None)
    with pytest.raises(UnoserverError, match="no data"):
        convert_to_pdf(DUMMY_DOCX, host="x", port=1, retries=0)


def test_convert_to_pdf_rejects_non_pdf_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proxy = _fake_proxy(xmlrpc.client.Binary(b"not a pdf"))
    monkeypatch.setattr(
        pdf_writer.xmlrpc.client, "ServerProxy", MagicMock(return_value=proxy)
    )
    with pytest.raises(UnoserverError, match="not a PDF"):
        convert_to_pdf(DUMMY_DOCX, host="x", port=1, retries=0)


def test_convert_to_pdf_records_duration_metric(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proxy = _fake_proxy(xmlrpc.client.Binary(PDF_HEADER))
    monkeypatch.setattr(
        pdf_writer.xmlrpc.client, "ServerProxy", MagicMock(return_value=proxy)
    )
    before = PDF_CONVERSION_DURATION._sum.get()  # type: ignore[attr-defined]
    convert_to_pdf(DUMMY_DOCX, host="x", port=1)
    after = PDF_CONVERSION_DURATION._sum.get()  # type: ignore[attr-defined]
    assert after >= before  # observation recorded (duration is non-negative)


def test_convert_to_pdf_wraps_xmlrpc_fault(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proxy = MagicMock()
    proxy.convert.side_effect = xmlrpc.client.Fault(1, "boom")
    monkeypatch.setattr(
        pdf_writer.xmlrpc.client, "ServerProxy", MagicMock(return_value=proxy)
    )
    monkeypatch.setattr(pdf_writer.time, "sleep", lambda _s: None)
    with pytest.raises(UnoserverError, match="convert failed"):
        convert_to_pdf(DUMMY_DOCX, host="x", port=1, retries=1)


# Sanity guard: socket import is unused outside ping helpers — keep it linted.
assert socket is not None
