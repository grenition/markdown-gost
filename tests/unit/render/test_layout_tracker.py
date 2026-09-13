from __future__ import annotations

from docx.shared import Cm, Length

from markdown_gost.render.layout_tracker import LayoutState, LayoutTracker


def _tracker() -> LayoutTracker:
    return LayoutTracker(max_height=Cm(20), max_width=Cm(15))


def test_initial_state() -> None:
    tracker = _tracker()
    state = tracker.current_state
    assert isinstance(state, LayoutState)
    assert state.page == 1
    assert state.current_page_height == 0
    assert state.remaining_page_height == Cm(20)
    assert tracker.is_new_page is False


def test_add_height_without_overflow() -> None:
    tracker = _tracker()
    tracker.add_height(Length(Cm(5)))
    assert tracker.is_new_page is False
    assert tracker.current_state.page == 1
    assert tracker.current_state.current_page_height == Cm(5)
    assert tracker.current_state.remaining_page_height == Cm(15)


def test_add_height_with_overflow_marks_new_page() -> None:
    tracker = _tracker()
    tracker.add_height(Length(Cm(15)))
    assert tracker.is_new_page is False
    tracker.add_height(Length(Cm(10)))  # overflows the remaining 5cm
    assert tracker.is_new_page is True
    assert tracker.current_state.page == 2


def test_can_fit_to_page() -> None:
    tracker = _tracker()
    tracker.add_height(Length(Cm(15)))
    assert tracker.can_fit_to_page(Length(Cm(5))) is True
    assert tracker.can_fit_to_page(Length(Cm(6))) is False


def test_explicit_new_page_flushes_remaining_height() -> None:
    tracker = _tracker()
    tracker.add_height(Length(Cm(3)))
    tracker.new_page()
    assert tracker.current_state.page == 2
    assert tracker.current_state.current_page_height == 0
    assert tracker.current_state.remaining_page_height == Cm(20)


def test_multi_page_overflow_chain() -> None:
    tracker = _tracker()
    # three sequential overflows -> page should advance to 4
    tracker.add_height(Length(Cm(25)))
    assert tracker.current_state.page == 2
    tracker.add_height(Length(Cm(20)))
    assert tracker.current_state.page == 3
    tracker.add_height(Length(Cm(20)))
    assert tracker.current_state.page == 4


def test_current_state_is_independent_copy() -> None:
    tracker = _tracker()
    snapshot = tracker.current_state
    tracker.add_height(Length(Cm(5)))
    # mutating the tracker should not retroactively change the snapshot
    assert snapshot.current_page_height == 0
    assert snapshot.page == 1
    assert tracker.current_state.current_page_height == Cm(5)
