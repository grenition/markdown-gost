"""Сбор кросс-ссылочных данных за первый проход рендера (T016).

Заполняется ``Renderer``ом по мере рендера: для каждого заголовка и каждого
нумерованного объекта (картинка, таблица, листинг, формула) сохраняется
запись с актуальной страницей и стабильным якорем. На втором проходе
``Renderable.post_process(index, doc)`` пользователи (в первую очередь
шаблон ``content`` из T023) могут опираться на эти данные для финального
рендера.

Якорь — детерминированный идентификатор вида ``_md_<8hex>``, посчитанный
из ``(kind, ordinal, raw_text)``. Один и тот же набор входов в разных
прогонах даёт один и тот же якорь — это нужно, чтобы DOCX-закладки и
HTML-anchor'ы не «дребезжали» между сборками.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


@dataclass(frozen=True)
class HeadingEntry:
    """Заголовок документа — позиция в TOC.

    ``number`` — строка вида ``"1.2.3"`` (или ``None`` для ненумерованных
    заголовков с ``.unnumbered``). ``page`` — номер страницы (1-based).
    """

    level: int
    text: str
    numbered: bool
    number: str | None
    anchor: str
    page: int


@dataclass(frozen=True)
class ObjectEntry:
    """Нумерованный объект (image / table / listing / equation).

    ``caption`` — текст подписи без префикса «Рисунок N — ». ``None``,
    если у объекта нет подписи (bare-листинг, формула без подписи).
    """

    number: int
    caption: str | None
    page: int
    anchor: str
    number_text: str | None = None


@dataclass
class RenderIndex:
    """Контейнер для кросс-ссылочных данных, накопленных за первый проход.

    ``headings`` — все заголовки в порядке появления в документе.
    ``numbered_objects`` — словарь ``category -> list[ObjectEntry]``;
    категории совпадают со значением ``Renderable.numbering_category``
    (``image``/``table``/``listing``/``equation``).
    ``total_pages`` — фактическое число страниц после первого прохода
    (выставляет ``Renderer.process`` в самом конце).
    """

    headings: list[HeadingEntry] = field(default_factory=list)
    numbered_objects: dict[str, list[ObjectEntry]] = field(default_factory=dict)
    total_pages: int = 0

    def add_heading(
        self,
        *,
        level: int,
        text: str,
        numbered: bool,
        number: str | None,
        page: int,
    ) -> HeadingEntry:
        anchor = _make_anchor("h", len(self.headings), text, number)
        entry = HeadingEntry(
            level=level,
            text=text,
            numbered=numbered,
            number=number,
            anchor=anchor,
            page=page,
        )
        self.headings.append(entry)
        return entry

    def add_object(
        self,
        *,
        category: str,
        number: int,
        number_text: str | None = None,
        caption: str | None,
        page: int,
    ) -> ObjectEntry:
        ordinal = len(self.numbered_objects.get(category, []))
        anchor = _make_anchor(category, ordinal, caption or "", number_text or str(number))
        entry = ObjectEntry(
            number=number,
            caption=caption,
            page=page,
            anchor=anchor,
            number_text=number_text,
        )
        self.numbered_objects.setdefault(category, []).append(entry)
        return entry

    def set_total_pages(self, total: int) -> None:
        self.total_pages = total


def _make_anchor(*parts: str | int | None) -> str:
    """Стабильный якорь длиной 12 символов: ``_md_`` + 8 hex от sha1(parts).

    Кодируем элементы UTF-8 и разделяем NUL — гарантирует разные хэши
    для разных композиций (в Python collisions от sha1 на коротких хвостах
    практически нулевые, но конкатенация без разделителя теоретически
    могла бы вернуть одинаковую строку из разных входов).
    """

    raw = "\x00".join(str(p) for p in parts).encode("utf-8")
    digest = hashlib.sha1(raw).hexdigest()[:8]
    return f"_md_{digest}"
