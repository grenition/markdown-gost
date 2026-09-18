"""Юнит-тесты шаблона ``titlepage-university`` (T023)."""""

from __future__ import annotations

import struct
import zlib

import pytest
from docx.shared import Length

from markdown_gost.config.loader import load_config_from_string
from markdown_gost.render.document_factory import build_document
from markdown_gost.render.layout_tracker import LayoutTracker
from markdown_gost.renderable.base import RenderedInfo
from markdown_gost.templates import TemplateContext, render_template
from markdown_gost.templates.titlepage_university.render import Titlepage


@pytest.fixture
def config():
    return load_config_from_string("preset: gost-7-32-2017\n")


@pytest.fixture
def document(config):
    return build_document(config)


@pytest.fixture
def ctx(document, config):
    return TemplateContext(document=document, config=config)


def _render_to_paragraphs(rendered, max_height=10_000_000, max_width=6_000_000):
    tracker = LayoutTracker(Length(max_height), Length(max_width))
    return [
        info for info in rendered.render(None, tracker.current_state)
        if isinstance(info, RenderedInfo)
    ]


def test_titlepage_renders_with_only_defaults(ctx):
    """Все поля имеют дефолты — шаблон должен отрендериться без params."""

    rendered = render_template("titlepage-university", {}, ctx)
    assert isinstance(rendered, Titlepage)
    infos = _render_to_paragraphs(rendered)
    xml = "".join(info.docx_element._p.xml for info in infos)
    assert "МИНОБРНАУКИ РОССИИ" in xml
    assert "Федеральное государственное бюджетное образовательное" in xml


def test_titlepage_renders_university_params(ctx):
    """Вуз задается параметрами и без них не печатается."""

    rendered = render_template(
        "titlepage-university",
        {
            "university_full": "«Государственный тестовый университет»",
            "university_short": "ГТУ-ТЕСТ",
        },
        ctx,
    )
    infos = _render_to_paragraphs(rendered)
    xml = "".join(info.docx_element._p.xml for info in infos)
    assert "«Государственный тестовый университет»" in xml
    assert "ГТУ-ТЕСТ" in xml


def test_titlepage_renders_full_payload(ctx):
    rendered = render_template(
        "titlepage-university",
        {
            "title": "Отчёт по практике",
            "subject": "Моделирование сред",
            "topic": "Информационная система учёта заявок",
            "institute": "Институт ИТ",
            "department": "Кафедра ИПС",
            "authors": [
                {
                    "label": "Студент группы ИКБО-20-23",
                    "names": ["Михеев А.Е."],
                }
            ],
            "reviewers": [
                {
                    "label": "Старший преподаватель",
                    "names": ["Горбатов Г.В.", "Иванов И.И."],
                }
            ],
            "city": "МОСКВА",
            "year": "2026 г.",
        },
        ctx,
    )
    assert isinstance(rendered, Titlepage)
    infos = _render_to_paragraphs(rendered)
    xml = "".join(info.docx_element._p.xml for info in infos)
    assert "Отчёт по практике" in xml
    assert "по дисциплине «Моделирование сред»" in xml
    assert "на тему" in xml
    assert "«Информационная система учёта заявок»" in xml
    assert "Институт ИТ" in xml
    assert "Кафедра ИПС" in xml
    assert "Михеев А.Е." in xml
    assert "Горбатов Г.В." in xml
    assert "Иванов И.И." in xml
    # Подписи целиком берутся из полей групп, без авто-достройки.
    assert "Студент группы ИКБО-20-23" in xml
    assert "Старший преподаватель" in xml
    # Footer прижат framePr.
    assert "МОСКВА 2026 г." in xml
    assert "framePr" in xml


def test_titlepage_group_label_is_user_text(ctx):
    """``label`` в группе рендерится буквально, без авто-склонения по числу имён."""

    rendered = render_template(
        "titlepage-university",
        {
            "authors": [
                {
                    "label": "Студенты группы ИКБО-20-23",
                    "names": ["Иванов И.И.", "Петров П.П."],
                }
            ],
        },
        ctx,
    )
    assert isinstance(rendered, Titlepage)
    infos = _render_to_paragraphs(rendered)
    xml = "".join(info.docx_element._p.xml for info in infos)
    assert "Студенты группы ИКБО-20-23" in xml
    assert "Иванов И.И." in xml
    assert "Петров П.П." in xml


def test_titlepage_no_auto_group_label(ctx):
    """Шаблон не подставляет «Студент группы …» от себя — только то, что в ``label``."""

    rendered = render_template(
        "titlepage-university",
        {"authors": [{"label": "", "names": ["Иванов И.И."]}]},
        ctx,
    )
    assert isinstance(rendered, Titlepage)
    infos = _render_to_paragraphs(rendered)
    xml = "".join(info.docx_element._p.xml for info in infos)
    assert "Иванов И.И." in xml
    assert "Студент" not in xml
    assert "группы" not in xml


def test_titlepage_rejects_legacy_group_field(ctx):
    """Поле ``group`` удалено — strict-схема должна выкинуть его как unknown."""

    rendered = render_template(
        "titlepage-university", {"group": "ИКБО-20-23"}, ctx
    )
    assert not isinstance(rendered, Titlepage)


def test_titlepage_rejects_legacy_footer_field(ctx):
    """``footer`` разделён на ``city``/``year`` — старое поле запрещено."""

    rendered = render_template(
        "titlepage-university", {"footer": "МОСКВА 2026 г."}, ctx
    )
    assert not isinstance(rendered, Titlepage)


def test_titlepage_city_and_year_combined_in_footer(ctx):
    """``city`` и ``year`` рендерятся одной строкой через пробел внизу страницы."""

    rendered = render_template(
        "titlepage-university",
        {"city": "САНКТ-ПЕТЕРБУРГ", "year": "2027"},
        ctx,
    )
    assert isinstance(rendered, Titlepage)
    infos = _render_to_paragraphs(rendered)
    xml = "".join(info.docx_element._p.xml for info in infos)
    assert "САНКТ-ПЕТЕРБУРГ 2027" in xml
    assert "framePr" in xml


def test_titlepage_only_city(ctx):
    """Только ``city`` без года — рендерится без лишнего пробела."""

    rendered = render_template("titlepage-university", {"city": "МОСКВА"}, ctx)
    assert isinstance(rendered, Titlepage)
    infos = _render_to_paragraphs(rendered)
    xml = "".join(info.docx_element._p.xml for info in infos)
    assert "МОСКВА" in xml
    assert "framePr" in xml


def test_titlepage_rejects_legacy_label_fields(ctx):
    """``authors_label``/``reviewer_label`` теперь живут внутри групп."""

    rendered = render_template(
        "titlepage-university",
        {"authors_label": "Студент группы ИКБО-20-23"},
        ctx,
    )
    assert not isinstance(rendered, Titlepage)


def test_titlepage_multiple_author_groups(ctx):
    """Несколько групп авторов — каждая со своей подписью."""

    rendered = render_template(
        "titlepage-university",
        {
            "authors": [
                {
                    "label": "Студент группы ИКБО-20-23",
                    "names": ["Иванов И.И.", "Петров П.П."],
                },
                {
                    "label": "Студент группы ИКБО-23-23",
                    "names": ["Сидоров С.С."],
                },
            ],
        },
        ctx,
    )
    assert isinstance(rendered, Titlepage)
    infos = _render_to_paragraphs(rendered)
    xml = "".join(info.docx_element._p.xml for info in infos)
    # Обе подписи присутствуют.
    assert "Студент группы ИКБО-20-23" in xml
    assert "Студент группы ИКБО-23-23" in xml
    # Имена идут в порядке: первая группа, потом вторая.
    pos1 = xml.find("Иванов И.И.")
    pos2 = xml.find("Петров П.П.")
    pos3 = xml.find("Сидоров С.С.")
    assert -1 < pos1 < pos2 < pos3


def test_titlepage_multiple_reviewer_groups(ctx):
    """Несколько групп проверяющих — например, разные должности."""

    rendered = render_template(
        "titlepage-university",
        {
            "reviewers": [
                {
                    "label": "Старший преподаватель",
                    "names": ["Горбатов Г.В."],
                },
                {
                    "label": "Доцент кафедры ИПС",
                    "names": ["Иванов И.И.", "Петров П.П."],
                },
            ],
        },
        ctx,
    )
    assert isinstance(rendered, Titlepage)
    infos = _render_to_paragraphs(rendered)
    xml = "".join(info.docx_element._p.xml for info in infos)
    assert "Старший преподаватель" in xml
    assert "Доцент кафедры ИПС" in xml
    pos1 = xml.find("Горбатов Г.В.")
    pos2 = xml.find("Иванов И.И.")
    pos3 = xml.find("Петров П.П.")
    assert -1 < pos1 < pos2 < pos3


def test_titlepage_footer_omitted_when_empty(ctx):
    """Пустые ``city``/``year`` — параграф с framePr вообще не рендерится."""

    rendered = render_template("titlepage-university", {}, ctx)
    assert isinstance(rendered, Titlepage)
    infos = _render_to_paragraphs(rendered)
    xml = "".join(info.docx_element._p.xml for info in infos)
    assert "framePr" not in xml


def test_titlepage_rejects_unknown_field(ctx):
    rendered = render_template(
        "titlepage-university", {"title": "T", "extra": "boom"}, ctx
    )
    assert not isinstance(rendered, Titlepage)


def test_titlepage_last_yield_fills_page_height(ctx):
    """Последний RenderedInfo должен иметь высоту = max_height страницы."""

    rendered = render_template(
        "titlepage-university",
        {"title": "T", "city": "МОСКВА", "year": "2026"},
        ctx,
    )
    assert isinstance(rendered, Titlepage)
    page_height = Length(10_000_000)
    tracker = LayoutTracker(page_height, Length(6_000_000))
    infos = [
        info for info in rendered.render(None, tracker.current_state)
        if isinstance(info, RenderedInfo)
    ]
    assert infos[-1].height == page_height
    # Все промежуточные элементы — height=0.
    assert all(info.height == 0 for info in infos[:-1])


def _png_bytes() -> bytes:
    """Minimal valid 1×1 PNG."""

    sig = b"\x89PNG\r\n\x1a\n"

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    raw = bytes([0, 127, 127, 127])
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def _rendered_xml(ctx, params) -> str:
    rendered = render_template("titlepage-university", params, ctx)
    infos = _render_to_paragraphs(rendered)
    return "".join(info.docx_element._p.xml for info in infos)


def test_titlepage_logo_from_local_file(ctx, tmp_path):
    logo = tmp_path / "emblem.png"
    logo.write_bytes(_png_bytes())

    xml = _rendered_xml(ctx, {"logo": str(logo)})

    assert "<w:drawing>" in xml


def test_titlepage_without_logo_renders_no_drawing(ctx):
    xml = _rendered_xml(ctx, {})

    assert "<w:drawing>" not in xml


def test_titlepage_broken_logo_reference_raises(ctx):
    with pytest.raises(ValueError, match="logo not found"):
        _rendered_xml(ctx, {"logo": "/no/such/emblem.png"})
