"""Нативная нумерация Word: часть numbering.xml + ``w:numPr`` на параграфах.

Модуль владеет numbering-частью документа (создаёт и подключает её к
document.xml при первом обращении) и выдаёт свежую пару
``w:abstractNum`` + ``w:num`` на каждый корень списка — счётчики
LibreOffice/Word живут на abstractNum, поэтому нумерация не продолжается
между соседними списками. ``start != 1`` корня пишется в ``w:start``
уровня; ``w:startOverride`` на ``w:num`` остаётся только для редкого случая
literal start у вложенного узла уже начатой цепочки.

Геометрия списка (левый отступ + висячий отступ маркера) задаётся в
``w:pPr/w:ind`` уровня нумерации — линейка и список-UI Word показывают её
корректно, прямого форматирования на параграфах не нужно.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from weakref import WeakKeyDictionary

from docx.document import Document as DocxDocument
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.opc.packuri import PackURI
from docx.opc.part import Part
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls, nsmap, qn
from docx.parts.document import DocumentPart
from docx.shared import Length
from lxml import etree

_NUMBERING_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"
)

# Дети w:pPr, идущие после w:numPr (ECMA-376 CT_PPr) — чтобы вставить numPr
# в схемно-корректную позицию.
_PPR_SUCCESORS = (
    "w:suppressLineNumbers",
    "w:pBdr",
    "w:shd",
    "w:tabs",
    "w:suppressAutoHyphens",
    "w:kinsoku",
    "w:wordWrap",
    "w:overflowPunct",
    "w:topLinePunct",
    "w:autoSpaceDE",
    "w:autoSpaceDN",
    "w:bidi",
    "w:adjustRightInd",
    "w:snapToGrid",
    "w:spacing",
    "w:ind",
    "w:contextualSpacing",
    "w:mirrorIndents",
    "w:suppressOverlap",
    "w:jc",
    "w:textDirection",
    "w:textAlignment",
    "w:textboxTightWrap",
    "w:outlineLvl",
    "w:divId",
    "w:cnfStyle",
    "w:rPr",
    "w:sectPr",
    "w:pPrChange",
)


@dataclass(frozen=True)
class LevelSpec:
    """Спецификация одного уровня нумерации (rel-уровень абстрактного списка)."""

    num_fmt: str  # "bullet" | "decimal"
    lvl_text: str  # «—», "%1.", "%2)" …
    left: int  # EMU (docx.shared.Length)
    hanging: int  # EMU


class _LiveNumberingPart(Part):
    """Part с живым XML-деревом: blob сериализуется в момент сохранения."""

    def __init__(self, partname: PackURI, content_type: str, root: Any) -> None:
        super().__init__(partname, content_type, blob=b"")
        self._numbering_root = root

    @property
    def blob(self) -> bytes:
        return bytes(
            etree.tostring(
                self._numbering_root,
                xml_declaration=True,
                encoding="UTF-8",
                standalone=True,
            )
        )


class Numbering:
    """Реестр нумерации одного документа."""

    def __init__(self, document: DocxDocument) -> None:
        self._document = document
        self._static_part: Part | None = None
        self._root = self._attach()
        # abstractNum НЕ кэшируем по сигнатуре: LibreOffice держит счётчики
        # на abstractNum, и общий abstractNum продолжал нумерацию между
        # соседними списками. Свежий abstractNum на каждый корень цепочки.
        self._next_abstract = self._max_id("w:abstractNum", "w:abstractNumId") + 1
        self._next_num = self._max_id("w:num", "w:numId") + 1

    # --подключение части--

    def _attach(self) -> Any:
        doc_part = self._document.part
        try:
            part: Part | None = doc_part.part_related_by(RT.NUMBERING)
        except KeyError:
            part = None

        if part is None:
            root: Any = parse_xml(f"<w:numbering {nsdecls('w')}/>")
            live = _LiveNumberingPart(PackURI("/word/numbering.xml"), _NUMBERING_CONTENT_TYPE, root)
            doc_part.relate_to(live, RT.NUMBERING)
            return root

        # Часть уже есть (шаблон документа): дописываемся в существующее дерево.
        root = getattr(part, "_element", None)  # XmlPart — динамический blob
        if root is None:
            root = parse_xml(part.blob)
            self._static_part = part  # статический Part — обновляем _blob руками
        return root

    def _sync(self) -> None:
        if self._static_part is not None:
            self._static_part._blob = etree.tostring(
                self._root,
                xml_declaration=True,
                encoding="UTF-8",
                standalone=True,
            )

    def _max_id(self, tag: str, attr: str) -> int:
        return max(
            (
                int(el.get(qn(attr)))
                for el in self._root.findall(qn(tag))
                if el.get(qn(attr)) is not None
            ),
            default=0,
        )

    # --публичный API--

    def new_num(self, levels: Sequence[LevelSpec], start: int = 1) -> int:
        """Свежие ``w:abstractNum`` + ``w:num``; возвращает numId.

        ``start`` корня кодируется ``w:start`` на ilvl 0 (не startOverride:
        LibreOffice применяет override к общему счётчику).
        """
        abstract_id = self._add_abstract_num(tuple(levels), root_start=start)

        num_id = self._next_num
        self._next_num += 1
        num = self._element("w:num", numId=num_id)
        self._sub(num, "w:abstractNumId", val=abstract_id)
        self._root.append(num)
        self._sync()
        return num_id

    def override_start(self, num_id: int, ilvl: int, start: int) -> None:
        """startOverride для вложенного уровня (редкий случай start≠1 у подтекста)."""
        num = next(
            (el for el in self._root.findall(qn("w:num")) if el.get(qn("w:numId")) == str(num_id)),
            None,
        )
        if num is None:
            return
        for existing in num.findall(qn("w:lvlOverride")):
            if existing.get(qn("w:ilvl")) == str(ilvl):
                num.remove(existing)
        override = self._sub(num, "w:lvlOverride", ilvl=ilvl)
        self._sub(override, "w:startOverride", val=start)
        self._sync()

    # --построение XML--

    def _add_abstract_num(
        self,
        signature: tuple[LevelSpec, ...],
        *,
        root_start: int = 1,
    ) -> int:
        abstract_id = self._next_abstract
        self._next_abstract += 1
        abstract = self._element("w:abstractNum", abstractNumId=abstract_id)
        self._sub(abstract, "w:multiLevelType", val="multilevel")
        for ilvl, spec in enumerate(signature):
            lvl = self._sub(abstract, "w:lvl", ilvl=ilvl)
            self._sub(lvl, "w:start", val=root_start if ilvl == 0 else 1)
            self._sub(lvl, "w:numFmt", val=spec.num_fmt)
            self._sub(lvl, "w:lvlText", val=spec.lvl_text)
            self._sub(lvl, "w:lvlJc", val="left")
            ppr = self._sub(lvl, "w:pPr")
            self._sub(
                ppr,
                "w:ind",
                left=Length(spec.left).twips,
                hanging=Length(spec.hanging).twips,
            )
        # w:abstractNum должен идти до w:num — вставляем перед первым num.
        first_num = self._root.find(qn("w:num"))
        if first_num is not None:
            self._root.insert(self._root.index(first_num), abstract)
        else:
            self._root.append(abstract)
        self._sync()
        return abstract_id

    @staticmethod
    def _element(tag: str, **attrs: object) -> Any:
        el = etree.Element(qn(tag), nsmap={"w": nsmap["w"]})
        for key, value in attrs.items():
            el.set(qn(f"w:{key}"), str(value))
        return el

    @staticmethod
    def _sub(parent: Any, tag: str, **attrs: object) -> Any:
        el = etree.SubElement(parent, qn(tag))
        for key, value in attrs.items():
            el.set(qn(f"w:{key}"), str(value))
        return el


# Реестры по частям документов: сам docx.Document — ElementProxy (unhashable),
# а DocumentPart — обычный объект, годится как слабый ключ.
_registries: WeakKeyDictionary[DocumentPart, Numbering] = WeakKeyDictionary()


def get_numbering(document: DocxDocument) -> Numbering:
    """Реестр нумерации для документа (лениво, один на документ)."""
    numbering = _registries.get(document.part)
    if numbering is None:
        numbering = Numbering(document)
        _registries[document.part] = numbering
    return numbering


def apply_num_pr(docx_paragraph: Any, ilvl: int, num_id: int) -> None:
    """Поставить ``w:numPr`` (ilvl + numId) в pPr параграфа."""
    num_pr = parse_xml(
        f'<w:numPr {nsdecls("w")}><w:ilvl w:val="{ilvl}"/><w:numId w:val="{num_id}"/></w:numPr>'
    )
    ppr = docx_paragraph._p.get_or_add_pPr()
    ppr.insert_element_before(num_pr, *_PPR_SUCCESORS)
