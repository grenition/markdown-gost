from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import replace
from html import escape
from typing import Any
from urllib.parse import urlsplit

from markdown_gost.preview_json import JsonPrimitive

from .model import (
    PreviewBlock,
    PreviewDocument,
    PreviewImageDimension,
    PreviewInline,
    PreviewTableCell,
    PreviewTableDimension,
    PreviewTableRow,
)

AssetResolver = Callable[[str], str]
_LINE_HEIGHT_CALIBRATION: dict[tuple[str, int], float] = {
    ("Times", 14): 16.05,
    ("Courier", 12): 13.61,
    ("Consolas", 12): 14.75,
    ("Arial", 14): 16.05,
}
_PAGE_NUMBER_BOTTOM = "12.8mm"
_NATIVE_INLINE_MATH_COMMANDS = frozenset(
    {
        "begin",
        "cdot",
        "frac",
        "geq",
        "hbar",
        "iint",
        "infty",
        "int",
        "leq",
        "pmatrix",
        "prod",
        "sqrt",
        "sum",
        "to",
        "zeta",
    }
)
_STYLED_BLOCK_KINDS = frozenset(
    {"paragraph", "heading", "list_item", "image", "table", "listing", "equation", "toc"}
)
_SAFE_LINK_SCHEMES = frozenset({"http", "https", "mailto"})


def render_preview_html(
    document: PreviewDocument,
    *,
    asset_resolver: AssetResolver | None = None,
    style_source: PreviewDocument | None = None,
) -> str:
    """Render a preview document into standalone HTML."""

    styles = _style_registry(style_source or document)
    pages = "\n".join(
        _render_page(page_number, blocks, styles, asset_resolver)
        for page_number, blocks in _pages(document)
    )
    css = _render_css(document, styles)
    return (
        "<!doctype html>\n"
        '<html lang="ru">\n'
        "<head>\n"
        '  <meta charset="utf-8">\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "  <title>markdown-gost preview</title>\n"
        f"  <style>\n{css}\n  </style>\n"
        "</head>\n"
        "<body>\n"
        '<main class="md2gost-preview" data-md2gost-preview-version="'
        f"{escape(document.version, quote=True)}"
        '">\n'
        f"{pages}\n"
        "</main>\n"
        "</body>\n"
        "</html>\n"
    )


def render_preview_stylesheet(document: PreviewDocument) -> str:
    """Return the document-wide stylesheet used by standalone and chunk HTML."""

    return _render_css(document, _style_registry(document))


def _style_registry(document: PreviewDocument) -> _StyleRegistry:
    styles = _StyleRegistry()
    for page in document.pages:
        for block in page.blocks:
            if block.kind in _STYLED_BLOCK_KINDS:
                styles.class_for(block.style)
            if block.caption and block.kind in {"table", "listing"}:
                styles.class_for(_caption_style_from_block(block.style))
    return styles


def _pages(document: PreviewDocument) -> Iterable[tuple[int, list[PreviewBlock]]]:
    for page in document.pages:
        yield page.number, page.blocks


def _render_page(
    page_number: int,
    blocks: list[PreviewBlock],
    styles: _StyleRegistry,
    asset_resolver: AssetResolver | None,
) -> str:
    rendered_blocks = "\n".join(_render_block(block, styles, asset_resolver) for block in blocks)
    page_class = "md2gost-page"
    if any(block.kind == "title_page" for block in blocks):
        page_class += " md2gost-page--unnumbered"
    return (
        f'  <section id="page-{page_number}" class="{page_class}" '
        f'data-md2gost-page="{page_number}">\n'
        f"{rendered_blocks}\n"
        "  </section>"
    )


def _render_block(
    block: PreviewBlock,
    styles: _StyleRegistry,
    asset_resolver: AssetResolver | None,
) -> str:
    if block.anchor and block.anchor != block.id:
        alias = f'    <span id="{_id(block.anchor)}"></span>\n'
        return alias + _render_block(replace(block, anchor=None), styles, asset_resolver)
    if block.kind == "title_page":
        return _render_title_page_block(block)
    if block.kind == "toc":
        return _render_toc_block(block, styles)
    if block.kind == "paragraph":
        class_name = styles.class_for(block.style)
        return (
            f'    <p id="{_id(block.id)}" '
            'class="md2gost-block md2gost-flow-text md2gost-paragraph '
            f'{class_name}">'
            f"{_render_inlines(block, asset_resolver=asset_resolver)}"
            "</p>"
        )
    if block.kind == "heading":
        class_name = styles.class_for(block.style)
        tag = _heading_tag(block.level)
        text = _render_heading_text(block)
        return (
            f'    <{tag} id="{_id(block.id)}" '
            f'class="md2gost-block md2gost-flow-text md2gost-heading '
            f'md2gost-heading-level-{block.level or 1} {class_name}">'
            f"{text}"
            f"</{tag}>"
        )
    if block.kind == "list_item":
        class_name = styles.class_for(block.style)
        marker = escape(block.marker or "")
        separator = escape(block.marker_separator or "")
        return (
            f'    <div id="{_id(block.id)}" '
            'class="md2gost-block md2gost-flow-text md2gost-list-item '
            f'{class_name}" '
            f'data-list-type="{escape(block.list_type or "", quote=True)}" '
            f'data-list-level="{escape(str(block.level or 1), quote=True)}" '
            f'data-list-marker="{escape(block.marker or "", quote=True)}">'
            '<span class="md2gost-list-marker">'
            f"{marker}"
            "</span>"
            '<span class="md2gost-list-separator">'
            f"{separator}"
            "</span>"
            '<span class="md2gost-list-content">'
            f"{_render_inlines(block, asset_resolver=asset_resolver)}"
            "</span>"
            "</div>"
        )
    if block.kind == "image":
        return _render_image_block(block, styles, asset_resolver)
    if block.kind == "table":
        return _render_table_block(block, styles, asset_resolver)
    if block.kind == "listing":
        return _render_listing_block(block, styles)
    if block.kind == "equation":
        return _render_equation_block(block, styles)
    if block.kind == "page_break":
        return (
            f'    <div id="{_id(block.id)}" '
            'class="md2gost-block md2gost-page-break" '
            'data-kind="hard" aria-hidden="true"></div>'
        )
    if block.kind == "thematic_break":
        return f'    <hr id="{_id(block.id)}" class="md2gost-block">'
    return _render_unsupported_block(block)


def _render_title_page_block(block: PreviewBlock) -> str:
    layout = block.layout or {}
    header = "\n".join(
        _render_title_page_item(item, "md2gost-title-page-header-line")
        for item in _layout_items(layout, "header")
    )
    organization = "\n".join(
        _render_title_page_item(item, "md2gost-title-page-organization-line")
        for item in _layout_items(layout, "organization")
    )
    work = "\n".join(
        _render_title_page_item(item, "md2gost-title-page-work-line")
        for item in _layout_items(layout, "work")
    )
    signatures = "\n".join(
        _render_title_page_signature_section(section)
        for section in _layout_items(layout, "signature_sections")
    )
    footer = _layout_text(layout.get("footer"))
    footer_html = ""
    if footer:
        footer_html = f'      <footer class="md2gost-title-page-footer">{escape(footer)}</footer>'
    return (
        f'    <article id="{_id(block.id)}" '
        'class="md2gost-block md2gost-title-page">\n'
        '      <header class="md2gost-title-page-header">\n'
        f"{header}\n"
        "      </header>\n"
        '      <div class="md2gost-title-page-divider" aria-hidden="true"></div>\n'
        '      <section class="md2gost-title-page-organization">\n'
        f"{organization}\n"
        "      </section>\n"
        '      <section class="md2gost-title-page-work">\n'
        f"{work}\n"
        "      </section>\n"
        '      <section class="md2gost-title-page-signatures">\n'
        f"{signatures}\n"
        "      </section>\n"
        f"{footer_html}\n"
        "    </article>"
    )


def _render_title_page_item(item: dict[str, Any], base_class: str) -> str:
    role = _layout_text(item.get("role"))
    role_class = f" {escape(f'{base_class}--{role}', quote=True)}" if role else ""
    return (
        f'        <div class="{base_class}{role_class}">'
        f"{escape(_layout_text(item.get('text')))}"
        "</div>"
    )


def _render_title_page_signature_section(section: dict[str, Any]) -> str:
    title = _layout_text(section.get("title"))
    rendered_rows: list[str] = []
    for row in _layout_items(section, "rows"):
        label = escape(_layout_text(row.get("label")))
        name = escape(_layout_text(row.get("name")))
        rendered_rows.append(
            '          <div class="md2gost-title-page-signature-row">'
            f'<span class="md2gost-title-page-signature-label">{label}</span>'
            f'<span class="md2gost-title-page-signature-name">{name}</span>'
            "</div>"
        )
    rows = "\n".join(rendered_rows)
    return (
        '        <section class="md2gost-title-page-signature-section">\n'
        f'          <div class="md2gost-title-page-signature-title">{escape(title)}</div>\n'
        f"{rows}\n"
        "        </section>"
    )


def _render_toc_block(block: PreviewBlock, styles: _StyleRegistry) -> str:
    layout = block.layout or {}
    dot_leader = "true" if layout.get("dot_leader") else "false"
    class_name = styles.class_for(block.style)
    entries = "\n".join(
        _render_toc_entry(entry, dot_leader=bool(layout.get("dot_leader")))
        for entry in _layout_items(layout, "entries")
    )
    return (
        f'    <nav id="{_id(block.id)}" '
        f'class="md2gost-block md2gost-flow-text md2gost-toc {class_name}" '
        f'data-dot-leader="{dot_leader}" aria-label="Оглавление">\n'
        f"{entries}\n"
        "    </nav>"
    )


def _render_toc_entry(entry: dict[str, Any], *, dot_leader: bool) -> str:
    level = _layout_level(entry.get("level"))
    number = _layout_text(entry.get("number")) if entry.get("numbered") else ""
    text = _layout_text(entry.get("text"))
    anchor = _layout_text(entry.get("anchor"))
    page = _layout_text(entry.get("page"))
    leader_class = " md2gost-toc-leader--none" if not dot_leader else ""
    href = _safe_link_href(f"#{anchor}")
    link = escape(text)
    if href is not None:
        link = f'<a class="md2gost-toc-link" href="{escape(href, quote=True)}">{link}</a>'
    return (
        '      <div class="md2gost-toc-entry" '
        f'data-toc-level="{level}" style="--md2gost-toc-level: {level};">'
        f'<span class="md2gost-toc-number">{escape(number)}</span>'
        f'<span class="md2gost-toc-title">{link}</span>'
        f'<span class="md2gost-toc-leader{leader_class}" aria-hidden="true"></span>'
        f'<span class="md2gost-toc-page-number">{escape(page)}</span>'
        "</div>"
    )


def _layout_items(layout: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = layout.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _layout_text(value: object) -> str:
    return value if isinstance(value, str) else str(value or "")


def _layout_level(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return 1
    try:
        return max(1, min(6, int(value)))
    except (TypeError, ValueError):
        return 1


def _render_table_block(
    block: PreviewBlock,
    styles: _StyleRegistry,
    asset_resolver: AssetResolver | None,
) -> str:
    class_name = styles.class_for(block.style)
    colgroup = _render_table_colgroup(block)
    caption = ""
    if block.caption:
        caption_class = styles.class_for(_caption_style_from_block(block.style))
        caption = (
            f'      <caption class="md2gost-caption md2gost-flow-text {caption_class}">'
            f"{escape(block.caption)}</caption>\n"
        )
    header_rows = [row for row in block.rows or [] if row.header]
    body_rows = [row for row in block.rows or [] if not row.header]
    thead = ""
    if header_rows:
        rendered_rows = "\n".join(
            _render_table_row(row, header=True, asset_resolver=asset_resolver)
            for row in header_rows
        )
        thead = f"      <thead>\n{rendered_rows}\n      </thead>\n"
    rendered_body_rows = "\n".join(
        _render_table_row(row, header=False, asset_resolver=asset_resolver) for row in body_rows
    )
    tbody = f"      <tbody>\n{rendered_body_rows}\n      </tbody>\n"
    return (
        f'    <table id="{_id(block.id)}" '
        f'class="md2gost-block md2gost-table {class_name}" '
        f'data-table-number="{escape(block.number or "", quote=True)}" '
        f'data-table-layout="{escape(str(block.style.get("table_layout") or ""), quote=True)}" '
        f'data-continuation="{_bool_attr(block.continuation)}">\n'
        f"{colgroup}"
        f"{caption}"
        f"{thead}"
        f"{tbody}"
        "    </table>"
    )


def _render_table_colgroup(block: PreviewBlock) -> str:
    if not block.column_widths:
        return ""
    cols: list[str] = []
    for width in block.column_widths:
        css_width = _table_dimension_css(width)
        if css_width is None:
            cols.append("        <col>")
        else:
            cols.append(f'        <col style="width: {escape(css_width, quote=True)};">')
    return "      <colgroup>\n" + "\n".join(cols) + "\n      </colgroup>\n"


def _render_table_row(
    row: PreviewTableRow,
    *,
    header: bool,
    asset_resolver: AssetResolver | None,
) -> str:
    rendered_cells = "".join(
        _render_table_cell(
            cell,
            tag="th" if header or cell.header else "td",
            asset_resolver=asset_resolver,
        )
        for cell in row.cells
    )
    return f"        <tr>{rendered_cells}</tr>"


def _render_table_cell(
    cell: PreviewTableCell,
    *,
    tag: str,
    asset_resolver: AssetResolver | None,
) -> str:
    attrs: list[str] = []
    if cell.align:
        safe_align = escape(cell.align, quote=True)
        attrs.append(f'data-align="{safe_align}"')
        attrs.append(f'style="text-align: {safe_align};"')
    if cell.col_span != 1:
        attrs.append(f'colspan="{escape(str(cell.col_span), quote=True)}"')
    if cell.row_span != 1:
        attrs.append(f'rowspan="{escape(str(cell.row_span), quote=True)}"')
    attr_text = "" if not attrs else " " + " ".join(attrs)
    content = _render_inline_list(
        cell.inlines,
        fallback_text=cell.text,
        asset_resolver=asset_resolver,
    )
    return f"<{tag}{attr_text}>{content}</{tag}>"


def _render_listing_block(
    block: PreviewBlock,
    styles: _StyleRegistry,
) -> str:
    class_name = styles.class_for(block.style)
    caption = ""
    if block.caption:
        caption_class = styles.class_for(_caption_style_from_block(block.style))
        caption = (
            '      <figcaption class="md2gost-caption md2gost-flow-text '
            f'md2gost-listing-caption {caption_class}">'
            f"{escape(block.caption)}"
            "</figcaption>\n"
        )
    language_attr = ""
    if block.language:
        language_attr = f' data-language="{escape(block.language, quote=True)}"'
    highlighted_class = ""
    if any(inline.kind == "listing_token" for inline in block.inlines):
        highlighted_class = " md2gost-listing-highlighted"
    continuation_attr = _bool_attr(block.continuation)
    return (
        f'    <figure id="{_id(block.id)}" '
        'class="md2gost-block md2gost-listing-block" '
        f'data-listing-number="{escape(block.number or "", quote=True)}" '
        f'data-continuation="{continuation_attr}">\n'
        f"{caption}"
        f'      <pre class="md2gost-listing{highlighted_class} {class_name}">'
        f"<code{language_attr}>{_render_listing_code(block)}</code>"
        "</pre>\n"
        "    </figure>"
    )


def _render_listing_code(block: PreviewBlock) -> str:
    if not block.inlines:
        return escape(block.text)
    return "".join(_render_listing_token(inline) for inline in block.inlines)


def _render_listing_token(inline: PreviewInline) -> str:
    text = escape(inline.text or "")
    declarations: list[str] = []
    if inline.color:
        declarations.append(f"color: {_css_value(inline.color)};")
    if inline.bold:
        declarations.append("font-weight: 700;")
    if inline.italic:
        declarations.append("font-style: italic;")
    if not declarations:
        return text
    attrs = escape(" ".join(declarations), quote=True)
    return f'<span class="md2gost-listing-token" style="{attrs}">{text}</span>'


def _render_heading_text(
    block: PreviewBlock,
    *,
    asset_resolver: AssetResolver | None = None,
) -> str:
    prefix = ""
    if block.number:
        prefix = f"{escape(block.number)} "
    text = _render_inlines(
        block,
        uppercase=bool(block.style.get("uppercase")),
        asset_resolver=asset_resolver,
    )
    return f"{prefix}{text}"


def _render_inlines(
    block: PreviewBlock,
    *,
    uppercase: bool = False,
    asset_resolver: AssetResolver | None = None,
) -> str:
    if not block.inlines:
        text = block.text.upper() if uppercase else block.text
        return escape(text)
    return _render_inline_list(
        block.inlines,
        uppercase=uppercase,
        fallback_text=block.text,
        asset_resolver=asset_resolver,
    )


def _render_inline_list(
    inlines: list[PreviewInline],
    *,
    fallback_text: str,
    uppercase: bool = False,
    asset_resolver: AssetResolver | None = None,
) -> str:
    if not inlines:
        text = fallback_text.upper() if uppercase else fallback_text
        return escape(text)
    return "".join(
        _render_inline(inline, uppercase=uppercase, asset_resolver=asset_resolver)
        for inline in inlines
    )


def _render_inline(
    inline: PreviewInline,
    *,
    uppercase: bool,
    asset_resolver: AssetResolver | None,
) -> str:
    raw_text = inline.text or ""
    if uppercase:
        raw_text = raw_text.upper()
    text = escape(_docx_text(raw_text))
    rendered: str
    if inline.kind == "text":
        rendered = text
    elif inline.kind == "code":
        rendered = _render_code_inline(inline, raw_text)
    elif inline.kind == "line_break":
        rendered = escape(raw_text or " ")
    elif inline.kind == "link":
        href = _safe_link_href(inline.href or "")
        rendered = text if href is None else f'<a href="{escape(href, quote=True)}">{text}</a>'
    elif inline.kind == "image":
        rendered = _render_image_inline(inline, asset_resolver=asset_resolver)
    elif inline.kind == "inline_equation":
        rendered = _render_inline_equation(inline)
    else:
        rendered = (
            '<span class="md2gost-inline-unsupported">'
            f"[unsupported inline: {escape(inline.kind)}]"
            "</span>"
        )
    return _wrap_inline_formatting(rendered, inline)


def _safe_link_href(raw_href: str) -> str | None:
    # Browsers ignore ASCII controls around schemes, so normalize them before
    # checking. Relative URLs and internal anchors have no scheme and remain valid.
    scheme_probe = re.sub(r"[\x00-\x20]+", "", raw_href)
    scheme = urlsplit(scheme_probe).scheme.lower()
    if scheme and scheme not in _SAFE_LINK_SCHEMES:
        return None
    return raw_href


def _docx_text(text: str) -> str:
    return text.replace("-", "\u2011")


def _wrap_inline_formatting(rendered: str, inline: PreviewInline) -> str:
    if inline.underline:
        rendered = f"<u>{rendered}</u>"
    if inline.strike:
        rendered = f"<s>{rendered}</s>"
    if inline.italic:
        rendered = f"<em>{rendered}</em>"
    if inline.bold:
        rendered = f"<strong>{rendered}</strong>"
    return rendered


def _render_code_inline(inline: PreviewInline, raw_text: str) -> str:
    attrs = ""
    declarations: list[str] = []
    if inline.font_family:
        declarations.append(f"font-family: {_css_value(inline.font_family)};")
    if inline.font_size:
        declarations.append(f"font-size: {_css_value(inline.font_size)};")
    if declarations:
        attrs = f' style="{escape(" ".join(declarations), quote=True)}"'
    return f"<code{attrs}>{escape(raw_text)}</code>"


def _render_inline_equation(inline: PreviewInline) -> str:
    data_latex = escape(inline.text or "", quote=True)
    if inline.mathml is None:
        diagnostic = escape(inline.diagnostic or "invalid equation")
        return (
            '<span class="md2gost-equation md2gost-inline-equation '
            'md2gost-equation-invalid" role="note" '
            f'data-latex="{data_latex}">'
            f"[Invalid equation: {diagnostic}]"
            "</span>"
        )
    if _should_render_native_inline_math(inline.text or ""):
        mathml = _mathml_with_display(inline.mathml, "inline")
        return (
            '<span class="md2gost-equation md2gost-inline-equation" '
            f'data-latex="{data_latex}">'
            f'<span class="md2gost-equation-native">{mathml}</span>'
            "</span>"
        )
    return (
        '<span class="md2gost-equation md2gost-inline-equation" '
        f'data-latex="{data_latex}">'
        f'<span class="md2gost-equation-visual">{_latex_visual_html(inline.text or "")}</span>'
        f'<span hidden aria-hidden="true">{inline.mathml}</span>'
        "</span>"
    )


def _should_render_native_inline_math(latex: str) -> bool:
    return any(command in _NATIVE_INLINE_MATH_COMMANDS for command in _latex_commands(latex))


def _latex_commands(latex: str) -> list[str]:
    commands: list[str] = []
    i = 0
    while i < len(latex):
        if latex[i] != "\\":
            i += 1
            continue
        command, i = _latex_command(latex, i + 1)
        if command:
            commands.append(command)
    return commands


def _latex_visual_html(latex: str) -> str:
    compact = "".join(latex.split())
    out: list[str] = []
    i = 0
    while i < len(compact):
        char = compact[i]
        if char in {"^", "_"}:
            tag = "sup" if char == "^" else "sub"
            value, i = _latex_script_value(compact, i + 1)
            out.append(f"<{tag}>{_latex_visual_html(value)}</{tag}>")
            continue
        if char == "\\":
            command, i = _latex_command(compact, i + 1)
            out.append(escape(_latex_command_visual(command)))
            continue
        if char in "{}":
            i += 1
            continue
        out.append(escape(char))
        i += 1
    return "".join(out)


def _latex_script_value(latex: str, start: int) -> tuple[str, int]:
    if start >= len(latex):
        return "", start
    if latex[start] != "{":
        return latex[start], start + 1
    depth = 1
    i = start + 1
    while i < len(latex) and depth:
        if latex[i] == "{":
            depth += 1
        elif latex[i] == "}":
            depth -= 1
        i += 1
    return latex[start + 1 : i - 1], i


def _latex_command(latex: str, start: int) -> tuple[str, int]:
    i = start
    while i < len(latex) and latex[i].isalpha():
        i += 1
    if i == start and i < len(latex):
        return latex[i], i + 1
    return latex[start:i], i


def _latex_command_visual(command: str) -> str:
    return {
        "alpha": "α",
        "beta": "β",
        "gamma": "γ",
        "delta": "δ",
        "epsilon": "ε",
        "lambda": "λ",
        "mu": "μ",
        "pi": "π",
        "sigma": "σ",
        "sqrt": "√",
    }.get(command, command)


def _render_equation_block(block: PreviewBlock, styles: _StyleRegistry) -> str:
    class_name = styles.class_for(block.style)
    number = escape(_equation_number_text(block), quote=False)
    data_number = escape(block.number or "", quote=True)
    data_latex = escape(block.text, quote=True)
    number_alignment = escape(
        str(block.style.get("numbering_alignment") or "right"),
        quote=True,
    )
    if block.mathml is None:
        diagnostic = escape(block.diagnostic or "invalid equation")
        formula = (
            '<span class="md2gost-equation-invalid" role="note">'
            f"[Invalid equation: {diagnostic}]"
            "</span>"
        )
    else:
        formula = _mathml_with_display(block.mathml, "block")
    return (
        f'    <div id="{_id(block.id)}" '
        f'class="md2gost-block md2gost-equation-block {class_name}" '
        f'data-equation-number="{data_number}" data-latex="{data_latex}">\n'
        '      <div class="md2gost-equation-formula">'
        f"{formula}"
        "</div>\n"
        '      <div class="md2gost-equation-number" '
        f'style="text-align: {number_alignment};">'
        f"{number}"
        "</div>\n"
        "    </div>"
    )


def _equation_number_text(block: PreviewBlock) -> str:
    if block.number is None:
        return ""
    if block.style.get("parentheses") is False:
        return block.number
    return f"({block.number})"


def _mathml_with_display(mathml: str, display: str) -> str:
    opening_end = mathml.find(">")
    if opening_end == -1:
        return mathml
    opening = mathml[:opening_end]
    if " display=" in opening:
        return re.sub(
            r'(<math\b[^>]*\sdisplay=)["\'][^"\']*["\']',
            rf'\1"{display}"',
            mathml,
            count=1,
        )
    return f'{mathml[:opening_end]} display="{display}"{mathml[opening_end:]}'


def _render_image_block(
    block: PreviewBlock,
    styles: _StyleRegistry,
    asset_resolver: AssetResolver | None,
) -> str:
    class_name = styles.class_for(block.style)
    image = block.inlines[0] if block.inlines else None
    rendered_image = (
        _render_image_inline(image, block=True, asset_resolver=asset_resolver)
        if image is not None
        else '<span class="md2gost-inline-unsupported">[image]</span>'
    )
    caption = ""
    if block.caption:
        caption = (
            f'<figcaption class="md2gost-image-caption md2gost-flow-text {class_name}">'
            f"{escape(block.caption)}"
            "</figcaption>"
        )
    return (
        f'    <figure id="{_id(block.id)}" '
        'class="md2gost-block md2gost-image-block" '
        f'data-image-number="{escape(block.number or "", quote=True)}">'
        f"{rendered_image}"
        f"{caption}"
        "</figure>"
    )


def _render_image_inline(
    inline: PreviewInline,
    *,
    block: bool = False,
    asset_resolver: AssetResolver | None = None,
) -> str:
    raw_src = inline.src or ""
    if asset_resolver is not None and inline.asset_path:
        raw_src = asset_resolver(inline.asset_path)
    src = escape(raw_src, quote=True)
    alt = escape(inline.alt or "", quote=True)
    attrs = [
        f'src="{src}"',
        f'alt="{alt}"',
        'loading="lazy"',
        'decoding="async"',
    ]
    if inline.title:
        attrs.append(f'title="{escape(inline.title, quote=True)}"')
    width_attr = _image_pixel_attr(inline.width)
    height_attr = _image_pixel_attr(inline.height)
    if width_attr is not None:
        attrs.append(f'width="{width_attr}"')
    if height_attr is not None:
        attrs.append(f'height="{height_attr}"')
    classes = ["md2gost-image"]
    classes.append("md2gost-image-standalone" if block else "md2gost-image-inline")
    attrs.append(f'class="{" ".join(classes)}"')
    style = _image_style(inline, block=block)
    if style:
        attrs.append(f'style="{escape(style, quote=True)}"')
    return f"<img {' '.join(attrs)}>"


def _image_pixel_attr(dimension: PreviewImageDimension | None) -> str | None:
    if dimension is None:
        return None
    if dimension.unit != "px":
        return None
    numeric = float(dimension.value)
    if not numeric.is_integer() or numeric <= 0:
        return None
    return str(int(numeric))


def _image_style(inline: PreviewInline, *, block: bool) -> str:
    declarations: list[str] = []
    width = _dimension_css(inline.width)
    height = _dimension_css(inline.height)
    if width is not None:
        declarations.append(f"width: {width};")
    elif block and height is None:
        declarations.append("width: 100%;")
        declarations.append("max-width: 100%;")
    elif block:
        declarations.append("width: auto;")
    if height is not None:
        declarations.append(f"height: {height};")
    else:
        declarations.append("height: auto;")
    if inline.aspect_ratio:
        declarations.append(f"aspect-ratio: {_css_value(inline.aspect_ratio)};")
    declarations.append("object-fit: contain;")
    return " ".join(declarations)


def _dimension_css(dimension: PreviewImageDimension | None) -> str | None:
    if dimension is None:
        return None
    formatted = f"{float(dimension.value):.4f}".rstrip("0").rstrip(".")
    return f"{formatted}{_css_value(dimension.unit)}"


def _bool_attr(value: bool | None) -> str:
    return "true" if value else "false"


def _caption_style_from_block(
    style: dict[str, JsonPrimitive],
) -> dict[str, JsonPrimitive]:
    prefix = "caption_"
    return {name[len(prefix) :]: value for name, value in style.items() if name.startswith(prefix)}


def _table_dimension_css(dimension: PreviewTableDimension) -> str | None:
    if dimension.unit == "auto":
        return None
    formatted = f"{float(dimension.value):.4f}".rstrip("0").rstrip(".")
    return f"{formatted}{dimension.unit}"


def _render_unsupported_block(block: PreviewBlock) -> str:
    text = escape(block.text) if block.text else "not rendered by basic HTML preview"
    return (
        f'    <div id="{_id(block.id)}" '
        'class="md2gost-block md2gost-unsupported" role="note">'
        f"Unsupported preview block: {escape(block.kind)}. {text}"
        "</div>"
    )


def _heading_tag(level: int | None) -> str:
    normalized = min(6, max(1, level or 1))
    return f"h{normalized}"


def _render_css(document: PreviewDocument, styles: _StyleRegistry) -> str:
    geometry = document.geometry
    margins = geometry.margins
    page_width = _length(geometry.width.value, geometry.width.unit)
    page_height = _length(geometry.height.value, geometry.height.unit)
    padding = " ".join(
        [
            _length(margins.top.value, margins.top.unit),
            _length(margins.right.value, margins.right.unit),
            _length(margins.bottom.value, margins.bottom.unit),
            _length(margins.left.value, margins.left.unit),
        ]
    )
    css = [
        "    html, body {",
        "      margin: 0;",
        "      padding: 0;",
        "      background: #eef0f2;",
        "      color: #111;",
        "    }",
        "    .md2gost-preview {",
        "      box-sizing: border-box;",
        "      display: flex;",
        "      flex-direction: column;",
        "      align-items: center;",
        "      gap: 8mm;",
        "      padding: 8mm 0;",
        "    }",
        "    .md2gost-page {",
        "      box-sizing: border-box;",
        "      position: relative;",
        f"      width: {page_width};",
        f"      height: {page_height};",
        f"      padding: {padding};",
        "      overflow: hidden;",
        "      background: #fff;",
        "      box-shadow: 0 1mm 4mm rgba(0, 0, 0, 0.18);",
        "    }",
        "    .md2gost-page::after {",
        "      content: attr(data-md2gost-page);",
        "      position: absolute;",
        f"      right: {_length(margins.right.value, margins.right.unit)};",
        f"      bottom: {_PAGE_NUMBER_BOTTOM};",
        f"      left: {_length(margins.left.value, margins.left.unit)};",
        "      color: #000;",
        "      font-family: Times New Roman, serif;",
        "      font-size: 14pt;",
        "      line-height: 1;",
        "      text-align: center;",
        "    }",
        "    .md2gost-page--unnumbered::after {",
        "      content: none;",
        "    }",
        "    .md2gost-block {",
        "      box-sizing: border-box;",
        "    }",
        "    .md2gost-flow-text {",
        "      transform: translateY(var(--md2gost-leading-offset));",
        "    }",
        "    .md2gost-title-page {",
        "      display: flex;",
        "      flex-direction: column;",
        "      height: 100%;",
        "      padding-top: 80pt;",
        "      padding-bottom: 28pt;",
        "      font-family: Times New Roman, serif;",
        "      font-size: 14pt;",
        "      line-height: 1.1464;",
        "    }",
        "    .md2gost-title-page-header,",
        "    .md2gost-title-page-organization,",
        "    .md2gost-title-page-work {",
        "      text-align: center;",
        "    }",
        "    .md2gost-title-page-header-line {",
        "      white-space: pre-line;",
        "    }",
        "    .md2gost-title-page-header-line--institution-full-name {",
        "      font-size: 11pt;",
        "      font-style: italic;",
        "    }",
        "    .md2gost-title-page-header-line--university-name {",
        "      font-weight: 700;",
        "    }",
        "    .md2gost-title-page-header-line--university-short-name {",
        "      font-size: 16pt;",
        "      font-weight: 700;",
        "    }",
        "    .md2gost-title-page-divider {",
        "      border-bottom: 0.5pt solid #000;",
        "      margin: 18pt 0 6pt;",
        "    }",
        "    .md2gost-title-page-organization-line + .md2gost-title-page-organization-line {",
        "      margin-top: 16pt;",
        "    }",
        "    .md2gost-title-page-work {",
        "      margin-top: 48pt;",
        "    }",
        "    .md2gost-title-page-work-line--work-title {",
        "      font-size: 16pt;",
        "      font-weight: 700;",
        "    }",
        "    .md2gost-title-page-work-line--work-subject {",
        "      margin-top: 16pt;",
        "    }",
        "    .md2gost-title-page-work-line--work-topic {",
        "      font-weight: 700;",
        "    }",
        "    .md2gost-title-page-signatures {",
        "      margin-top: 96pt;",
        "    }",
        "    .md2gost-title-page-signature-section + .md2gost-title-page-signature-section {",
        "      margin-top: 12pt;",
        "    }",
        "    .md2gost-title-page-signature-title {",
        "      font-weight: 700;",
        "      margin-bottom: 2pt;",
        "    }",
        "    .md2gost-title-page-signature-row {",
        "      display: grid;",
        "      grid-template-columns: minmax(0, 1fr) auto;",
        "      column-gap: 12pt;",
        "    }",
        "    .md2gost-title-page-signature-name {",
        "      text-align: right;",
        "    }",
        "    .md2gost-title-page-footer {",
        "      margin-top: auto;",
        "      text-align: center;",
        "    }",
        "    .md2gost-toc {",
        "      width: 100%;",
        "    }",
        "    .md2gost-toc-entry {",
        "      display: grid;",
        "      grid-template-columns: auto minmax(0, auto) minmax(0, 1fr) auto;",
        "      align-items: baseline;",
        "      min-width: 0;",
        "      padding-left: calc((var(--md2gost-toc-level) - 1) * 0.75cm);",
        "    }",
        "    .md2gost-toc-number {",
        "      white-space: pre;",
        "    }",
        "    .md2gost-toc-number:not(:empty)::after {",
        "      content: ' ';",
        "    }",
        "    .md2gost-toc-title {",
        "      min-width: 0;",
        "    }",
        "    .md2gost-toc-link {",
        "      color: #000;",
        "      text-decoration: none;",
        "    }",
        "    .md2gost-toc-leader {",
        "      align-self: baseline;",
        "      border-bottom: 1px dotted currentColor;",
        "      margin: 0 0.15em;",
        "    }",
        "    .md2gost-toc-leader--none {",
        "      border-bottom: 0;",
        "    }",
        "    .md2gost-toc-page-number {",
        "      text-align: right;",
        "      white-space: nowrap;",
        "    }",
        "    .md2gost-list-item {",
        "      white-space: pre-wrap;",
        "    }",
        "    .md2gost-image-block {",
        "      margin: 0;",
        "      text-align: center;",
        "    }",
        "    .md2gost-image {",
        "      box-sizing: border-box;",
        "      max-width: 100%;",
        "      vertical-align: middle;",
        "      border: 0;",
        "    }",
        "    .md2gost-image-standalone {",
        "      display: block;",
        "      margin: 0 auto;",
        "    }",
        "    .md2gost-table {",
        "      width: 100%;",
        "      table-layout: fixed;",
        "      border-collapse: collapse;",
        "      margin: 0;",
        "      margin-left: -5.4pt;",
        "    }",
        "    .md2gost-table caption {",
        "      caption-side: top;",
        "      text-align: left;",
        "      margin-left: 5.4pt;",
        "    }",
        "    .md2gost-table th {",
        "      font-weight: var(--md2gost-table-header-font-weight);",
        "    }",
        "    .md2gost-table th, .md2gost-table td {",
        "      border: 0.5pt solid #000;",
        "      padding: 2.75pt 5.4pt;",
        "      vertical-align: top;",
        "      overflow-wrap: break-word;",
        "    }",
        "    .md2gost-listing-block {",
        "      margin: 0;",
        "    }",
        "    .md2gost-listing-caption {",
        "      display: block;",
        "      text-align: left;",
        "    }",
        "    .md2gost-listing {",
        "      box-sizing: border-box;",
        "      width: 100%;",
        "      margin: 0;",
        "      margin-left: -4pt;",
        "      padding: 2pt 4pt;",
        "      border: 0.5pt solid #000;",
        "      white-space: pre;",
        "      overflow: hidden;",
        "    }",
        "    .md2gost-listing-highlighted code::after {",
        '      content: "";',
        "      display: block;",
        "      height: 1lh;",
        "    }",
        "    .md2gost-inline-equation {",
        "      display: inline;",
        "      max-width: 100%;",
        "      line-height: normal;",
        "      vertical-align: baseline;",
        "    }",
        "    .md2gost-inline-equation [hidden] {",
        "      display: none !important;",
        "    }",
        "    .md2gost-equation-visual {",
        "      font-style: italic;",
        "      white-space: nowrap;",
        "    }",
        "    .md2gost-equation-visual sup, .md2gost-equation-visual sub {",
        "      font-size: 70%;",
        "      line-height: 0;",
        "    }",
        "    .md2gost-equation-native {",
        "      display: inline-block;",
        "      line-height: 1;",
        "      vertical-align: -0.2em;",
        "    }",
        "    .md2gost-equation-native math {",
        "      font-size: 95%;",
        "    }",
        "    .md2gost-equation-block {",
        "      display: grid;",
        "      grid-template-columns: minmax(0, 1fr) 36pt;",
        "      column-gap: 0;",
        "      align-items: center;",
        "      width: 100%;",
        "    }",
        "    .md2gost-equation-formula {",
        "      min-width: 0;",
        "      text-align: center;",
        "      overflow-wrap: anywhere;",
        "    }",
        "    .md2gost-equation-formula math {",
        "      max-width: 100%;",
        "    }",
        "    .md2gost-equation-number {",
        "      white-space: nowrap;",
        "    }",
        "    .md2gost-equation-invalid {",
        "      color: #b00020;",
        "      background: #ffe8e8;",
        "      font-style: italic;",
        "    }",
        "    .md2gost-page-break {",
        "      display: none;",
        "    }",
        "    .md2gost-unsupported, .md2gost-inline-unsupported {",
        "      color: #8a4b00;",
        "      background: #fff4d8;",
        "    }",
        "    @media print {",
        "      html, body { background: #fff; }",
        "      .md2gost-preview { gap: 0; padding: 0; }",
        "      .md2gost-page { box-shadow: none; break-after: page; }",
        "      .md2gost-page:last-child { break-after: auto; }",
        "    }",
        f"    @page {{ size: {page_width} {page_height}; margin: 0; }}",
    ]
    css.extend(styles.rules())
    return "\n".join(css)


def _length(value: float, unit: str) -> str:
    formatted = f"{value:.4f}".rstrip("0").rstrip(".")
    return f"{formatted}{unit}"


def _id(value: str) -> str:
    return escape(value, quote=True)


class _StyleRegistry:
    def __init__(self) -> None:
        self._classes: dict[tuple[tuple[str, JsonPrimitive], ...], str] = {}
        self._rules: list[tuple[str, dict[str, JsonPrimitive]]] = []

    def class_for(self, style: dict[str, JsonPrimitive]) -> str:
        key = tuple(sorted(style.items()))
        existing = self._classes.get(key)
        if existing is not None:
            return existing
        class_name = f"md2gost-block-style-{len(self._classes) + 1}"
        self._classes[key] = class_name
        self._rules.append((class_name, dict(style)))
        return class_name

    def rules(self) -> list[str]:
        return [_style_rule(class_name, style) for class_name, style in self._rules]


def _style_rule(class_name: str, style: dict[str, JsonPrimitive]) -> str:
    declarations = [
        _declaration("font-family", style.get("font_family")),
        _declaration("font-size", style.get("font_size")),
        _line_height_declaration(style),
        _leading_offset_declaration(style),
        _declaration("text-align", style.get("alignment")),
        _declaration("text-indent", style.get("indent_first_line")),
        _declaration("margin-left", style.get("margin_left")),
        _declaration("text-indent", style.get("text_indent")),
        _declaration("margin-top", style.get("space_before", "0pt")),
        _declaration("margin-bottom", style.get("space_after", "0pt")),
        _declaration("padding-top", style.get("padding_before")),
        _declaration("padding-bottom", style.get("padding_after")),
        _font_weight_declaration(style),
        _font_style_declaration(style),
        _table_header_weight_declaration(style),
    ]
    body = "\n".join(f"      {item}" for item in declarations if item is not None)
    return f"    .{class_name} {{\n{body}\n    }}"


def _line_height_declaration(style: dict[str, JsonPrimitive]) -> str | None:
    line_spacing = style.get("line_spacing")
    if line_spacing is None or line_spacing is False:
        return None
    factor = _docx_line_height_factor(style)
    return f"line-height: {_format_css_number(factor)};"


def _leading_offset_declaration(
    style: dict[str, JsonPrimitive],
) -> str | None:
    line_spacing = style.get("line_spacing")
    if line_spacing is None or line_spacing is False:
        return None
    font_size_pt = _font_size_pt(style.get("font_size"))
    if font_size_pt is None:
        return None
    try:
        spacing = float(line_spacing)
    except (TypeError, ValueError):
        return None
    font_family = str(style.get("font_family") or "")
    line_height_pt = _calibrated_line_height_pt(font_family, font_size_pt)
    offset_pt = (font_size_pt - line_height_pt * spacing) / 2.0
    return f"--md2gost-leading-offset: {_format_css_number(offset_pt)}pt;"


def _font_weight_declaration(style: dict[str, JsonPrimitive]) -> str | None:
    value = style.get("bold")
    if not isinstance(value, bool):
        return None
    return f"font-weight: {700 if value else 400};"


def _font_style_declaration(style: dict[str, JsonPrimitive]) -> str | None:
    value = style.get("italic")
    if not isinstance(value, bool):
        return None
    return f"font-style: {'italic' if value else 'normal'};"


def _table_header_weight_declaration(
    style: dict[str, JsonPrimitive],
) -> str | None:
    value = style.get("header_bold")
    if not isinstance(value, bool):
        return None
    return f"--md2gost-table-header-font-weight: {700 if value else 400};"


def _docx_line_height_factor(style: dict[str, JsonPrimitive]) -> float:
    try:
        spacing = float(style.get("line_spacing") or 1.0)
    except (TypeError, ValueError):
        return 1.0
    font_size_pt = _font_size_pt(style.get("font_size"))
    if font_size_pt is None:
        return spacing
    font_family = str(style.get("font_family") or "")
    line_height_pt = _calibrated_line_height_pt(font_family, font_size_pt)
    return spacing * line_height_pt / font_size_pt


def _calibrated_line_height_pt(font_family: str, font_size_pt: float) -> float:
    rounded = int(round(font_size_pt))
    for (name_fragment, size), line_height in _LINE_HEIGHT_CALIBRATION.items():
        if size == rounded and name_fragment in font_family:
            return line_height
    return font_size_pt


def _font_size_pt(value: JsonPrimitive) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    if not text.endswith("pt"):
        return None
    try:
        return float(text[:-2])
    except ValueError:
        return None


def _format_css_number(value: float) -> str:
    return f"{value:.4f}".rstrip("0").rstrip(".")


def _declaration(name: str, value: JsonPrimitive) -> str | None:
    if value is None or value is False:
        return None
    return f"{name}: {_css_value(value)};"


def _css_value(value: JsonPrimitive) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    escapes = {
        "\\": "\\5c ",
        ";": "\\3b ",
        "{": "\\7b ",
        "}": "\\7d ",
        "<": "\\3c ",
        ">": "\\3e ",
    }
    return "".join(escapes.get(character, character) for character in str(value))
