"""Integration test for the full postprocessor pipeline (T033)."""

from __future__ import annotations

import textwrap

from markdown_gost.import_.postprocessor import postprocess


def test_all_transformers_compose_on_synthetic_raw_md() -> None:
    raw = textwrap.dedent(
        """\
        # 1 Введение

        Текст с [подчёркнутым]{.underline} словом и [мелким]{.smallcaps} капсом.

        ## 1.1 Метод

        Таблица 1 — Сравнение

        | A | B |
        |---|---|
        | 1 | 2 |

        Рисунок 1 — Схема

        ![](media/image1.png)

        # СОДЕРЖАНИЕ

        Листинг 1 — Echo

        ```python
        print("hi")
        ```
        """
    )

    out, fallbacks = postprocess(raw)

    assert fallbacks == {}
    # heading_normalizer strips "1", then unnumbered_heading_detector marks it
    # because "введение" is a known service heading.
    assert "# Введение {.unnumbered}" in out
    assert "## Метод" in out
    assert "# СОДЕРЖАНИЕ {.unnumbered}" in out
    assert ": Сравнение" in out
    assert ": Echo" in out
    assert "![Схема](media/image1.png)" in out
    assert "[подчёркнутым]{.underline}" in out
    assert "мелким капсом" in out  # smallcaps stripped
    # Raw pandoc-style caption markers must be gone.
    assert "Таблица 1 —" not in out
    assert "Рисунок 1 —" not in out
    assert "Листинг 1 —" not in out


def test_html_table_is_converted_then_caption_is_folded() -> None:
    raw = textwrap.dedent(
        """\
        Таблица 1 — Слитная

        <table>
        <tbody>
        <tr><td>A</td><td>B</td></tr>
        <tr><td colspan="2">merged</td></tr>
        </tbody>
        </table>
        """
    )
    out, fallbacks = postprocess(raw)
    assert fallbacks == {}
    # html_table_converter runs first → pipe-table; caption_folder then
    # folds the "Таблица 1 — ..." paragraph into a trailing universal caption.
    assert ": Слитная" in out
    assert "| A | B |" in out
    assert "| merged |  |" in out
    assert "<table>" not in out


def test_pipeline_preserves_fenced_code_contents() -> None:
    raw = textwrap.dedent(
        """\
        ```python
        # 1 Not a heading
        x = "[span]{.underline}"
        ```
        """
    )
    out, fallbacks = postprocess(raw)
    assert fallbacks == {}
    assert "# 1 Not a heading" in out
    assert "[span]{.underline}" in out
    assert "++" not in out
