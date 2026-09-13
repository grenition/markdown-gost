from __future__ import annotations

from dataclasses import replace

from lxml import html

from markdown_gost.config.loader import load_config_from_string
from markdown_gost.config.schema import Config
from markdown_gost.preview import build_preview_model, render_preview_html
from markdown_gost.preview.model import PreviewBlock, PreviewImageDimension, PreviewInline


class UnavailableStorage:
    def fetch(self, src: str) -> bytes:
        raise AssertionError(f"unexpected fetch for {src}")

    def exists(self, src: str) -> bool:
        return False

    def stat(self, src: str) -> object:
        raise AssertionError(f"unexpected stat for {src}")

    def put(self, key: str, data: bytes) -> None:
        raise AssertionError(f"unexpected put for {key}")


def _config(overrides: str = "") -> Config:
    return load_config_from_string(f"preset: default\n{overrides}")


def _parse(rendered: str) -> html.HtmlElement:
    return html.fromstring(rendered)


def test_rendered_html_is_valid_document_without_duplicate_ids_or_scripts() -> None:
    model = build_preview_model("# Intro\n\nBody\n", _config())

    rendered = render_preview_html(model)
    root = _parse(rendered)
    ids = root.xpath("//*[@id]/@id")

    assert root.xpath("string(/html/head/title)") == "markdown-gost preview"
    assert rendered.startswith("<!doctype html>")
    assert len(ids) == len(set(ids))
    assert root.xpath("//script") == []


def test_preview_style_values_cannot_break_out_of_style_element() -> None:
    model = build_preview_model("Body\n", _config())
    payload = "</style><script>window.previewStyleInjected = true</script><style>"
    block = replace(
        model.pages[0].blocks[0],
        style={"font_family": payload, "font_size": "14pt"},
    )
    model = replace(
        model,
        pages=[replace(model.pages[0], blocks=[block])],
    )

    rendered = render_preview_html(model)
    root = _parse(rendered)

    assert payload not in rendered
    assert root.xpath("//script") == []
    assert "previewStyleInjected" not in root.xpath("string(/html/body)")


def test_preview_image_dimensions_cannot_inject_css_declarations() -> None:
    model = build_preview_model("Body\n", _config())
    unit_payload = "px; background-image: url(https://attacker.invalid/unit)"
    ratio_payload = "1 / 1; background-image: url(https://attacker.invalid/ratio)"
    inline = PreviewInline(
        kind="image",
        src="/safe.png",
        width=PreviewImageDimension(value=10, unit=unit_payload),
        aspect_ratio=ratio_payload,
    )
    block = replace(model.pages[0].blocks[0], text="", inlines=[inline])
    model = replace(model, pages=[replace(model.pages[0], blocks=[block])])

    rendered = render_preview_html(model)

    assert unit_payload not in rendered
    assert ratio_payload not in rendered
    assert "; background-image:" not in rendered


def test_page_shell_uses_preview_geometry() -> None:
    cfg = _config(
        "overrides:\n"
        "  page:\n"
        "    size: A3\n"
        "    orientation: landscape\n"
        "    margins:\n"
        "      top: 10mm\n"
        "      right: 15mm\n"
        "      bottom: 20mm\n"
        "      left: 30mm\n"
    )
    model = build_preview_model("Text\n", cfg)

    rendered = render_preview_html(model)
    root = _parse(rendered)
    style = root.xpath("string(/html/head/style)")

    assert ".md2gost-page" in style
    assert "width: 420mm;" in style
    assert "height: 297mm;" in style
    assert "padding: 10mm 15mm 20mm 30mm;" in style
    assert "content: attr(data-md2gost-page);" in style
    assert "bottom: 12.8mm;" in style
    assert "right: 15mm;" in style
    assert "left: 30mm;" in style
    assert root.xpath("//section[@data-md2gost-page='1']/@id") == ["page-1"]


def test_paragraph_and_heading_styles_are_mapped_from_preview_model() -> None:
    cfg = _config(
        "overrides:\n"
        "  font:\n"
        "    family: Arial\n"
        "    size: 12pt\n"
        "    line_spacing: 1.25\n"
        "  paragraph:\n"
        "    alignment: left\n"
        "    indent_first_line: 7mm\n"
        "  headings:\n"
        "    levels:\n"
        "      2:\n"
        "        size: 16pt\n"
        "        alignment: center\n"
        "        indent_first_line: 0cm\n"
        "        space_before: 6pt\n"
        "        space_after: 3pt\n"
    )
    model = build_preview_model("## Styled\n\nBody\n", cfg)

    root = _parse(render_preview_html(model))
    style = root.xpath("string(/html/head/style)")
    heading_class = root.xpath("//h2[contains(@class, 'md2gost-heading')]/@class")[0]
    paragraph_class = root.xpath("//p[contains(@class, 'md2gost-paragraph')]/@class")[0]

    assert "font-family: Arial;" in style
    assert "font-size: 16pt;" in style
    assert "text-align: center;" in style
    assert "text-indent: 0cm;" in style
    assert "margin-top: 6pt;" in style
    assert "margin-bottom: 3pt;" in style
    assert "font-size: 12pt;" in style
    assert "line-height: 1.25;" in style
    assert "text-align: left;" in style
    assert "text-indent: 7mm;" in style
    assert "md2gost-block-style-" in heading_class
    assert "md2gost-block-style-" in paragraph_class
    assert "md2gost-flow-text" in heading_class
    assert "md2gost-flow-text" in paragraph_class
    assert "--md2gost-leading-offset: -1.5pt;" in style


def test_heading_style_resets_disabled_browser_default_emphasis() -> None:
    cfg = _config(
        "overrides:\n"
        "  headings:\n"
        "    levels:\n"
        "      3:\n"
        "        bold: false\n"
        "        italic: false\n"
    )
    model = build_preview_model("### Plain heading\n", cfg)

    style = _parse(render_preview_html(model)).xpath("string(/html/head/style)")

    assert "font-weight: 400;" in style
    assert "font-style: normal;" in style


def test_page_break_renders_as_hidden_marker_between_pages() -> None:
    model = build_preview_model("Before\n\n::: {.page-break}\n:::\n\nAfter\n", _config())

    root = _parse(render_preview_html(model))
    style = root.xpath("string(/html/head/style)")

    assert root.xpath("//section[@data-md2gost-page]/@data-md2gost-page") == ["1", "2"]
    assert root.xpath("//div[contains(@class, 'md2gost-page-break')]/@data-kind") == ["hard"]
    assert root.xpath("//div[contains(@class, 'md2gost-page-break')]/@aria-hidden") == ["true"]
    assert ".md2gost-page-break" in style
    assert "display: none;" in style


def test_titlepage_template_is_visible_in_html_before_following_page() -> None:
    model = build_preview_model(
        '::: {.template name="titlepage-university"}\n'
        "title: Preview title\n"
        "city: МОСКВА\n"
        "year: 2026 г.\n"
        ":::\n\n"
        "Following content\n",
        _config(),
    )

    root = _parse(render_preview_html(model))

    assert root.xpath("//section[@data-md2gost-page='1']//text()[contains(., 'Preview title')]")
    assert root.xpath("//section[@data-md2gost-page='2']//text()[contains(., 'Following content')]")


def test_titlepage_template_renders_divider_signature_columns_and_bottom_footer() -> None:
    root = _parse(
        render_preview_html(
            build_preview_model(
                '::: {.template name="titlepage-university"}\n'
                "title: Preview title\n"
                "authors:\n"
                "  - label: Student\n"
                "    names: [Author]\n"
                "reviewers:\n"
                "  - label: Reviewer\n"
                "    names: [Teacher]\n"
                "city: МОСКВА\n"
                "year: 2026 г.\n"
                ":::\n",
                _config(),
            )
        )
    )
    style = root.xpath("string(/html/head/style)")

    title_page = root.xpath(
        "//section[@data-md2gost-page='1']//article[contains(@class, 'md2gost-title-page')]"
    )
    assert title_page
    assert root.xpath("//div[contains(@class, 'md2gost-title-page-divider')]")
    signature_labels = root.xpath(
        "//div[contains(@class, 'md2gost-title-page-signature-row')]/span[1]/text()"
    )
    assert signature_labels == [
        "Student",
        "Reviewer",
    ]
    footer = root.xpath("string(//footer[contains(@class, 'md2gost-title-page-footer')])")
    assert footer == "МОСКВА 2026 г."
    assert root.xpath(
        "//section[@data-md2gost-page='1'][contains(@class, 'md2gost-page--unnumbered')]"
    )
    assert "grid-template-columns: minmax(0, 1fr) auto;" in style
    assert ".md2gost-page--unnumbered::after" in style
    assert "content: none;" in style
    assert "margin-top: auto;" in style
    assert "padding-top: 80pt;" in style
    assert "margin: 18pt 0 6pt;" in style
    assert "margin-top: 96pt;" in style


def test_content_template_renders_indented_rows_with_leader_and_plain_links() -> None:
    model = build_preview_model(
        '::: {.template name="content"}\n:::\n\n# Intro\n\n## Details\n', _config()
    )
    root = _parse(render_preview_html(model))
    style = root.xpath("string(/html/head/style)")
    entries = root.xpath("//div[contains(@class, 'md2gost-toc-entry')]")

    assert len(entries) == 2
    assert [entry.get("data-toc-level") for entry in entries] == ["1", "2"]
    assert [entry.xpath("string(.//a)") for entry in entries] == ["Intro", "Details"]
    assert [
        entry.xpath("string(.//span[contains(@class, 'md2gost-toc-page-number')])")
        for entry in entries
    ] == [str(anchor.page) for anchor in model.anchors]
    assert "text-decoration: none;" in style
    assert "color: #000;" in style
    assert "border-bottom: 1px dotted currentColor;" in style
    assert "padding-left: calc((var(--md2gost-toc-level) - 1) * 0.75cm);" in style


def test_content_template_toc_uses_configured_flow_text_style_and_calibration() -> None:
    cfg = _config(
        "overrides:\n  font:\n    family: Arial\n    size: 14pt\n    line_spacing: 1.25\n"
    )
    root = _parse(
        render_preview_html(build_preview_model('::: {.template name="content"}\n:::\n', cfg))
    )
    style = root.xpath("string(/html/head/style)")
    toc_class = root.xpath("//nav[contains(@class, 'md2gost-toc')]/@class")[0]

    assert "md2gost-flow-text" in toc_class
    assert "md2gost-block-style-" in toc_class
    assert "font-family: Arial;" in style
    assert "font-size: 14pt;" in style
    assert "line-height: 1.433;" in style
    assert "--md2gost-leading-offset: -3.0312pt;" in style


def test_internal_anchors_resolve() -> None:
    model = build_preview_model("# Target\n\nBody\n", _config())
    target = model.anchors[0].anchor
    paragraph = model.pages[0].blocks[1]
    paragraph.inlines.append(PreviewInline(kind="link", text="jump", href=f"#{target}"))

    root = _parse(render_preview_html(model))
    ids = set(root.xpath("//*[@id]/@id"))
    internal_hrefs = root.xpath("//a[starts-with(@href, '#')]/@href")

    assert internal_hrefs == [f"#{target}"]
    assert all(href[1:] in ids for href in internal_hrefs)


def test_links_drop_unsafe_url_schemes() -> None:
    model = build_preview_model("Body\n", _config())
    paragraph = model.pages[0].blocks[0]
    paragraph.inlines.clear()
    paragraph.inlines.extend(
        [
            PreviewInline(kind="link", text="safe", href="https://example.test/doc"),
            PreviewInline(kind="text", text=" "),
            PreviewInline(kind="link", text="bad", href="java\nscript:alert(1)"),
            PreviewInline(kind="text", text=" "),
            PreviewInline(kind="link", text="file", href="file:///etc/passwd"),
        ]
    )

    rendered = render_preview_html(model)
    root = _parse(rendered)

    assert root.xpath("//a/@href") == ["https://example.test/doc"]
    assert "safe bad file" in root.xpath("string(//body)")
    assert "javascript:" not in rendered.lower()
    assert "file:///" not in rendered.lower()


def test_unsupported_blocks_are_visible_diagnostics() -> None:
    model = build_preview_model("Body\n", _config())
    model.pages[0].blocks.append(
        PreviewBlock(kind="unknown", id="unknown-1", page=1, text="unsupported block")
    )

    root = _parse(render_preview_html(model))

    assert root.xpath("//div[contains(@class, 'md2gost-unsupported')]/@id") == ["unknown-1"]
    assert "Unsupported preview block: unknown" in root.xpath(
        "string(//div[contains(@class, 'md2gost-unsupported')])"
    )


def test_lists_render_with_explicit_markers_and_configured_spacing() -> None:
    cfg = _config(
        "overrides:\n"
        "  font:\n"
        "    line_spacing: 1.35\n"
        "  lists:\n"
        '    bullet_marker: "•"\n'
        "    indent_left: 2cm\n"
        "    indent_per_level: 0.5cm\n"
    )
    model = build_preview_model("- First\n- Second\n", cfg)

    root = _parse(render_preview_html(model))
    style = root.xpath("string(/html/head/style)")
    items = root.xpath("//div[contains(@class, 'md2gost-list-item')]")

    assert root.xpath("//ol|//ul|//li") == []
    assert len(items) == 2
    assert items[0].xpath("string(.//span[contains(@class, 'md2gost-list-marker')])") == "•"
    assert items[0].xpath("string(.//span[contains(@class, 'md2gost-list-content')])") == "First"
    assert items[0].get("data-list-type") == "unordered"
    assert items[0].get("data-list-level") == "1"
    assert "font-family: Times New Roman;" in style
    assert "line-height: 1.5477;" in style
    assert "margin-left: 2cm;" in style
    assert "text-indent: -0.5cm;" in style
    assert "margin-top: 0pt;" in style
    assert "margin-bottom: 0pt;" in style
    assert "md2gost-flow-text" in (items[0].get("class") or "")


def test_default_text_leading_offset_matches_docx_line_box_geometry() -> None:
    root = _parse(render_preview_html(build_preview_model("Body\n", _config())))
    style = root.xpath("string(/html/head/style)")

    assert "--md2gost-leading-offset: -5.0375pt;" in style
    assert "transform: translateY(var(--md2gost-leading-offset));" in style


def test_body_paragraphs_keep_docx_default_paragraph_spacing() -> None:
    root = _parse(render_preview_html(build_preview_model("First\n\nSecond\n", _config())))
    style = root.xpath("string(/html/head/style)")

    assert "margin-bottom: 10pt;" in style


def test_nested_ordered_lists_preserve_parent_numbering_in_html() -> None:
    markdown = "1. A\n    1. X\n    2. Y\n2. B\n\n1) Paren\n2) Next\n"

    root = _parse(render_preview_html(build_preview_model(markdown, _config())))
    items = root.xpath("//div[contains(@class, 'md2gost-list-item')]")

    assert [item.get("data-list-marker") for item in items] == [
        "1.",
        "1.1.",
        "1.2.",
        "2.",
        "1)",
        "2)",
    ]
    assert [item.get("data-list-level") for item in items[:4]] == ["1", "2", "2", "1"]
    assert [
        item.xpath("string(.//span[contains(@class, 'md2gost-list-separator')])")
        for item in items[:4]
    ] == ["\t", "  ", "  ", "\t"]


def test_inline_images_with_unknown_availability_keep_native_lazy_assets() -> None:
    model = build_preview_model(
        'Before ![Alt text](assets/my+image.png "Title") after.\n',
        _config(),
    )

    rendered = render_preview_html(model)
    root = _parse(rendered)
    image = root.xpath("//img[contains(@class, 'md2gost-image-inline')]")[0]

    assert "data:image" not in rendered
    assert "base64" not in rendered.lower()
    assert root.xpath("//script") == []
    assert root.xpath("//span[contains(@class, 'md2gost-inline-unsupported')]") == []
    assert image.get("src") == "/api/preview/assets/assets%2Fmy%2Bimage.png"
    assert image.get("alt") == "Alt text"
    assert image.get("title") == "Title"
    assert image.get("loading") == "lazy"
    assert image.get("decoding") == "async"
    assert root.xpath("//object") == []
    assert "aspect-ratio: 16 / 9;" in (image.get("style") or "")


def test_image_alt_preserves_authored_copy_including_empty_alt() -> None:
    model = build_preview_model(
        "До ![Схема](images/authored.png) и ![](images/empty.png).\n",
        _config(),
        UnavailableStorage(),
    )

    root = _parse(render_preview_html(model))

    assert root.xpath("//img/@alt") == ["Схема", ""]
    assert root.xpath("//img/@loading") == ["lazy", "lazy"]
    assert root.xpath("//img/@decoding") == ["async", "async"]


def test_inline_formatting_and_line_breaks_follow_docx_semantics() -> None:
    rendered = render_preview_html(
        build_preview_model(
            "Text **bold** *italic* ~~strike~~ [under]{.underline}\nsoft break.\n",
            _config(),
        )
    )
    root = _parse(rendered)
    paragraph = root.xpath("//p[contains(@class, 'md2gost-paragraph')]")[0]

    assert paragraph.xpath("string(.//strong)") == "bold"
    assert paragraph.xpath("string(.//em)") == "italic"
    assert paragraph.xpath("string(.//s)") == "strike"
    assert paragraph.xpath("string(.//u)") == "under"
    assert paragraph.xpath(".//br") == []
    assert "under soft break." in paragraph.xpath("string(.)")


def test_inline_code_uses_configured_quotes_font_and_size() -> None:
    cfg = _config(
        "overrides:\n"
        "  paragraph:\n"
        "    inline_code:\n"
        "      font: Courier New\n"
        "      size: 12pt\n"
        "      italic: true\n"
        "      quotes: true\n"
    )

    root = _parse(render_preview_html(build_preview_model("Code `x-y`.\n", cfg)))
    code = root.xpath("//code")[0]

    assert code.text == "«x‑y»"
    assert "font-family: Courier New;" in (code.get("style") or "")
    assert "font-size: 12pt;" in (code.get("style") or "")
    assert root.xpath("string(//em/code)") == "«x‑y»"


def test_inline_equations_render_mathml_without_line_height_breakage() -> None:
    rendered = render_preview_html(
        build_preview_model("Формула $x^2+y^2=z^2$ в строке.\n", _config())
    )
    root = _parse(rendered)
    style = root.xpath("string(/html/head/style)")
    equation = root.xpath("//span[contains(@class, 'md2gost-inline-equation')]")[0]

    assert root.xpath("//span[contains(@class, 'md2gost-inline-unsupported')]") == []
    assert equation.get("data-latex") == "x^2+y^2=z^2"
    visual = equation.xpath("string(.//span[contains(@class, 'md2gost-equation-visual')])")
    assert visual == "x2+y2=z2"
    assert equation.xpath(".//math")
    assert "line-height: normal;" in style
    assert "display: none !important;" in style


def test_complex_inline_equations_render_visible_mathml() -> None:
    rendered = render_preview_html(
        build_preview_model(
            "Сумма $\\sum_{i=1}^{n} x_i$ и предел $n \\to \\infty$.\n",
            _config(),
        )
    )
    root = _parse(rendered)
    equations = root.xpath("//span[contains(@class, 'md2gost-inline-equation')]")

    assert len(equations) == 2
    assert equations[0].xpath(".//span[contains(@class, 'md2gost-equation-native')]")
    assert equations[0].xpath(".//math[not(ancestor::*[@hidden])]")
    assert equations[0].xpath("string(.//math)") == "∑i=1nxi"
    assert equations[1].xpath("string(.//math)") == "n→∞"


def test_block_equations_render_numbered_mathml() -> None:
    root = _parse(render_preview_html(build_preview_model("$$ x=1 $$\n\n$$ y=2 $$\n", _config())))

    equations = root.xpath("//div[contains(@class, 'md2gost-equation-block')]")

    assert [equation.get("data-equation-number") for equation in equations] == [
        "1",
        "2",
    ]
    assert [
        equation.xpath("string(.//div[contains(@class, 'md2gost-equation-number')])")
        for equation in equations
    ] == ["(1)", "(2)"]
    assert equations[0].xpath(".//math")
    assert equations[0].xpath(".//math")[0].get("display") == "block"


def test_block_equations_use_configured_parentheses_alignment_and_spacing() -> None:
    cfg = _config(
        "overrides:\n"
        "  equation:\n"
        "    space_before: 6pt\n"
        "    space_after: 9pt\n"
        "    numbering_alignment: left\n"
        "    parentheses: false\n"
    )

    root = _parse(render_preview_html(build_preview_model("$$ a=b $$\n", cfg)))
    style = root.xpath("string(/html/head/style)")
    equation = root.xpath("//div[contains(@class, 'md2gost-equation-block')]")[0]
    number = equation.xpath(".//div[contains(@class, 'md2gost-equation-number')]")[0]

    assert equation.xpath("string(.//div[contains(@class, 'md2gost-equation-number')])") == "1"
    assert number.get("style") == "text-align: left;"
    assert "padding-top: 6pt;" in style
    assert "padding-bottom: 9pt;" in style
    assert "grid-template-columns: minmax(0, 1fr) 36pt;" in style


def test_invalid_latex_equations_render_visible_diagnostic_marker() -> None:
    rendered = render_preview_html(
        build_preview_model("Inline $\\frac$.\n\n$$ \\frac $$\n", _config())
    )
    root = _parse(rendered)

    diagnostics = root.xpath("//*[contains(@class, 'md2gost-equation-invalid')]")

    assert len(diagnostics) == 2
    assert "[Invalid equation:" in root.xpath("string(//body)")
    assert root.xpath("//span[contains(@class, 'md2gost-inline-equation')]/@role") == ["note"]
    assert root.xpath("//div[contains(@class, 'md2gost-equation-formula')]//*[@role]")[
        0
    ].text.startswith("[Invalid equation:")
    assert "<math" not in rendered


def test_image_asset_src_does_not_emit_literal_parent_segments() -> None:
    rendered = render_preview_html(build_preview_model("![bad](../secret.png)\n", _config()))

    root = _parse(rendered)
    src = root.xpath("//img/@src")[0]

    assert "../" not in src
    assert src == "/api/preview/assets/..%2Fsecret.png"


def test_explicit_pixel_image_size_renders_width_height_attributes() -> None:
    model = build_preview_model(
        "![Sized](images/sized.png){width=320px height=180px}\n",
        _config(),
    )

    root = _parse(render_preview_html(model))
    image = root.xpath("//img")[0]

    assert image.get("width") == "320"
    assert image.get("height") == "180"
    assert "width: 320px;" in (image.get("style") or "")
    assert "height: 180px;" in (image.get("style") or "")
    assert "aspect-ratio: 320 / 180;" in (image.get("style") or "")


def test_standalone_image_paragraph_renders_figure_with_caption() -> None:
    cfg = _config(
        "overrides:\n"
        "  captions:\n"
        "    image:\n"
        "      alignment: left\n"
        "      italic: true\n"
        '      format: "Рис. {number}. {text}"\n'
    )
    model = build_preview_model("![Схема](diagrams/main.png)\n", cfg)

    root = _parse(render_preview_html(model))
    figure = root.xpath("//figure[contains(@class, 'md2gost-image-block')]")[0]
    caption = figure.xpath("string(.//figcaption)")
    style = root.xpath("string(/html/head/style)")

    assert figure.get("id") == "image-1"
    assert figure.get("data-image-number") == "1"
    assert figure.xpath(".//img/@src") == ["/api/preview/assets/diagrams%2Fmain.png"]
    assert caption == "Рис. 1. Схема"
    assert "md2gost-flow-text" in figure.xpath(".//figcaption/@class")[0].split()
    assert "font-style: italic;" in style
    assert "text-align: left;" in style


def test_unavailable_block_image_stays_lazy_and_keeps_caption_numbering() -> None:
    root = _parse(
        render_preview_html(
            build_preview_model("![Схема](missing.png)\n", _config(), UnavailableStorage())
        )
    )

    figure = root.xpath("//figure[contains(@class, 'md2gost-image-block')]")[0]
    image = figure.xpath(".//img")[0]

    assert figure.get("data-image-number") == "1"
    assert figure.xpath("string(.//figcaption)") == "Рисунок 1 — Схема"
    assert image.get("src") == "/api/preview/assets/missing.png"
    assert image.get("alt") == "Схема"
    assert image.get("loading") == "lazy"
    assert image.get("decoding") == "async"
    assert figure.xpath(".//span[contains(@class, 'md2gost-image-placeholder')]") == []


def test_unavailable_block_image_uses_bounded_default_aspect_ratio() -> None:
    root = _parse(
        render_preview_html(
            build_preview_model("![Схема](missing.png)\n", _config(), UnavailableStorage())
        )
    )

    image = root.xpath("//figure//img")[0]
    style = image.get("style") or ""

    assert "md2gost-image-standalone" in image.get("class", "").split()
    assert "width: 100%;" in style
    assert "max-width: 100%;" in style
    assert "height: auto;" in style
    assert "aspect-ratio: 16 / 9;" in style


def test_unavailable_block_image_honors_explicit_dimensions() -> None:
    root = _parse(
        render_preview_html(
            build_preview_model(
                "![Схема](missing.png){width=320px height=180px}\n",
                _config(),
                UnavailableStorage(),
            )
        )
    )

    image = root.xpath("//figure//img")[0]
    style = image.get("style") or ""

    assert "width: 320px;" in style
    assert "height: 180px;" in style
    assert "aspect-ratio: 320 / 180;" in style
    assert "width: 100%;" not in style


def test_unavailable_inline_image_stays_lazy_for_asset_route_fallback() -> None:
    root = _parse(
        render_preview_html(
            build_preview_model(
                "До ![Схема](missing.png) после.\n",
                _config(),
                UnavailableStorage(),
            )
        )
    )

    image = root.xpath("//img")[0]

    assert image.get("src") == "/api/preview/assets/missing.png"
    assert image.get("alt") == "Схема"
    assert image.get("loading") == "lazy"
    assert image.get("decoding") == "async"
    stylesheet = root.xpath("string(/html/head/style)")
    assert ".md2gost-image-placeholder" not in stylesheet
    assert root.xpath("//span[contains(@class, 'md2gost-image-placeholder')]") == []
    assert root.xpath("//object") == []


def test_simple_tables_render_as_real_html_tables() -> None:
    model = build_preview_model(
        "| Left | Center | Right |\n|:--|:-:|--:|\n| 1 | `two` | 3 |\n\n: Список\n",
        _config(),
    )

    root = _parse(render_preview_html(model))
    table = root.xpath("//table[contains(@class, 'md2gost-table')]")[0]
    style = root.xpath("string(/html/head/style)")

    assert root.xpath("//div[contains(@class, 'md2gost-unsupported')]") == []
    assert table.get("data-table-number") == "1"
    assert table.get("data-table-layout") == "autofit"
    assert table.get("data-continuation") == "false"
    caption = table.xpath(".//caption")[0]
    assert caption.xpath("string(.)") == "Таблица 1 — Список"
    assert "md2gost-flow-text" in caption.get("class", "").split()
    assert len(table.xpath(".//colgroup/col")) == 3
    assert table.xpath(".//thead/tr/th/text()") == ["Left", "Center", "Right"]
    assert table.xpath(".//tbody/tr/td[1]/text()") == ["1"]
    assert table.xpath(".//tbody/tr/td[2]/code/text()") == ["two"]
    assert table.xpath(".//thead/tr/th[2]/@data-align") == ["center"]
    assert table.xpath(".//thead/tr/th[3]/@data-align") == ["right"]
    assert ".md2gost-table" in style
    assert "border-collapse: collapse;" in style
    assert "margin-left: -5.4pt;" in style
    assert "width: 100%;" in style
    assert "padding: 2.75pt 5.4pt;" in style


def test_table_header_weight_follows_config() -> None:
    cfg = _config("overrides:\n  table:\n    header_bold: false\n")
    model = build_preview_model("| A | B |\n|---|---|\n| 1 | 2 |\n", cfg)

    root = _parse(render_preview_html(model))
    style = root.xpath("string(/html/head/style)")

    assert "--md2gost-table-header-font-weight: 400;" in style
    assert "font-weight: var(--md2gost-table-header-font-weight);" in style


def test_plain_listings_render_as_pre_code_blocks() -> None:
    cfg = _config(
        "overrides:\n  listing:\n    font:\n      family: Courier New\n      size: 10pt\n"
    )
    model = build_preview_model("```python\nprint(1)\n```\n\n: Пример\n", cfg)

    root = _parse(render_preview_html(model))
    figure = root.xpath("//figure[contains(@class, 'md2gost-listing-block')]")[0]
    style = root.xpath("string(/html/head/style)")

    assert figure.get("data-listing-number") == "1"
    assert figure.get("data-continuation") == "false"
    assert figure.xpath("string(.//figcaption)") == "Листинг 1 — Пример"
    assert figure.xpath(".//pre/code/@data-language") == ["python"]
    assert figure.xpath("string(.//pre/code)") == "print(1)\n"
    assert "font-family: Courier New;" in style
    assert "font-size: 10pt;" in style
    assert "white-space: pre;" in style
    assert "margin-left: -4pt;" in style
    assert "padding: 2pt 4pt;" in style
    caption_classes = figure.xpath(".//figcaption/@class")[0].split()
    listing_classes = figure.xpath(".//pre/@class")[0].split()
    caption_style = next(
        class_name
        for class_name in caption_classes
        if class_name.startswith("md2gost-block-style-")
    )
    listing_style = next(
        class_name
        for class_name in listing_classes
        if class_name.startswith("md2gost-block-style-")
    )
    assert caption_style != listing_style
    assert "md2gost-caption" in caption_classes
    assert "md2gost-flow-text" in caption_classes
    assert "font-family: Times New Roman;" in style


def test_highlighted_listings_render_token_spans() -> None:
    cfg = _config("overrides:\n  listing:\n    syntax_highlighting: true\n")
    model = build_preview_model(
        "```python\ndef f():\n    return 1\n```\n\n: Пример\n",
        cfg,
    )

    root = _parse(render_preview_html(model))
    code = root.xpath("//figure[contains(@class, 'md2gost-listing-block')]//code")[0]
    pre = code.getparent()

    assert code.xpath(".//span[contains(@class, 'md2gost-listing-token')]")
    assert "md2gost-listing-highlighted" in pre.get("class", "").split()
    assert "def" in code.xpath("string(.)")
    assert any(
        "color:" in value
        for value in code.xpath(".//span[contains(@class, 'md2gost-listing-token')]/@style")
    )
    style = root.xpath("string(/html/head/style)")
    assert "line-height: 1.2292;" in style
    assert ".md2gost-listing-highlighted code::after" in style
