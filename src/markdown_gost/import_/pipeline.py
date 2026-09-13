"""Import pipeline entry point.

T032 wired the pandoc invocation; T033 wires the line-based postprocessor.
T034 rewires image handling: every image pandoc extracts is routed through
an :class:`ImageHandler` (local FS for CLI, storage for API) and the markdown
is rewritten to point at the new link before postprocessing runs.

T041 adds PDF input via unoserver-prepass: ``import_pdf`` converts the PDF
to DOCX with LibreOffice and delegates to ``import_docx``. The dispatcher
:func:`import_file` selects the entry point by extension.
"""

from __future__ import annotations

import logging
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from .image_handler import ImageHandler, LocalImageHandler, StorageImageHandler
from .listing_detector import scan_monospace_paragraphs
from .metrics import IMPORT_DURATION, IMPORT_FALLBACK_TOTAL
from .pandoc_runner import PandocRunner
from .pdf_prepass import pdf_to_docx
from .postprocessor import postprocess
from .result import ImageRef, ImportContext, ImportResult
from .semantic_docx import prepare_pandoc_input

# Match ![alt](url ...trailing) — group 2 is the bare URL token, group 3 is
# everything after the URL up to and including the closing paren (titles,
# pandoc attrs, etc.). We rewrite only group 2.
_IMG_REF_RE = re.compile(r"(!\[[^\]]*\]\()([^\s)]+)([^)]*\))")

# Match pandoc-emitted raw <img src="url" .../>. ``markdown_strict`` falls
# back to raw HTML whenever an image carries attributes (width/height/etc.).
_IMG_HTML_RE = re.compile(r"<img\b[^>]*?\bsrc=\"([^\"]+)\"[^>]*?/?>", re.IGNORECASE)

_IMAGE_STAGE = "image"
_LISTING_STAGE = "listing"
_PDF_PREPASS_STAGE = "pdf_prepass"
_DOCX_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

_LOGGER = logging.getLogger("markdown_gost.import.pipeline")


def import_docx(docx_path: Path, ctx: ImportContext) -> ImportResult:
    """Convert a DOCX file into our extended markdown (best effort).

    Raises :class:`FileNotFoundError` if ``docx_path`` does not exist,
    :class:`PandocError` if the pandoc invocation fails.
    """
    if not docx_path.is_file():
        raise FileNotFoundError(docx_path)

    scan_fallbacks: dict[str, int] = {}
    try:
        ctx.metadata["monospace_ranges"] = scan_monospace_paragraphs(docx_path)
    except Exception:
        # Best-effort: if the docx is malformed enough that python-docx cannot
        # open it but pandoc can still read it, we skip listing detection
        # rather than aborting the whole import.
        ctx.metadata["monospace_ranges"] = []
        IMPORT_FALLBACK_TOTAL.labels(stage=_LISTING_STAGE).inc()
        scan_fallbacks[_LISTING_STAGE] = 1

    with (
        IMPORT_DURATION.labels(format="docx").time(),
        tempfile.TemporaryDirectory(prefix="markdown-gost-import-") as workdir,
    ):
        media_dir = Path(workdir) / "media"
        pandoc_input = prepare_pandoc_input(docx_path, Path(workdir) / "semantic.docx")
        raw_markdown = PandocRunner().run(pandoc_input, media_dir)
        rewritten, images, fallbacks = _process_images(raw_markdown, media_dir, ctx)

    for stage, count in scan_fallbacks.items():
        fallbacks[stage] = fallbacks.get(stage, 0) + count

    markdown, post_fallbacks = postprocess(
        rewritten, monospace_ranges=ctx.metadata.get("monospace_ranges")
    )
    for stage, count in post_fallbacks.items():
        fallbacks[stage] = fallbacks.get(stage, 0) + count

    return ImportResult(markdown=markdown, images=images, fallbacks=fallbacks)


def _process_images(
    raw_markdown: str, media_dir: Path, ctx: ImportContext
) -> tuple[str, list[ImageRef], dict[str, int]]:
    """Replace pandoc image paths with handler-issued links.

    Per T043 every image is keyed by a flat 32-hex content hash. The same
    bytes appearing at different pandoc paths therefore deduplicate naturally
    (one ``ImageRef`` per unique id).

    T047: when a pandoc-emitted reference cannot be written (missing media
    file, no handler configured, or a storage exception from
    :meth:`ImageHandler.place`), the URL is rewritten to a deterministic
    ``missing/{N}`` placeholder so callers never see raw pandoc paths or
    ``<img …/>`` tags in the result. The fallback counter is bumped once
    per failed reference.
    """
    refs_in_order = _collect_image_refs(raw_markdown)
    if not refs_in_order:
        return raw_markdown, [], {}

    by_basename = _index_media(media_dir)
    handler = _build_handler(ctx)

    fallbacks: dict[str, int] = {}
    rewrite: dict[str, str] = {}
    placeholders: dict[str, str] = {}
    images: list[ImageRef] = []
    seen_ids: set[str] = set()
    miss_counter = 0

    def _mark_failed(pandoc_path: str) -> None:
        nonlocal miss_counter
        miss_counter += 1
        placeholders[pandoc_path] = f"missing/{miss_counter}"
        IMPORT_FALLBACK_TOTAL.labels(stage=_IMAGE_STAGE).inc()
        fallbacks[_IMAGE_STAGE] = fallbacks.get(_IMAGE_STAGE, 0) + 1

    for pandoc_path in refs_in_order:
        if pandoc_path in rewrite or pandoc_path in placeholders:
            continue
        src = _resolve_media(pandoc_path, media_dir, by_basename)
        if src is None or handler is None:
            _mark_failed(pandoc_path)
            continue
        try:
            placed = handler.place(src)
        except Exception:
            _LOGGER.warning(
                "import: image handler failed for %s; emitting placeholder",
                pandoc_path,
                exc_info=True,
            )
            _mark_failed(pandoc_path)
            continue
        rewrite[pandoc_path] = placed.link
        if placed.image_id not in seen_ids:
            seen_ids.add(placed.image_id)
            images.append(ImageRef(name=placed.image_id, path=src))

    rewritten = _rewrite_markdown(raw_markdown, rewrite, placeholders)
    return rewritten, images, fallbacks


def _collect_image_refs(markdown: str) -> list[str]:
    """Return image URLs in order of first appearance.

    Scans both ``![alt](url)`` markdown and ``<img src="url" .../>`` raw HTML
    that pandoc emits when the image has attributes incompatible with
    ``markdown_strict`` (width/height/etc.).
    """
    matches: list[tuple[int, str]] = []
    for match in _IMG_REF_RE.finditer(markdown):
        matches.append((match.start(), match.group(2)))
    for match in _IMG_HTML_RE.finditer(markdown):
        matches.append((match.start(), match.group(1)))
    matches.sort(key=lambda item: item[0])

    seen: set[str] = set()
    ordered: list[str] = []
    for _, url in matches:
        if url not in seen:
            seen.add(url)
            ordered.append(url)
    return ordered


def _index_media(media_dir: Path) -> dict[str, Path]:
    """Map basename → first file found under ``media_dir`` with that name."""
    if not media_dir.is_dir():
        return {}
    index: dict[str, Path] = {}
    for path in sorted(media_dir.rglob("*")):
        if path.is_file() and path.name not in index:
            index[path.name] = path
    return index


def _resolve_media(pandoc_path: str, media_dir: Path, by_basename: dict[str, Path]) -> Path | None:
    candidate = Path(pandoc_path)
    if candidate.is_file():
        return candidate
    joined = media_dir / pandoc_path
    if joined.is_file():
        return joined
    return by_basename.get(candidate.name)


def _build_handler(ctx: ImportContext) -> ImageHandler | None:
    if ctx.images_dir is not None:
        return LocalImageHandler(
            target_dir=ctx.images_dir,
            link_prefix=ctx.images_dir.name,
        )
    if ctx.images_prefix is not None:
        return StorageImageHandler(storage=ctx.storage, prefix=ctx.images_prefix)
    return None


def _rewrite_markdown(
    markdown: str,
    rewrite: dict[str, str],
    placeholders: dict[str, str] | None = None,
) -> str:
    placeholders = placeholders or {}
    if not rewrite and not placeholders:
        return markdown

    def replace_md(match: re.Match[str]) -> str:
        url = match.group(2)
        placeholder = placeholders.get(url)
        if placeholder is not None:
            # Drop original alt + trailing pandoc attrs — for a failed image
            # the alt/title would still reference a broken source.
            return f"![]({placeholder})"
        new = rewrite.get(url)
        if new is None:
            return match.group(0)
        return f"{match.group(1)}{new}{match.group(3)}"

    def replace_html(match: re.Match[str]) -> str:
        url = match.group(1)
        placeholder = placeholders.get(url)
        if placeholder is not None:
            return f"![]({placeholder})"
        new = rewrite.get(url)
        if new is None:
            return match.group(0)
        # Normalize to ![](url) — drops width/height/etc. that we don't keep
        # round-trip, but makes the result visible to the caption folder.
        return f"![]({new})"

    markdown = _IMG_REF_RE.sub(replace_md, markdown)
    markdown = _IMG_HTML_RE.sub(replace_html, markdown)
    return markdown


def import_pdf(pdf_path: Path, ctx: ImportContext) -> ImportResult:
    """Convert a PDF file into our extended markdown via unoserver-prepass.

    Routes the PDF through unoserver (LibreOffice) to obtain a DOCX, then
    delegates to :func:`import_docx`. Scanned PDFs without an OCR layer
    typically yield empty or near-empty DOCX — we surface that as-is and
    bump ``md2gost_import_fallback_total{stage=pdf_prepass}`` so dashboards
    can see it (see ADR-0006 and T041 notes).
    """
    if not pdf_path.is_file():
        raise FileNotFoundError(pdf_path)

    with IMPORT_DURATION.labels(format="pdf").time():
        tmp_docx = pdf_to_docx(pdf_path)
        tmp_dir = tmp_docx.parent
        try:
            result = import_docx(tmp_docx, ctx)
            if _looks_empty(result.markdown):
                recovered = _recover_pdf_prepass_markdown(tmp_docx)
                if not _looks_empty(recovered):
                    result.markdown = recovered
                    _LOGGER.info(
                        "pdf prepass markdown recovered from docx XML for %s",
                        pdf_path,
                    )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    if _looks_empty(result.markdown):
        IMPORT_FALLBACK_TOTAL.labels(stage=_PDF_PREPASS_STAGE).inc()
        result.fallbacks[_PDF_PREPASS_STAGE] = result.fallbacks.get(_PDF_PREPASS_STAGE, 0) + 1
        _LOGGER.info(
            "pdf prepass produced empty/near-empty markdown for %s "
            "(likely scanned pdf without text layer)",
            pdf_path,
        )

    return result


def import_file(path: Path, ctx: ImportContext) -> ImportResult:
    """Dispatch to :func:`import_docx` / :func:`import_pdf` by extension.

    Raises :class:`ValueError` for any other extension.
    """
    if not path.is_file():
        raise FileNotFoundError(path)
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return import_docx(path, ctx)
    if suffix == ".pdf":
        return import_pdf(path, ctx)
    raise ValueError(f"unsupported input extension {suffix or '(none)'!r}; expected .docx or .pdf")


def _looks_empty(markdown: str) -> bool:
    """Heuristic: did the prepass return a near-empty document?

    True when the markdown has no headings *and* at most one non-empty
    paragraph-like line. Matches the scanned-PDF degenerate case where
    LibreOffice yields a single blank page.
    """
    non_empty = [line for line in markdown.splitlines() if line.strip()]
    if not non_empty:
        return True
    return len(non_empty) <= 1


def _recover_pdf_prepass_markdown(docx_path: Path) -> str:
    """Recover text from LibreOffice PDF-import DOCX when pandoc misses textboxes."""

    try:
        with zipfile.ZipFile(docx_path) as archive:
            document_xml = archive.read("word/document.xml")
        root = ET.fromstring(document_xml)
    except (ET.ParseError, KeyError, OSError, zipfile.BadZipFile):
        return ""

    paragraph_tag = f"{{{_DOCX_W_NS}}}p"
    text_tag = f"{{{_DOCX_W_NS}}}t"
    lines: list[str] = []
    for paragraph in root.iter(paragraph_tag):
        # LibreOffice PDF import wraps text boxes in outer paragraphs; taking
        # only leaf paragraphs avoids one huge concatenated line.
        if list(paragraph.iterfind(f".//{paragraph_tag}")):
            continue
        text = "".join(node.text or "" for node in paragraph.iter(text_tag))
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue
        if lines and lines[-1] == text:
            continue
        lines.append(text)

    if len(lines) <= 1:
        return ""
    return f"# {lines[0]}\n\n" + "\n\n".join(lines[1:]) + "\n"


__all__ = ["import_docx", "import_file", "import_pdf"]
