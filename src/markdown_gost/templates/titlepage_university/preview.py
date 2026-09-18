"""Native HTML-preview representation of a semantic title page."""

from __future__ import annotations

from typing import Any

from markdown_gost.templates import PreviewTemplateContext


def render_preview(params: dict[str, Any], context: PreviewTemplateContext) -> None:
    """Emit one semantic title-page block and reserve its preview page.

    The layout payload deliberately contains text only: the bundled DOCX logo
    is not copied into HTML because preview assets must come from storage/API
    references rather than arbitrary package-local paths.
    """

    context.add_block(
        "title_page",
        "",
        style={"page_break_before": True},
        layout=_title_page_layout(params),
    )
    context.add_page_break()


def _title_page_layout(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "header": _header_items(params),
        "organization": _text_items(params, "institute", "department"),
        "work": _work_items(params),
        "signature_sections": _signature_sections(params),
        "footer": " ".join(
            value
            for value in (_value(params, "city"), _value(params, "year"))
            if value
        ),
        "logo_url": _value(params, "logo") or None,
        "logo_omitted": not _value(params, "logo"),
    }


def _header_items(params: dict[str, Any]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = [
        {"role": "ministry", "text": "МИНОБРНАУКИ РОССИИ"},
        {
            "role": "institution-full-name",
            "text": (
                "Федеральное государственное бюджетное образовательное учреждение\n"
                "высшего образования"
            ),
        },
    ]
    if full := _value(params, "university_full"):
        items.append({"role": "university-name", "text": full})
    if short := _value(params, "university_short"):
        items.append({"role": "university-short-name", "text": short})
    return items


def _text_items(params: dict[str, Any], *keys: str) -> list[dict[str, str]]:
    return [{"text": value} for key in keys if (value := _value(params, key))]


def _work_items(params: dict[str, Any]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    if title := _value(params, "title"):
        items.append({"role": "work-title", "text": title})
    if subject := _value(params, "subject"):
        items.append({"role": "work-subject", "text": f"по дисциплине «{subject}»"})
    if topic := _value(params, "topic"):
        items.extend(
            [
                {"role": "work-topic-label", "text": "на тему"},
                {"role": "work-topic", "text": f"«{topic}»"},
            ]
        )
    return items


def _signature_sections(params: dict[str, Any]) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    for title_key, groups_key in (
        ("authors_title", "authors"),
        ("reviewer_title", "reviewers"),
    ):
        rows = _signature_rows(params.get(groups_key))
        if rows:
            sections.append({"title": _value(params, title_key), "rows": rows})
    return sections


def _signature_rows(groups: Any) -> list[dict[str, str | bool]]:
    rows: list[dict[str, str | bool]] = []
    for group_index, group in enumerate(groups or []):
        if not isinstance(group, dict):
            continue
        label = str(group.get("label") or "").strip()
        names = group.get("names") or []
        for index, name in enumerate(names):
            text = str(name).strip()
            if text:
                row: dict[str, str | bool] = {"label": label if index == 0 else "", "name": text}
                if index == 0 and group_index > 0:
                    row["group_start"] = True
                rows.append(row)
    return rows


def _value(params: dict[str, Any], key: str) -> str:
    return str(params.get(key) or "").strip()
