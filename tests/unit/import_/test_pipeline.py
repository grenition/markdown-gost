"""Unit tests for the import pipeline (T032 + T034 + T043).

The pipeline runs pandoc, routes extracted images through an
:class:`ImageHandler`, rewrites the markdown to point at the new links, and
finally hands the result to the postprocessor (T033). T043 moved every image
to a flat 32-hex content-hash id (no extension, no original archive name).
"""

from __future__ import annotations

import hashlib
import re
import zipfile
from pathlib import Path
from unittest import mock

import pytest

from markdown_gost.import_ import (
    ImageRef,
    ImportContext,
    ImportResult,
    import_docx,
    import_file,
    import_pdf,
)
from markdown_gost.import_.pandoc_runner import PandocError
from markdown_gost.output.pdf_writer import UnoserverError
from markdown_gost.storage import FilesystemStorage

_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def _expected_id(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:32]


def _ctx(tmp_path: Path) -> ImportContext:
    return ImportContext(
        storage=FilesystemStorage(base_dir=tmp_path),
        images_prefix=None,
        images_dir=tmp_path / "out_files",
    )


def test_import_docx_routes_images_through_local_handler(tmp_path: Path) -> None:
    docx = tmp_path / "in.docx"
    docx.write_bytes(b"PK\x03\x04")

    def fake_run(self: object, docx_path: Path, media_dir: Path) -> str:
        media_sub = media_dir / "media"
        media_sub.mkdir(parents=True, exist_ok=True)
        (media_sub / "image1.png").write_bytes(b"\x89PNG-1")
        (media_sub / "image2.jpg").write_bytes(b"\xff\xd8\xff")
        return (
            "# Hello\n\n"
            "![](media/image1.png)\n\n"
            "Body.\n\n"
            "![alt2](media/image2.jpg)\n"
        )

    with mock.patch(
        "markdown_gost.import_.pandoc_runner.PandocRunner.run", new=fake_run
    ):
        result = import_docx(docx, _ctx(tmp_path))

    assert isinstance(result, ImportResult)
    id1 = _expected_id(b"\x89PNG-1")
    id2 = _expected_id(b"\xff\xd8\xff")
    assert f"out_files/{id1}" in result.markdown
    assert f"out_files/{id2}" in result.markdown
    assert "media/image1.png" not in result.markdown
    assert "media/image2.jpg" not in result.markdown

    assert [img.name for img in result.images] == [id1, id2]
    for img in result.images:
        assert isinstance(img, ImageRef)
        assert _ID_RE.match(img.name)
    assert (tmp_path / "out_files" / id1).read_bytes() == b"\x89PNG-1"
    assert (tmp_path / "out_files" / id2).read_bytes() == b"\xff\xd8\xff"
    assert result.fallbacks.get("image", 0) == 0


def test_import_docx_routes_images_through_storage(tmp_path: Path) -> None:
    docx = tmp_path / "in.docx"
    docx.write_bytes(b"PK\x03\x04")

    storage_root = tmp_path / "bucket"
    ctx = ImportContext(
        storage=FilesystemStorage(base_dir=storage_root),
        images_prefix="jobs/42",
        images_dir=None,
    )

    def fake_run(self: object, docx_path: Path, media_dir: Path) -> str:
        media_sub = media_dir / "media"
        media_sub.mkdir(parents=True, exist_ok=True)
        (media_sub / "image1.png").write_bytes(b"\x89PNG-1")
        return "![](media/image1.png)\n"

    with mock.patch(
        "markdown_gost.import_.pandoc_runner.PandocRunner.run", new=fake_run
    ):
        result = import_docx(docx, ctx)

    image_id = _expected_id(b"\x89PNG-1")
    assert f"jobs/42/{image_id}" in result.markdown
    assert (storage_root / f"jobs/42/{image_id}").read_bytes() == b"\x89PNG-1"
    assert [img.name for img in result.images] == [image_id]


def test_import_docx_handles_no_images(tmp_path: Path) -> None:
    docx = tmp_path / "in.docx"
    docx.write_bytes(b"PK\x03\x04")

    def fake_run(self: object, docx_path: Path, media_dir: Path) -> str:
        return "plain text\n"

    with mock.patch(
        "markdown_gost.import_.pandoc_runner.PandocRunner.run", new=fake_run
    ):
        result = import_docx(docx, _ctx(tmp_path))

    assert result.markdown == "plain text\n"
    assert result.images == []
    # No images → no directory created.
    assert not (tmp_path / "out_files").exists()


def test_import_docx_dangling_path_falls_back(tmp_path: Path) -> None:
    docx = tmp_path / "in.docx"
    docx.write_bytes(b"PK\x03\x04")

    def fake_run(self: object, docx_path: Path, media_dir: Path) -> str:
        # pandoc references a file it didn't actually write.
        return "![](media/ghost.png)\n"

    with mock.patch(
        "markdown_gost.import_.pandoc_runner.PandocRunner.run", new=fake_run
    ):
        result = import_docx(docx, _ctx(tmp_path))

    # T047: raw pandoc path must not leak; image replaced by placeholder.
    assert "media/ghost.png" not in result.markdown
    assert "![](missing/1)" in result.markdown
    assert result.images == []
    assert result.fallbacks.get("image") == 1


def test_import_docx_place_failures_emit_placeholders(tmp_path: Path) -> None:
    """T047: when ImageHandler.place raises, the URL must not leak as raw
    pandoc path or `<img>` tag — emit a placeholder and bump the fallback."""
    docx = tmp_path / "in.docx"
    docx.write_bytes(b"PK\x03\x04")

    def fake_run(self: object, docx_path: Path, media_dir: Path) -> str:
        media_sub = media_dir / "media"
        media_sub.mkdir(parents=True, exist_ok=True)
        for idx, payload in enumerate(
            [b"\x89PNG-1", b"\x89PNG-2", b"\x89PNG-3"], start=1
        ):
            (media_sub / f"image{idx}.png").write_bytes(payload)
        # 1st: raw <img> (pandoc emits this for sized images);
        # 2nd: regular markdown ref; 3rd: another <img>.
        return (
            "Before.\n\n"
            '<img src="media/image1.png" '
            'style="width:6.49in;height:3.65in" />\n\n'
            "Middle.\n\n"
            "![ok](media/image2.png)\n\n"
            '<img src="media/image3.png" style="width:5in" />\n\n'
            "After.\n"
        )

    real_place = __import__(
        "markdown_gost.import_.image_handler", fromlist=["LocalImageHandler"]
    ).LocalImageHandler.place

    calls: list[Path] = []

    def flaky_place(self, src_path: Path):  # type: ignore[no-untyped-def]
        calls.append(src_path)
        if src_path.name in {"image1.png", "image3.png"}:
            raise OSError("simulated s3 PUT failure")
        return real_place(self, src_path)

    with (
        mock.patch(
            "markdown_gost.import_.pandoc_runner.PandocRunner.run", new=fake_run
        ),
        mock.patch(
            "markdown_gost.import_.image_handler.LocalImageHandler.place",
            new=flaky_place,
        ),
    ):
        result = import_docx(docx, _ctx(tmp_path))

    # No raw <img> tag and no leaked ./media/ paths.
    assert "<img" not in result.markdown
    assert "media/image1.png" not in result.markdown
    assert "media/image3.png" not in result.markdown
    # Placeholders are emitted for both failed refs.
    assert "![](missing/1)" in result.markdown
    assert "![](missing/2)" in result.markdown
    # The successful middle image was still written through the handler.
    id2 = _expected_id(b"\x89PNG-2")
    assert f"out_files/{id2}" in result.markdown
    # Fallback counter ticked exactly twice.
    assert result.fallbacks.get("image") == 2
    # Only the one successful image lands in result.images.
    assert [img.name for img in result.images] == [id2]


def test_import_docx_html_img_dangling_emits_placeholder(tmp_path: Path) -> None:
    """T047: raw `<img>` referencing a missing file must not leak either."""
    docx = tmp_path / "in.docx"
    docx.write_bytes(b"PK\x03\x04")

    def fake_run(self: object, docx_path: Path, media_dir: Path) -> str:
        # pandoc emits raw <img> for sized images but never wrote the file.
        return (
            '<img src="./media/media/imageN.jpeg" '
            'style="width:6.49in;height:3.65in" />\n'
        )

    with mock.patch(
        "markdown_gost.import_.pandoc_runner.PandocRunner.run", new=fake_run
    ):
        result = import_docx(docx, _ctx(tmp_path))

    assert "<img" not in result.markdown
    assert "./media/" not in result.markdown
    assert "![](missing/1)" in result.markdown
    assert result.fallbacks.get("image") == 1


def test_import_docx_same_path_referenced_twice(tmp_path: Path) -> None:
    docx = tmp_path / "in.docx"
    docx.write_bytes(b"PK\x03\x04")

    def fake_run(self: object, docx_path: Path, media_dir: Path) -> str:
        media_sub = media_dir / "media"
        media_sub.mkdir(parents=True, exist_ok=True)
        (media_sub / "image1.png").write_bytes(b"\x89PNG-1")
        return "![a](media/image1.png)\n\n![b](media/image1.png)\n"

    with mock.patch(
        "markdown_gost.import_.pandoc_runner.PandocRunner.run", new=fake_run
    ):
        result = import_docx(docx, _ctx(tmp_path))

    image_id = _expected_id(b"\x89PNG-1")
    # Same source → same id (content-addressable), written once.
    assert result.markdown.count(f"out_files/{image_id}") == 2
    assert [img.name for img in result.images] == [image_id]


def test_import_docx_dedupes_identical_bytes_at_different_paths(
    tmp_path: Path,
) -> None:
    """Two distinct pandoc paths sharing the same bytes collapse to one id."""
    docx = tmp_path / "in.docx"
    docx.write_bytes(b"PK\x03\x04")

    def fake_run(self: object, docx_path: Path, media_dir: Path) -> str:
        media_sub = media_dir / "media"
        media_sub.mkdir(parents=True, exist_ok=True)
        (media_sub / "image1.png").write_bytes(b"DUPE")
        (media_sub / "image2.png").write_bytes(b"DUPE")
        return "![a](media/image1.png)\n\n![b](media/image2.png)\n"

    with mock.patch(
        "markdown_gost.import_.pandoc_runner.PandocRunner.run", new=fake_run
    ):
        result = import_docx(docx, _ctx(tmp_path))

    image_id = _expected_id(b"DUPE")
    assert result.markdown.count(f"out_files/{image_id}") == 2
    assert [img.name for img in result.images] == [image_id]


def test_import_docx_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        import_docx(tmp_path / "missing.docx", _ctx(tmp_path))


def test_import_docx_propagates_pandoc_error(tmp_path: Path) -> None:
    docx = tmp_path / "in.docx"
    docx.write_bytes(b"PK\x03\x04")

    def fake_run(self: object, docx_path: Path, media_dir: Path) -> str:
        raise PandocError("boom")

    with (
        mock.patch("markdown_gost.import_.pandoc_runner.PandocRunner.run", new=fake_run),
        pytest.raises(PandocError),
    ):
        import_docx(docx, _ctx(tmp_path))


# --- T041: PDF prepass + dispatcher ---------------------------------------


def _stub_pdf_to_docx(markdown_after_pandoc: str):
    """Helper: build a (pdf→docx, pandoc.run) pair that fakes the prepass.

    Returns the two patch targets so the call site can use them in one
    ``mock.patch`` stack. The prepass writes a zero-byte docx into a tmp dir
    we own; pandoc's ``run`` is monkey-patched to return the chosen markdown.
    """

    def fake_prepass(pdf_path: Path) -> Path:
        import tempfile

        tmp_dir = Path(tempfile.mkdtemp(prefix="md2gost-test-prepass-"))
        out = tmp_dir / f"{pdf_path.stem}.docx"
        out.write_bytes(b"PK\x03\x04")
        return out

    def fake_run(self: object, docx_path: Path, media_dir: Path) -> str:
        return markdown_after_pandoc

    return fake_prepass, fake_run


def test_import_pdf_delegates_to_import_docx(tmp_path: Path) -> None:
    pdf = tmp_path / "in.pdf"
    pdf.write_bytes(b"%PDF-1.7\nfake\n")

    fake_prepass, fake_run = _stub_pdf_to_docx(
        "# Heading\n\nFirst paragraph.\n\nSecond paragraph.\n"
    )

    with (
        mock.patch("markdown_gost.import_.pipeline.pdf_to_docx", side_effect=fake_prepass),
        mock.patch("markdown_gost.import_.pandoc_runner.PandocRunner.run", new=fake_run),
    ):
        result = import_pdf(pdf, _ctx(tmp_path))

    assert isinstance(result, ImportResult)
    assert "Heading" in result.markdown
    # Real markdown → no pdf_prepass fallback.
    assert result.fallbacks.get("pdf_prepass", 0) == 0


def test_import_pdf_flags_empty_output_as_fallback(tmp_path: Path) -> None:
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.7\nfake\n")

    fake_prepass, fake_run = _stub_pdf_to_docx("")

    with (
        mock.patch("markdown_gost.import_.pipeline.pdf_to_docx", side_effect=fake_prepass),
        mock.patch("markdown_gost.import_.pandoc_runner.PandocRunner.run", new=fake_run),
    ):
        result = import_pdf(pdf, _ctx(tmp_path))

    # Empty/near-empty output → pdf_prepass fallback bumped, no crash.
    assert result.fallbacks.get("pdf_prepass") == 1
    assert result.markdown == ""


def test_import_pdf_flags_single_line_output_as_fallback(tmp_path: Path) -> None:
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.7\nfake\n")

    fake_prepass, fake_run = _stub_pdf_to_docx("just one line\n")

    with (
        mock.patch("markdown_gost.import_.pipeline.pdf_to_docx", side_effect=fake_prepass),
        mock.patch("markdown_gost.import_.pandoc_runner.PandocRunner.run", new=fake_run),
    ):
        result = import_pdf(pdf, _ctx(tmp_path))

    assert result.fallbacks.get("pdf_prepass") == 1


def test_import_pdf_recovers_textbox_paragraphs_when_pandoc_is_near_empty(
    tmp_path: Path,
) -> None:
    pdf = tmp_path / "in.pdf"
    pdf.write_bytes(b"%PDF-1.7\nfake\n")
    tmp_dir = tmp_path / "prepass"
    tmp_dir.mkdir()
    docx = tmp_dir / "x.docx"
    document_xml = """<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
            xmlns:v="urn:schemas-microsoft-com:vml">
  <w:body>
    <w:p>
      <w:r>
        <w:pict>
          <v:shape>
            <v:textbox>
              <w:txbxContent>
                <w:p><w:r><w:t>PDF Import Smoke</w:t></w:r></w:p>
                <w:p><w:r><w:t>PDF Import Smoke</w:t></w:r></w:p>
                <w:p><w:r><w:t>Первый абзац.</w:t></w:r></w:p>
                <w:p><w:r><w:t>Первый абзац.</w:t></w:r></w:p>
                <w:p><w:r><w:t>Второй абзац.</w:t></w:r></w:p>
              </w:txbxContent>
            </v:textbox>
          </v:shape>
        </w:pict>
      </w:r>
    </w:p>
  </w:body>
</w:document>
"""
    with zipfile.ZipFile(docx, "w") as archive:
        archive.writestr("word/document.xml", document_xml)

    fake_run = lambda self, docx_path, media_dir: "**PDF Import Smoke**\n"  # noqa: E731

    with (
        mock.patch("markdown_gost.import_.pipeline.pdf_to_docx", return_value=docx),
        mock.patch("markdown_gost.import_.pandoc_runner.PandocRunner.run", new=fake_run),
    ):
        result = import_pdf(pdf, _ctx(tmp_path))

    assert result.markdown == "# PDF Import Smoke\n\nПервый абзац.\n\nВторой абзац.\n"
    assert result.fallbacks.get("pdf_prepass", 0) == 0
    assert not tmp_dir.exists()


def test_import_pdf_cleans_up_tmp_docx_on_success(tmp_path: Path) -> None:
    pdf = tmp_path / "in.pdf"
    pdf.write_bytes(b"%PDF-1.7\nfake\n")

    captured: dict[str, Path] = {}

    def fake_prepass(pdf_path: Path) -> Path:
        import tempfile

        tmp_dir = Path(tempfile.mkdtemp(prefix="md2gost-test-prepass-"))
        out = tmp_dir / "x.docx"
        out.write_bytes(b"PK\x03\x04")
        captured["tmp_dir"] = tmp_dir
        return out

    fake_run = lambda self, docx_path, media_dir: "# H\n\nbody\n"  # noqa: E731

    with (
        mock.patch("markdown_gost.import_.pipeline.pdf_to_docx", side_effect=fake_prepass),
        mock.patch("markdown_gost.import_.pandoc_runner.PandocRunner.run", new=fake_run),
    ):
        import_pdf(pdf, _ctx(tmp_path))

    assert not captured["tmp_dir"].exists()


def test_import_pdf_cleans_up_tmp_docx_on_error(tmp_path: Path) -> None:
    pdf = tmp_path / "in.pdf"
    pdf.write_bytes(b"%PDF-1.7\nfake\n")

    captured: dict[str, Path] = {}

    def fake_prepass(pdf_path: Path) -> Path:
        import tempfile

        tmp_dir = Path(tempfile.mkdtemp(prefix="md2gost-test-prepass-"))
        out = tmp_dir / "x.docx"
        out.write_bytes(b"PK\x03\x04")
        captured["tmp_dir"] = tmp_dir
        return out

    def fake_run(self: object, docx_path: Path, media_dir: Path) -> str:
        raise PandocError("boom")

    with (
        mock.patch("markdown_gost.import_.pipeline.pdf_to_docx", side_effect=fake_prepass),
        mock.patch("markdown_gost.import_.pandoc_runner.PandocRunner.run", new=fake_run),
        pytest.raises(PandocError),
    ):
        import_pdf(pdf, _ctx(tmp_path))

    assert not captured["tmp_dir"].exists()


def test_import_pdf_propagates_unoserver_error(tmp_path: Path) -> None:
    pdf = tmp_path / "in.pdf"
    pdf.write_bytes(b"%PDF-1.7\nfake\n")

    def fake_prepass(pdf_path: Path) -> Path:
        raise UnoserverError("unoserver down")

    with (
        mock.patch("markdown_gost.import_.pipeline.pdf_to_docx", side_effect=fake_prepass),
        pytest.raises(UnoserverError),
    ):
        import_pdf(pdf, _ctx(tmp_path))


def test_import_pdf_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        import_pdf(tmp_path / "nope.pdf", _ctx(tmp_path))


def test_import_file_dispatches_by_extension_docx(tmp_path: Path) -> None:
    docx = tmp_path / "in.docx"
    docx.write_bytes(b"PK\x03\x04")

    fake_run = lambda self, docx_path, media_dir: "# X\n\nbody\n"  # noqa: E731

    with mock.patch("markdown_gost.import_.pandoc_runner.PandocRunner.run", new=fake_run):
        result = import_file(docx, _ctx(tmp_path))

    assert "X" in result.markdown


def test_import_file_dispatches_by_extension_pdf(tmp_path: Path) -> None:
    pdf = tmp_path / "in.pdf"
    pdf.write_bytes(b"%PDF-1.7\nfake\n")

    fake_prepass, fake_run = _stub_pdf_to_docx("# Hi\n\nbody\n")
    with (
        mock.patch("markdown_gost.import_.pipeline.pdf_to_docx", side_effect=fake_prepass),
        mock.patch("markdown_gost.import_.pandoc_runner.PandocRunner.run", new=fake_run),
    ):
        result = import_file(pdf, _ctx(tmp_path))

    assert "Hi" in result.markdown


def test_import_file_uppercase_extension(tmp_path: Path) -> None:
    pdf = tmp_path / "Mixed.PDF"
    pdf.write_bytes(b"%PDF-1.7\nfake\n")

    fake_prepass, fake_run = _stub_pdf_to_docx("# Y\n\nbody\n")
    with (
        mock.patch("markdown_gost.import_.pipeline.pdf_to_docx", side_effect=fake_prepass),
        mock.patch("markdown_gost.import_.pandoc_runner.PandocRunner.run", new=fake_run),
    ):
        result = import_file(pdf, _ctx(tmp_path))

    assert "Y" in result.markdown


def test_import_file_rejects_unsupported_extension(tmp_path: Path) -> None:
    txt = tmp_path / "in.txt"
    txt.write_bytes(b"hello")
    with pytest.raises(ValueError, match="unsupported"):
        import_file(txt, _ctx(tmp_path))


def test_import_file_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        import_file(tmp_path / "nope.docx", _ctx(tmp_path))
