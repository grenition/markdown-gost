from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.json_schema import JsonSchemaValue

from markdown_gost.config.units import parse_length

Alignment = Literal["left", "right", "center", "justify"]
PageSize = Literal["A4", "A3", "Letter"]
Orientation = Literal["portrait", "landscape"]
NumberingMode = Literal["continuous", "per-section", "none"]
BibliographyOrder = Literal["citation", "input"]
BibliographyStyle = Literal["minimal-gost"]

# Шрифты, которые гарантированно есть в Word на всех платформах. Не словарь
# «всех мыслимых» — это бы дало бесконечный селект; список нацелен на учебные
# работы и ту палитру, что предустановлена в Microsoft Office.
FontFamily = Literal[
    "Times New Roman",
    "Arial",
    "Calibri",
    "Cambria",
    "Georgia",
    "Tahoma",
    "Verdana",
    "Helvetica",
    "Courier New",
]
MonoFontFamily = Literal[
    "Consolas",
    "Courier New",
    "Cascadia Code",
    "Cascadia Mono",
    "JetBrains Mono",
    "Menlo",
    "Monaco",
    "Roboto Mono",
]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# Группы для UI form-generator-а. Идут в корень JSON Schema как ``x-groups``,
# фронт сортирует по ``order`` и группирует поля по совпадению ``id`` с
# именем top-level свойства.
_CONFIG_GROUPS: list[dict[str, Any]] = [
    {"id": "general", "label": "Общее", "order": 0},
    {"id": "page", "label": "Страница", "order": 10},
    {"id": "font", "label": "Шрифт", "order": 20},
    {"id": "paragraph", "label": "Параграф", "order": 30},
    {"id": "headings", "label": "Заголовки", "order": 40},
    {"id": "captions", "label": "Подписи", "order": 50},
    {"id": "table", "label": "Таблицы", "order": 60},
    {"id": "listing", "label": "Листинги", "order": 70},
    {"id": "lists", "label": "Списки", "order": 80},
    {"id": "equation", "label": "Формулы", "order": 90},
    {"id": "bibliography", "label": "Источники", "order": 100},
]

# Лейблы для значений ``enum`` (Literal-типов). Пробрасываются в JSON
# Schema каждого поля как ``x-enum-labels`` через ``json_schema_extra`` —
# UI-клиенты используют их вместо сырых машинных идентификаторов
# (``portrait`` → «Книжная», ``A4`` → «A4 (210 × 297 мм)», и т. д.).
_ALIGNMENT_LABELS: dict[str, str] = {
    "left": "По левому краю",
    "right": "По правому краю",
    "center": "По центру",
    "justify": "По ширине",
}
_PAGESIZE_LABELS: dict[str, str] = {
    "A4": "A4 (210 × 297 мм)",
    "A3": "A3 (297 × 420 мм)",
    "Letter": "Letter",
}
_ORIENTATION_LABELS: dict[str, str] = {
    "portrait": "Книжная",
    "landscape": "Альбомная",
}
_NUMBERING_LABELS: dict[str, str] = {
    "continuous": "Сквозная",
    "per-section": "Посекционная (1.1, 1.2…)",
    "none": "Без нумерации",
}
_BIBLIOGRAPHY_ORDER_LABELS: dict[str, str] = {
    "citation": "По первому цитированию",
    "input": "Как во входном списке",
}
_BIBLIOGRAPHY_STYLE_LABELS: dict[str, str] = {
    "minimal-gost": "Минимальный ГОСТ",
}


def _enum_labels(labels: dict[str, str]) -> dict[str, Any]:
    """Helper to build the ``json_schema_extra`` payload for an enum field."""
    return {"x-enum-labels": labels}


def _ui(group: str, order: int, **extra: Any) -> dict[str, Any]:
    """Common JSON Schema metadata used by the UI form generator."""
    return {"x-group": group, "x-order": order, **extra}


def _default_structural_heading() -> "HeadingLevel":
    return HeadingLevel(
        size="14pt",
        bold=True,
        italic=False,
        uppercase=True,
        alignment="center",
        space_before="0pt",
        space_after="0pt",
        page_break_before=True,
        keep_with_next=True,
        indent_first_line="0cm",
    )


def _default_structural_titles() -> list[str]:
    return [
        "СОДЕРЖАНИЕ",
        "ВВЕДЕНИЕ",
        "ЗАКЛЮЧЕНИЕ",
        "СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ",
    ]


class PageMargins(_Strict):
    top: str = Field(
        "2cm",
        title="Верхнее поле",
        description="Верхний отступ от края листа до текста",
        json_schema_extra=_ui("page", 31),
    )
    bottom: str = Field(
        "2cm",
        title="Нижнее поле",
        description="Нижний отступ от края листа до текста",
        json_schema_extra=_ui("page", 32),
    )
    left: str = Field(
        "3cm",
        title="Левое поле",
        description="Левый отступ от края листа до текста",
        json_schema_extra=_ui("page", 33),
    )
    right: str = Field(
        "1.5cm",
        title="Правое поле",
        description="Правый отступ от края листа до текста",
        json_schema_extra=_ui("page", 34),
    )


class Page(_Strict):
    size: PageSize = Field(
        "A4",
        title="Размер листа",
        description="Формат бумаги",
        json_schema_extra=_ui("page", 10, **_enum_labels(_PAGESIZE_LABELS)),
    )
    orientation: Orientation = Field(
        "portrait",
        title="Ориентация",
        description="Книжная или альбомная",
        json_schema_extra=_ui("page", 20, **_enum_labels(_ORIENTATION_LABELS)),
    )
    margins: PageMargins = Field(
        default_factory=PageMargins,
        title="Поля",
        description="Отступы от краёв листа",
        json_schema_extra=_ui("page", 30),
    )


class Font(_Strict):
    family: FontFamily = Field(
        "Times New Roman",
        title="Семейство шрифта",
        description="Основной шрифт документа",
        json_schema_extra=_ui("font", 10),
    )
    size: str = Field(
        "14pt",
        title="Размер шрифта",
        description="Базовый размер шрифта",
        json_schema_extra=_ui("font", 20),
    )
    line_spacing: float = Field(
        1.5,
        title="Межстрочный интервал",
        description="Множитель межстрочного интервала (1.5 — полуторный)",
        json_schema_extra=_ui("font", 30),
    )


class InlineCode(_Strict):
    font: MonoFontFamily = Field(
        "Consolas",
        title="Шрифт",
        description="Моноширинный шрифт для inline-кода (`code`)",
        json_schema_extra=_ui("paragraph", 30),
    )
    size: str = Field(
        "14pt",
        title="Размер шрифта",
        description="Размер для inline-кода",
        json_schema_extra=_ui("paragraph", 31),
    )
    italic: bool = Field(
        False,
        title="Курсив",
        description="Курсивное начертание",
        json_schema_extra=_ui("paragraph", 32),
    )
    quotes: bool = Field(
        False,
        title="Кавычки",
        description="Оборачивать ли inline-код в «ёлочки»",
        json_schema_extra=_ui("paragraph", 33),
    )


class Paragraph(_Strict):
    alignment: Alignment = Field(
        "justify",
        title="Выравнивание",
        description="Выравнивание основного текста",
        json_schema_extra=_ui("paragraph", 10, **_enum_labels(_ALIGNMENT_LABELS)),
    )
    indent_first_line: str = Field(
        "1.25cm",
        title="Отступ первой строки",
        description="Красная строка обычного параграфа",
        json_schema_extra=_ui("paragraph", 20),
    )
    inline_code: InlineCode = Field(
        default_factory=InlineCode,
        title="Inline-код",
        description="Оформление inline-кода (`code`)",
        json_schema_extra=_ui("paragraph", 30),
    )


class HeadingLevel(_Strict):
    size: str | None = Field(
        None,
        title="Размер шрифта",
        description=(
            "Размер шрифта заголовка. Оставьте пустым, чтобы наследовать от базового шрифта."
        ),
        json_schema_extra=_ui("headings", 101, **{"x-inherit-from": "font.size"}),
    )
    bold: bool = Field(
        True,
        title="Жирный",
        description="Жирное начертание",
        json_schema_extra=_ui("headings", 102),
    )
    italic: bool = Field(
        False,
        title="Курсив",
        description="Курсивное начертание",
        json_schema_extra=_ui("headings", 103),
    )
    uppercase: bool = Field(
        False,
        title="Верхний регистр",
        description="Перевести текст заголовка в верхний регистр",
        json_schema_extra=_ui("headings", 104),
    )
    alignment: Alignment = Field(
        "left",
        title="Выравнивание",
        description="Выравнивание текста заголовка",
        json_schema_extra=_ui("headings", 105, **_enum_labels(_ALIGNMENT_LABELS)),
    )
    space_before: str = Field(
        "0pt",
        title="Отступ сверху",
        description="Вертикальный отступ перед заголовком",
        json_schema_extra=_ui("headings", 106),
    )
    space_after: str = Field(
        "0pt",
        title="Отступ снизу",
        description="Вертикальный отступ после заголовка",
        json_schema_extra=_ui("headings", 107),
    )
    page_break_before: bool = Field(
        False,
        title="С новой страницы",
        description="Начинать заголовок с новой страницы",
        json_schema_extra=_ui("headings", 108),
    )
    keep_with_next: bool = Field(
        True,
        title="Не отрывать от текста",
        description="Запрещать разрыв страницы между заголовком и следующим параграфом",
        json_schema_extra=_ui("headings", 109),
    )
    indent_first_line: str = Field(
        "1.25cm",
        title="Отступ первой строки",
        description="Красная строка заголовка",
        json_schema_extra=_ui("headings", 110),
    )


class Headings(_Strict):
    numbering: NumberingMode = Field(
        "continuous",
        title="Тип нумерации",
        description="Способ нумерации заголовков по документу",
        json_schema_extra=_ui("headings", 10, **_enum_labels(_NUMBERING_LABELS)),
    )
    leading_space_in_numbered: bool = Field(
        True,
        title="Пробел после номера",
        description="Вставлять пробел между номером и текстом заголовка",
        json_schema_extra=_ui("headings", 20),
    )
    levels: dict[int, HeadingLevel] = Field(
        default_factory=dict,
        title="Параметры уровней",
        description="Параметры конкретных уровней заголовков (1, 2, 3, …)",
        json_schema_extra=_ui("headings", 30),
    )
    structural: HeadingLevel = Field(
        default_factory=_default_structural_heading,
        title="Структурные заголовки",
        description="Оформление ненумерованных структурных элементов",
        json_schema_extra=_ui("headings", 45),
    )
    structural_titles: list[str] = Field(
        default_factory=_default_structural_titles,
        title="Названия структурных заголовков",
        description="H1 без номера с этими названиями рендерятся как структурные",
        json_schema_extra=_ui("headings", 46),
    )


class CaptionStyle(_Strict):
    italic: bool = Field(
        False,
        title="Курсив",
        description="Курсивное начертание подписи",
        json_schema_extra=_ui("captions", 101),
    )
    bold: bool = Field(
        False,
        title="Жирный",
        description="Жирное начертание подписи",
        json_schema_extra=_ui("captions", 102),
    )
    alignment: Alignment = Field(
        "left",
        title="Выравнивание",
        description="Выравнивание текста подписи",
        json_schema_extra=_ui("captions", 103, **_enum_labels(_ALIGNMENT_LABELS)),
    )
    format: str = Field(
        "{category} {number} — {text}",
        title="Шаблон подписи",
        description="Плейсхолдеры: {category}, {number}, {text}",
        json_schema_extra=_ui("captions", 104),
    )
    space_before: str = Field(
        "0pt",
        title="Отступ сверху",
        description="Вертикальный отступ перед параграфом подписи",
        json_schema_extra=_ui("captions", 105),
    )
    space_after: str = Field(
        "0pt",
        title="Отступ снизу",
        description="Вертикальный отступ после параграфа подписи",
        json_schema_extra=_ui("captions", 106),
    )
    line_spacing: float | None = Field(
        None,
        gt=0,
        title="Межстрочный интервал",
        description=(
            "Множитель межстрочного интервала внутри подписи. Оставьте пустым, "
            "чтобы наследовать базовый интервал документа."
        ),
        json_schema_extra=_ui("captions", 107, **{"x-inherit-from": "font.line_spacing"}),
    )


class Captions(_Strict):
    image: CaptionStyle = Field(
        default_factory=lambda: CaptionStyle(alignment="center"),
        title="Подписи рисунков",
        description="Оформление подписей под рисунками",
        json_schema_extra=_ui("captions", 10),
    )
    table: CaptionStyle = Field(
        default_factory=CaptionStyle,
        title="Подписи таблиц",
        description="Оформление подписей перед таблицами",
        json_schema_extra=_ui("captions", 20),
    )
    listing: CaptionStyle = Field(
        default_factory=CaptionStyle,
        title="Подписи листингов",
        description="Оформление подписей перед листингами",
        json_schema_extra=_ui("captions", 30),
    )
    continuation_break: bool = Field(
        False,
        title="Подпись «Продолжение» при разрыве",
        description=("Добавлять на стыке страниц подпись «Продолжение таблицы/листинга N»."),
        json_schema_extra=_ui("captions", 40),
    )


class Table(_Strict):
    repeat_header_on_break: bool = Field(
        True,
        title="Повторять шапку",
        description="Повторять шапку таблицы при автоматическом разрезе на страницы",
        json_schema_extra=_ui("table", 10),
    )
    header_bold: bool = Field(
        True,
        title="Жирная шапка",
        description="Жирное начертание ячеек строки-шапки",
        json_schema_extra=_ui("table", 20),
    )
    font_size: str | None = Field(
        None,
        title="Размер шрифта",
        description=(
            "Размер шрифта в ячейках таблицы. Оставьте пустым, чтобы наследовать "
            "от базового шрифта."
        ),
        json_schema_extra=_ui("table", 30, **{"x-inherit-from": "font.size"}),
    )
    space_before: str = Field(
        "0pt",
        title="Отступ сверху",
        description="Вертикальный отступ перед таблицей (накладывается на параграф подписи)",
        json_schema_extra=_ui("table", 40),
    )
    space_after: str = Field(
        "0pt",
        title="Отступ снизу",
        description="Вертикальный отступ после таблицы",
        json_schema_extra=_ui("table", 50),
    )


class ListingFont(_Strict):
    family: MonoFontFamily = Field(
        "Consolas",
        title="Семейство шрифта",
        description="Моноширинный шрифт строк листинга",
        json_schema_extra=_ui("listing", 21),
    )
    size: str = Field(
        "12pt",
        title="Размер шрифта",
        description="Размер строк листинга",
        json_schema_extra=_ui("listing", 22),
    )


class Listing(_Strict):
    syntax_highlighting: bool = Field(
        False,
        title="Подсветка синтаксиса",
        description="Раскрашивать ли токены через pygments",
        json_schema_extra=_ui("listing", 10),
    )
    font: ListingFont = Field(
        default_factory=ListingFont,
        title="Шрифт",
        description="Шрифт строк листинга",
        json_schema_extra=_ui("listing", 20),
    )
    line_spacing: float = Field(
        1.0,
        title="Межстрочный интервал",
        description="Множитель межстрочного внутри листинга (1.0 — одинарный)",
        json_schema_extra=_ui("listing", 30),
    )
    space_before: str = Field(
        "0pt",
        title="Отступ сверху",
        description="Вертикальный отступ перед листингом",
        json_schema_extra=_ui("listing", 40),
    )
    space_after: str = Field(
        "0pt",
        title="Отступ снизу",
        description="Вертикальный отступ после листинга",
        json_schema_extra=_ui("listing", 50),
    )


class Lists(_Strict):
    bullet_marker: str = Field(
        "—",
        title="Маркер bullet",
        description="Символ для маркированных списков",
        json_schema_extra=_ui("lists", 10),
    )
    numbered_format: str = Field(
        "{n}.",
        title="Формат номера",
        description="Шаблон номера для arabic-списков (плейсхолдер {n})",
        json_schema_extra=_ui("lists", 20),
    )
    alphabetic_format: str = Field(
        "{a})",
        title="Формат буквы",
        description="Шаблон маркера для alpha-списков (плейсхолдер {a})",
        json_schema_extra=_ui("lists", 30),
    )
    indent_left: str = Field(
        "1.25cm",
        title="Левый отступ",
        description="Отступ списка от левого края",
        json_schema_extra=_ui("lists", 40),
    )
    indent_first_line: str = Field(
        "0cm",
        title="Отступ первой строки",
        description="Красная строка для пунктов списка",
        json_schema_extra=_ui("lists", 50),
    )
    indent_per_level: str = Field(
        "0.75cm",
        title="Отступ на уровень",
        description="Дополнительный отступ для каждого вложенного уровня",
        json_schema_extra=_ui("lists", 60),
    )


class Equation(_Strict):
    space_before: str = Field(
        "0pt",
        title="Отступ сверху",
        description=(
            "Вертикальный отступ перед формулой. В DOCX рендерится верхней "
            "строкой-отступом внутри невидимой таблицы формулы."
        ),
        json_schema_extra=_ui("equation", 10),
    )
    space_after: str = Field(
        "0pt",
        title="Отступ снизу",
        description=(
            "Вертикальный отступ после формулы. В DOCX рендерится нижней "
            "строкой-отступом внутри невидимой таблицы формулы."
        ),
        json_schema_extra=_ui("equation", 20),
    )
    numbering_alignment: Alignment = Field(
        "right",
        title="Выравнивание номера",
        description="Сторона, к которой прижимается номер формулы",
        json_schema_extra=_ui("equation", 30, **_enum_labels(_ALIGNMENT_LABELS)),
    )
    parentheses: bool = Field(
        True,
        title="Номер в скобках",
        description="Оборачивать ли номер формулы в круглые скобки",
        json_schema_extra=_ui("equation", 40),
    )

    @field_validator("space_before", "space_after")
    @classmethod
    def _validate_spacing(cls, value: str) -> str:
        length = parse_length(value)
        if int(length) < 0:
            raise ValueError("spacing length must be non-negative")
        return value


class Bibliography(_Strict):
    citation_format: str = Field(
        "[{n}]",
        title="Формат ссылки",
        description="Шаблон inline-ссылки на источник; плейсхолдер {n} — номер источника",
        json_schema_extra=_ui("bibliography", 10),
    )
    order: BibliographyOrder = Field(
        "citation",
        title="Порядок источников",
        description="Порядок вывода списка источников",
        json_schema_extra={
            **_ui("bibliography", 20),
            **_enum_labels(_BIBLIOGRAPHY_ORDER_LABELS),
        },
    )
    style: BibliographyStyle = Field(
        "minimal-gost",
        title="Стиль описания",
        description="Стиль форматирования библиографического описания",
        json_schema_extra={
            **_ui("bibliography", 30),
            **_enum_labels(_BIBLIOGRAPHY_STYLE_LABELS),
        },
    )
    entry_number_format: str = Field(
        "{n}.",
        title="Формат номера",
        description="Шаблон номера в списке источников; плейсхолдер {n} — номер источника",
        json_schema_extra=_ui("bibliography", 40),
    )


class Config(_Strict):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra=cast("JsonSchemaValue", {"x-groups": _CONFIG_GROUPS}),
    )

    preset: str = Field(
        ...,
        title="Пресет",
        description="Имя базового пресета (default, gost-r-7.32, …)",
        json_schema_extra=_ui("general", 10),
    )
    page: Page = Field(
        default_factory=Page,
        title="Страница",
        description="Размер, ориентация и поля",
        json_schema_extra=_ui("page", 10),
    )
    font: Font = Field(
        default_factory=Font,
        title="Шрифт",
        description="Базовый шрифт документа",
        json_schema_extra=_ui("font", 20),
    )
    paragraph: Paragraph = Field(
        default_factory=Paragraph,
        title="Параграф",
        description="Оформление обычного параграфа",
        json_schema_extra=_ui("paragraph", 30),
    )
    headings: Headings = Field(
        default_factory=Headings,
        title="Заголовки",
        description="Нумерация и параметры заголовков по уровням",
        json_schema_extra=_ui("headings", 40),
    )
    captions: Captions = Field(
        default_factory=Captions,
        title="Подписи",
        description="Оформление подписей рисунков, таблиц, листингов",
        json_schema_extra=_ui("captions", 50),
    )
    table: Table = Field(
        default_factory=Table,
        title="Таблицы",
        description="Параметры рендера таблиц",
        json_schema_extra=_ui("table", 60),
    )
    listing: Listing = Field(
        default_factory=Listing,
        title="Листинги",
        description="Параметры рендера листингов",
        json_schema_extra=_ui("listing", 70),
    )
    lists: Lists = Field(
        default_factory=Lists,
        title="Списки",
        description="Маркеры и отступы списков",
        json_schema_extra=_ui("lists", 80),
    )
    equation: Equation = Field(
        default_factory=Equation,
        title="Формулы",
        description="Оформление формул и их нумерации",
        json_schema_extra=_ui("equation", 90),
    )
    bibliography: Bibliography = Field(
        default_factory=Bibliography,
        title="Источники",
        description="Оформление библиографических ссылок и списка источников",
        json_schema_extra=_ui("bibliography", 100),
    )
