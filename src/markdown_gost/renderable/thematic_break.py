"""CommonMark thematic break, distinct from pagination."""

from typing import Any

from markdown_gost.config.schema import Config
from markdown_gost.renderable._oxml import create_element
from markdown_gost.renderable.paragraph import Paragraph


class ThematicBreak(Paragraph):
    def __init__(self, parent: Any, config: Config) -> None:
        super().__init__(parent, config)
        self.docx_paragraph._p.get_or_add_pPr().append(
            create_element(
                "w:pBdr",
                [create_element("w:bottom", {"w:val": "single", "w:sz": "4", "w:color": "auto"})],
            )
        )
