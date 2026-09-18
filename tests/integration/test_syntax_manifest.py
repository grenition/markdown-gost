from io import BytesIO

from docx import Document

from markdown_gost.config.loader import load_config_from_string
from markdown_gost.convert import convert


def test_docx_forward_links_have_targets_and_thematic_break_is_not_pagination():
    document = Document(
        BytesIO(
            convert(
                "См. [](#data) и [метод](#method).\n\n"
                "# Метод {#method}\n\n"
                "| A |\n|---|\n| 1 |\n\n: Данные {#data}\n\n---\n",
                load_config_from_string("preset: gost-7-32-2017\n"),
            )
        )
    )
    xml = document.element
    assert {"data", "method"} <= set(xml.xpath("//w:bookmarkStart/@w:name"))
    assert xml.xpath("//w:hyperlink/@w:anchor") == ["data", "method"]
    assert "Таблица 1" in "".join(xml.xpath("//w:hyperlink//w:t/text()"))
    assert len(xml.xpath("//w:pBdr/w:bottom")) == 1
