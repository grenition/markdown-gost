from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from markdown_gost.config.schema import Config
from markdown_gost.core.ast import nodes as ast


@dataclass(frozen=True)
class BibliographyEntry:
    number: int
    source: ast.BibliographySource


class BibliographyIndex:
    def __init__(
        self,
        config: Config,
        sources_by_id: dict[str, ast.BibliographySource],
        entries: list[BibliographyEntry],
    ) -> None:
        self._config = config
        self._sources_by_id = sources_by_id
        self._entries = entries
        self._numbers_by_id = {entry.source.id: entry.number for entry in entries}

    @classmethod
    def from_document(cls, document: ast.Document, config: Config) -> BibliographyIndex:
        sources = _collect_sources(document)
        citations = _collect_citations(document)
        source_ids = {source.id for source in sources}
        for key in citations:
            if key not in source_ids:
                raise ValueError(f"missing bibliography source for citation {key!r}")

        ordered_sources = _order_sources(sources, citations, config.bibliography.order)
        entries = [
            BibliographyEntry(number=idx, source=source)
            for idx, source in enumerate(ordered_sources, start=1)
        ]
        return cls(
            config,
            {source.id: source for source in ordered_sources},
            entries,
        )

    def entries(self) -> list[BibliographyEntry]:
        return list(self._entries)

    def number_for(self, key: str) -> int:
        try:
            return self._numbers_by_id[key]
        except KeyError as exc:
            raise ValueError(f"missing bibliography source for citation {key!r}") from exc

    def format_citation(self, key: str) -> str:
        n = self.number_for(key)
        try:
            return self._config.bibliography.citation_format.format(n=n)
        except (KeyError, IndexError):
            return self._config.bibliography.citation_format

    def format_entry(self, key: str) -> str:
        try:
            source = self._sources_by_id[key]
        except KeyError as exc:
            raise ValueError(f"missing bibliography source {key!r}") from exc
        if self._config.bibliography.style != "minimal-gost":
            raise ValueError(
                f"unsupported bibliography style: {self._config.bibliography.style!r}"
            )
        return _format_minimal_gost(source)


def _collect_sources(document: ast.Document) -> list[ast.BibliographySource]:
    sources: list[ast.BibliographySource] = []
    seen: set[str] = set()
    for child in document.children:
        if not isinstance(child, ast.Bibliography):
            continue
        for source in child.sources:
            if source.id in seen:
                raise ValueError(f"duplicate bibliography source id {source.id!r}")
            seen.add(source.id)
            sources.append(source)
    return sources


def _order_sources(
    sources: list[ast.BibliographySource],
    citations: list[str],
    order: str,
) -> list[ast.BibliographySource]:
    if order == "input" or not citations:
        return list(sources)

    sources_by_id = {source.id: source for source in sources}
    ordered_ids: list[str] = []
    seen: set[str] = set()
    for key in citations:
        if key in seen:
            continue
        seen.add(key)
        ordered_ids.append(key)

    return [sources_by_id[source_id] for source_id in ordered_ids]


def _collect_citations(document: ast.Document) -> list[str]:
    citations: list[str] = []
    for child in document.children:
        _collect_citations_from_node(child, citations)
    return citations


def _collect_citations_from_node(node: ast.Node, out: list[str]) -> None:
    if isinstance(node, ast.Citation):
        out.append(node.key)
        return
    if isinstance(node, ast.Text | ast.InlineCode | ast.LineBreak | ast.InlineEquation):
        return
    if isinstance(node, ast.Reference):
        return
    if isinstance(node, ast.Image):
        return
    if isinstance(node, ast.Bibliography):
        return

    if isinstance(node, ast.Table):
        for row in node.rows:
            _collect_citations_from_node(row, out)
        return
    if isinstance(node, ast.TableRow):
        for cell in node.cells:
            _collect_citations_from_node(cell, out)
        return
    if isinstance(node, ast.TableCell):
        for child in node.children:
            _collect_citations_from_node(child, out)
        return
    if isinstance(node, ast.List):
        for item in node.items:
            _collect_citations_from_node(item, out)
        return

    children = getattr(node, "children", None)
    if isinstance(children, list):
        for child in children:
            _collect_citations_from_node(child, out)


def _format_minimal_gost(source: ast.BibliographySource) -> str:
    raw = source.fields.get("text")
    if raw is not None:
        return str(raw)

    authors = _format_authors(source.fields.get("authors"))
    title = _string_field(source.fields.get("title"))
    city = _string_field(source.fields.get("city"))
    publisher = _string_field(source.fields.get("publisher"))
    year = _string_field(source.fields.get("year"))
    url = _string_field(source.fields.get("url"))

    parts: list[str] = []
    if authors and title:
        parts.append(f"{authors} {title}")
    elif authors:
        parts.append(authors)
    elif title:
        parts.append(title)

    imprint = _format_imprint(city, publisher, year)
    if imprint:
        parts.append(imprint)
    if url:
        parts.append(f"URL: {url}")
    return ". ".join(parts)


def _format_authors(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if str(item))
    return str(value)


def _format_imprint(city: str, publisher: str, year: str) -> str:
    if city and publisher and year:
        return f"{city}: {publisher}, {year}"
    if city and publisher:
        return f"{city}: {publisher}"
    if publisher and year:
        return f"{publisher}, {year}"
    return city or publisher or year


def _string_field(value: Any) -> str:
    if value is None:
        return ""
    return str(value)
