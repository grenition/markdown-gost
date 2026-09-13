"""Unit tests for the PDF → DOCX prepass (T041).

The unoserver XML-RPC proxy is fully mocked: these tests exercise our error
mapping, retries, and timeout plumbing, not LibreOffice itself.
"""

from __future__ import annotations

import os
import xmlrpc.client
from pathlib import Path
from unittest import mock

import pytest

from markdown_gost.import_ import pdf_prepass
from markdown_gost.output.pdf_writer import UnoserverError


def _docx_bytes() -> bytes:
    # docx files are zip containers — they start with PK\x03\x04.
    return b"PK\x03\x04" + b"\x00" * 32


@pytest.fixture
def fake_pdf(tmp_path: Path) -> Path:
    pdf = tmp_path / "in.pdf"
    pdf.write_bytes(b"%PDF-1.7\n%fake\n")
    return pdf


def test_pdf_to_docx_writes_tmp_docx(fake_pdf: Path) -> None:
    captured: dict[str, object] = {}

    class FakeProxy:
        def __init__(self, url: str, allow_none: bool = False, **_: object) -> None:
            captured["url"] = url

        def convert(
            self,
            infile: object,
            indata: xmlrpc.client.Binary,
            outfile: object,
            convert_to: str,
            filtername: object,
            filter_options: list[str],
            update_index: bool,
            infiltername: str,
        ) -> xmlrpc.client.Binary:
            captured["convert_to"] = convert_to
            captured["indata"] = indata.data
            captured["filtername"] = filtername
            captured["filter_options"] = filter_options
            captured["update_index"] = update_index
            captured["infiltername"] = infiltername
            return xmlrpc.client.Binary(_docx_bytes())

    with mock.patch.object(xmlrpc.client, "ServerProxy", FakeProxy):
        out = pdf_prepass.pdf_to_docx(fake_pdf)

    try:
        assert out.is_file()
        assert out.suffix == ".docx"
        assert out.read_bytes().startswith(b"PK")
        assert captured["convert_to"] == "docx"
        assert captured["indata"] == fake_pdf.read_bytes()
        assert captured["infiltername"] == pdf_prepass.PDF_INPUT_FILTER
        assert captured["filtername"] is None
        assert captured["filter_options"] == []
        assert captured["update_index"] is True
    finally:
        import shutil

        shutil.rmtree(out.parent, ignore_errors=True)


def test_pdf_to_docx_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        pdf_prepass.pdf_to_docx(tmp_path / "nope.pdf")


def test_pdf_to_docx_rejects_empty_file(tmp_path: Path) -> None:
    empty = tmp_path / "empty.pdf"
    empty.write_bytes(b"")
    with pytest.raises(UnoserverError, match="empty"):
        pdf_prepass.pdf_to_docx(empty)


def test_pdf_to_docx_wraps_xmlrpc_fault(fake_pdf: Path) -> None:
    class FailingProxy:
        def __init__(self, *a: object, **kw: object) -> None:
            pass

        def convert(self, *args: object) -> object:
            raise xmlrpc.client.Fault(1, "boom")

    with (
        mock.patch.object(xmlrpc.client, "ServerProxy", FailingProxy),
        pytest.raises(UnoserverError, match="boom"),
    ):
        pdf_prepass.pdf_to_docx(fake_pdf, retries=0)


def test_pdf_to_docx_wraps_socket_error(fake_pdf: Path) -> None:
    class FailingProxy:
        def __init__(self, *a: object, **kw: object) -> None:
            pass

        def convert(self, *args: object) -> object:
            raise OSError("connection refused")

    with (
        mock.patch.object(xmlrpc.client, "ServerProxy", FailingProxy),
        pytest.raises(UnoserverError, match="connection refused"),
    ):
        pdf_prepass.pdf_to_docx(fake_pdf, retries=0)


def test_pdf_to_docx_retries_then_succeeds(fake_pdf: Path) -> None:
    calls = {"n": 0}

    class FlakyProxy:
        def __init__(self, *a: object, **kw: object) -> None:
            pass

        def convert(self, *args: object) -> xmlrpc.client.Binary:
            calls["n"] += 1
            if calls["n"] == 1:
                raise OSError("transient")
            return xmlrpc.client.Binary(_docx_bytes())

    with mock.patch.object(xmlrpc.client, "ServerProxy", FlakyProxy):
        out = pdf_prepass.pdf_to_docx(fake_pdf, retries=1)

    try:
        assert calls["n"] == 2
        assert out.is_file()
    finally:
        import shutil

        shutil.rmtree(out.parent, ignore_errors=True)


def test_pdf_to_docx_rejects_non_docx_result(fake_pdf: Path) -> None:
    class WrongTypeProxy:
        def __init__(self, *a: object, **kw: object) -> None:
            pass

        def convert(self, *args: object) -> xmlrpc.client.Binary:
            return xmlrpc.client.Binary(b"<html>not a docx</html>")

    with (
        mock.patch.object(xmlrpc.client, "ServerProxy", WrongTypeProxy),
        pytest.raises(UnoserverError, match="not a docx"),
    ):
        pdf_prepass.pdf_to_docx(fake_pdf, retries=0)


def test_pdf_prepass_timeout_env_picked_up(
    fake_pdf: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PDF_PREPASS_TIMEOUT_SECONDS", "7")
    assert pdf_prepass._timeout_seconds() == 7.0


def test_pdf_prepass_timeout_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PDF_PREPASS_TIMEOUT_SECONDS", raising=False)
    assert pdf_prepass._timeout_seconds() == float(
        pdf_prepass.DEFAULT_TIMEOUT_SECONDS
    )


def test_pdf_prepass_timeout_invalid_env_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PDF_PREPASS_TIMEOUT_SECONDS", "notanumber")
    assert pdf_prepass._timeout_seconds() == float(
        pdf_prepass.DEFAULT_TIMEOUT_SECONDS
    )


# Keep os import alive (used implicitly by monkeypatched env vars).
assert os is not None
