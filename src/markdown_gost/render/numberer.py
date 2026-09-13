from __future__ import annotations

from collections import defaultdict

_HEADING_LEVELS = 6
APPENDIX_LETTERS = "АБВГДЕЖИКЛМНПРСТУФХЦШЩЭЮЯ"


class Numberer:
    """Tracks per-category cross-reference counters (figures, tables, etc.).

    Также умеет вести многоуровневую нумерацию заголовков ``1.2.3.``: при
    инкременте уровня ``i`` сбрасывает все счётчики уровней ``i+1..N``.
    """

    def __init__(self) -> None:
        self._categories: dict[str, int] = defaultdict(int)
        self._heading_counters: list[int] = [0] * _HEADING_LEVELS
        self._current_appendix: str | None = None
        self._appendix_index = 0
        self._main_state: tuple[dict[str, int], list[int]] | None = None

    @property
    def current_appendix(self) -> str | None:
        return self._current_appendix

    def start_appendix(self, letter: str | None = None) -> str:
        if self._current_appendix is None:
            self._main_state = (dict(self._categories), list(self._heading_counters))
        if letter is None:
            letter = self._letter_at(self._appendix_index)
            self._appendix_index += 1
        else:
            if letter not in APPENDIX_LETTERS:
                raise ValueError(f"invalid appendix letter: {letter!r}")
            self._appendix_index = APPENDIX_LETTERS.index(letter) + 1
        self._current_appendix = letter
        self._categories = defaultdict(int)
        self._heading_counters = [0] * _HEADING_LEVELS
        return letter

    def end_appendix(self) -> None:
        if self._main_state is not None:
            categories, headings = self._main_state
            self._categories = defaultdict(int, categories)
            self._heading_counters = headings
        self._current_appendix = None
        self._main_state = None

    def get_current_number(self, category: str) -> int:
        return self._categories[category]

    def save_number(self, category: str, number: int) -> None:
        self._categories[category] = number

    def allocate(self, category: str) -> int:
        """Increment and return the next number for ``category``."""
        self._categories[category] += 1
        return self._categories[category]

    def format_number(self, category: str, number: int) -> str:
        del category
        if self._current_appendix is None:
            return str(number)
        return f"{self._current_appendix}.{number}"

    def bump_heading(self, level: int) -> str:
        """Увеличить счётчик заголовка уровня ``level`` и вернуть префикс ``"1.2 "``.

        Уровни нумеруются с 1. Все более глубокие уровни сбрасываются в 0.
        """
        if not 1 <= level <= _HEADING_LEVELS:
            raise ValueError(f"heading level must be in 1..{_HEADING_LEVELS}")
        idx = level - 1
        self._heading_counters[idx] += 1
        for i in range(idx + 1, _HEADING_LEVELS):
            self._heading_counters[i] = 0
        parts = [str(c) for c in self._heading_counters[: idx + 1]]
        if self._current_appendix is not None:
            return ".".join([self._current_appendix, *parts])
        return ".".join(parts)

    def heading_prefix_at(self, level: int) -> str:
        """Текущее состояние нумерации (без инкремента) — для тестов/отладки."""
        idx = level - 1
        parts = [str(c) for c in self._heading_counters[: idx + 1]]
        if self._current_appendix is not None:
            return ".".join([self._current_appendix, *parts])
        return ".".join(parts)

    @staticmethod
    def _letter_at(index: int) -> str:
        base = len(APPENDIX_LETTERS)
        if index < base:
            return APPENDIX_LETTERS[index]
        parts: list[str] = []
        n = index
        while n >= 0:
            n, rem = divmod(n, base)
            parts.append(APPENDIX_LETTERS[rem])
            n -= 1
        return "".join(reversed(parts))
