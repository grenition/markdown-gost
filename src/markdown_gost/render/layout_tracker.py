from __future__ import annotations

from copy import copy

from docx.shared import Length


class LayoutState:
    """Snapshot of the page-layout cursor: max page size + current offset.

    Heights are kept in EMU (``docx.shared.Length`` is just ``int``); the
    tracker stores the *cumulative* height across all pages so paging is a
    pure modulo operation against ``max_height``.
    """

    def __init__(self, max_height: Length, max_width: Length) -> None:
        self.max_height: Length = max_height
        self.max_width: Length = max_width
        self._current_height: Length = Length(0)

    def new_page(self) -> None:
        self._current_height = Length(self._current_height + self.remaining_page_height)

    @property
    def current_page_height(self) -> Length:
        return Length(self._current_height % self.max_height)

    @property
    def remaining_page_height(self) -> Length:
        return Length(self.max_height - self.current_page_height)

    @property
    def page(self) -> int:
        return self._current_height // self.max_height + 1

    def add_height(self, height: Length) -> None:
        self._current_height = Length(self._current_height + height)


class LayoutTracker:
    """Owns a mutable :class:`LayoutState` and reports page transitions."""

    def __init__(self, max_height: Length, max_width: Length) -> None:
        self._state = LayoutState(max_height, max_width)
        self._is_new_page = False

    @property
    def current_state(self) -> LayoutState:
        # return a copy so callers can't mutate the tracker's state by accident
        return copy(self._state)

    @property
    def is_new_page(self) -> bool:
        return self._is_new_page

    def add_height(self, height: Length) -> None:
        page_before = self._state.page
        self._state.add_height(height)
        self._is_new_page = self._state.page > page_before

    def can_fit_to_page(self, height: Length) -> bool:
        return height <= self._state.remaining_page_height

    def new_page(self) -> None:
        self._state.new_page()
