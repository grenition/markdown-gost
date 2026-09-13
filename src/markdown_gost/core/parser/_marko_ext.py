"""Context-aware extensions; normative contract: skills/markdown-gost/syntax.md."""

from __future__ import annotations

import re
from re import Match

from marko import block, inline
from marko.helpers import MarkoExtension
from marko.source import Source

from .attrs import parse_attributes, split_attributes


class Heading(block.Heading):
    override = True

    def __init__(self, match: Match[str]) -> None:
        super().__init__(match)
        self.inline_body, self.attrs = split_attributes(self.inline_body)


class AttributeBlock(block.BlockElement):
    priority = 7
    pattern = re.compile(r" {0,3}(\{[^{}\n]+\})[ \t]*(?:\n|$)")

    def __init__(self, match: Match[str]) -> None:
        self.attrs = parse_attributes(match.group(1))

    @classmethod
    def match(cls, source: Source) -> Match[str] | None:
        return source.expect_re(cls.pattern)

    @classmethod
    def parse(cls, source: Source) -> Match[str] | None:
        match = source.match
        source.consume()
        return match


class Caption(AttributeBlock):
    pattern = re.compile(r" {0,3}: ([^\n]+)[ \t]*(?:\n|$)")

    def __init__(self, match: Match[str]) -> None:
        self.caption_text, self.attrs = split_attributes(match.group(1))


class Equation(AttributeBlock):
    pattern = re.compile(r" {0,3}\$\$([\s\S]*?)\$\$[ \t]*(?:\n|$)")

    def __init__(self, match: Match[str]) -> None:
        self.latex = match.group(1).strip()


class Container(block.BlockElement):
    priority = 8
    pattern = re.compile(r" {0,3}(:{3,})[ \t]+(\{[^{}\n]+\})[ \t]*(?:\n|$)")

    def __init__(self, data: tuple[dict[str, str], str]) -> None:
        self.attrs, self.body = data

    @classmethod
    def match(cls, source: Source) -> Match[str] | None:
        return source.expect_re(cls.pattern)

    @classmethod
    def parse(cls, source: Source) -> tuple[dict[str, str], str]:
        assert source.match is not None
        fence = source.match.group(1)
        attrs = parse_attributes(source.match.group(2))
        source.consume()
        lines: list[str] = []
        code_fence: str | None = None
        while line := source.next_line():
            source.consume()
            if code_fence is None and line.strip() == fence:
                return attrs, "".join(lines)
            code = re.match(r" {0,3}(`{3,}|~{3,})(.*)", line)
            if code:
                marker, suffix = code.groups()
                if code_fence is None:
                    code_fence = marker
                elif (
                    marker[0] == code_fence[0]
                    and len(marker) >= len(code_fence)
                    and not suffix.strip()
                ):
                    code_fence = None
            lines.append(line)
        raise ValueError("unclosed Markdown container")


class InlineEquation(inline.InlineElement):
    pattern = re.compile(r"\$(?!\$)([^\n$]+?)\$(?!\$)")
    priority = 7

    def __init__(self, match: Match[str]) -> None:
        self.latex = match.group(1)


class Citation(inline.InlineElement):
    pattern = re.compile(r"\[@([^\W\d][\w-]*)\]", re.UNICODE)
    priority = 7

    def __init__(self, match: Match[str]) -> None:
        self.key = match.group(1)


class Underline(inline.InlineElement):
    pattern = re.compile(r"\[((?:\\.|[^\[\]\n])+)\]\{\.underline\}")
    priority = 7
    parse_children = True

    def __init__(self, match: Match[str]) -> None:
        pass


class InlineAttributes(inline.InlineElement):
    pattern = re.compile(r"\{((?:[#.]\w|[A-Za-z_]\w*\s*=)[^{}\n]*)\}")
    priority = 5

    def __init__(self, match: Match[str]) -> None:
        self.raw = match.group(0)


class Paragraph(block.Paragraph):
    override = True

    @classmethod
    def break_paragraph(cls, source: Source, lazy: bool = False) -> bool:
        if super().break_paragraph(source, lazy):
            return True
        previous = source.match
        try:
            return any(
                element.match(source) for element in (Container, Caption, Equation, AttributeBlock)
            )
        finally:
            source.match = previous


GostExtension = MarkoExtension(
    elements=[
        Heading,
        Caption,
        Equation,
        AttributeBlock,
        Container,
        InlineEquation,
        Citation,
        Underline,
        InlineAttributes,
        Paragraph,
    ]
)
