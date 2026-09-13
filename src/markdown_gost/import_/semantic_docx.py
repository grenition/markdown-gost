"""Expose markdown-gost semantic structures to Pandoc in a temporary DOCX copy.

The exported numbering table is layout, not a data table. Structural headings
use a custom visual style which Pandoc otherwise treats as ordinary paragraphs.
The author's source file is never modified.
"""

from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path
from zipfile import ZipFile, is_zipfile

from lxml import etree

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
_NS = {"w": _W, "m": _M}


def prepare_pandoc_input(source: Path, target: Path) -> Path:
    if not is_zipfile(source):
        return source
    with ZipFile(source) as archive:
        if not {"word/document.xml", "word/styles.xml"} <= set(archive.namelist()):
            return source
        parser = etree.XMLParser(resolve_entities=False, no_network=True)
        document = etree.fromstring(archive.read("word/document.xml"), parser)
        styles = etree.fromstring(archive.read("word/styles.xml"), parser)
        changed = False
        for style in styles.findall("w:style", _NS):
            name = style.find("w:name", _NS)
            if name is not None and name.get(f"{{{_W}}}val") == "MD2GOST Structural Heading":
                name.set(f"{{{_W}}}val", "heading 1")
                changed = True
        for table in document.findall(".//w:tbl", _NS):
            borders = table.find("w:tblPr/w:tblBorders", _NS)
            if borders is None or any(border.get(f"{{{_W}}}val") != "none" for border in borders):
                continue
            rows = table.findall("w:tr", _NS)
            math = table.findall(".//m:oMath", _NS)
            math_rows = [row for row in rows if row.find(".//m:oMath", _NS) is not None]
            if not math or any(len(row.findall("w:tc", _NS)) != 2 for row in math_rows):
                continue
            text = "".join(table.xpath(".//w:t/text()", namespaces=_NS)).strip()
            if not re.fullmatch(r"\(?[\w.]+\)?", text):
                continue
            parent = table.getparent()
            if parent is None:
                continue
            position = parent.index(table)
            for formula in math:
                paragraph = etree.Element(f"{{{_W}}}p")
                display = etree.SubElement(paragraph, f"{{{_M}}}oMathPara")
                display.append(deepcopy(formula))
                parent.insert(position, paragraph)
                position += 1
            parent.remove(table)
            changed = True
        if not changed:
            return source
        with ZipFile(target, "w") as output:
            for member in archive.infolist():
                if member.filename == "word/document.xml":
                    data = etree.tostring(document, xml_declaration=True, encoding="UTF-8")
                elif member.filename == "word/styles.xml":
                    data = etree.tostring(styles, xml_declaration=True, encoding="UTF-8")
                else:
                    data = archive.read(member.filename)
                output.writestr(member, data)
    return target
