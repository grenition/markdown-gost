from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Generator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from docx.shared import Length

if TYPE_CHECKING:
    from markdown_gost.render.layout_tracker import LayoutState
    from markdown_gost.render.render_index import RenderIndex


@dataclass(frozen=True)
class RenderedInfo:
    """Immutable output of a single render step: an XML element + its height."""

    # ``Any`` here is intentional: docx 1.x splits the old ``Parented`` into
    # several incompatible base classes (``StoryChild`` etc.) that mypy can't
    # reconcile cleanly. Runtime contract is "anything python-docx accepts as
    # a body child" — DocxParagraph, Table, etc.
    docx_element: Any
    height: Length


@dataclass(frozen=True)
class SubRenderable:
    """A nested renderable yielded by another renderable.

    If ``add_to_new_page`` is True, the renderer defers the child until the
    current page is flushed (used for floats: figures, tables that should
    appear on the next page).
    """

    renderable: Renderable
    add_to_new_page: bool


class Renderable(ABC):
    """Base interface for everything that can be placed into the document."""

    identifier: str | None = None

    @abstractmethod
    def render(
        self,
        previous_rendered: RenderedInfo | None,
        layout_state: LayoutState,
    ) -> Generator[RenderedInfo | SubRenderable]:
        """Yield rendered info objects (or nested renderables) for this element."""

    def added_to_document(self) -> None:  # noqa: B027 — intentional no-op hook
        """Hook called after the renderable's elements are appended."""

    def post_process(  # noqa: B027 — intentional no-op hook
        self, index: RenderIndex, document: Any
    ) -> None:
        """Hook второго прохода (T016).

        Вызывается ``Renderer.process`` после того, как все renderable'ы
        отрендерены и ``index`` заполнен (заголовки, нумерованные объекты,
        ``total_pages``). Renderable может опереться на эти данные и
        замутировать уже размещённые в документе элементы — например,
        подставить плейсхолдер ``{TOTAL}`` фактическим числом страниц.

        Дефолтный no-op: для большинства renderable'ов второй проход не нужен.
        """


class RequiresNumbering:
    """Mixin for renderables that participate in cross-reference numbering.

    Subclasses must implement :meth:`set_number` and provide
    ``numbering_category`` via ``__init__``.
    """

    numbering_category: str

    def __init__(self, category: str) -> None:
        self.numbering_category = category

    def set_number(self, number: int | str) -> None:
        raise NotImplementedError
