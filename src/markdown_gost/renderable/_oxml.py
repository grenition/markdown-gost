"""Маленький helper для создания OxmlElement (порт ``util.create_element``)."""

from __future__ import annotations

from typing import Any

from docx.oxml import OxmlElement
from docx.oxml.ns import qn


def create_element(name: str, *args: Any) -> Any:
    """Создать OxmlElement с атрибутами/детьми/текстом.

    Принимает варьируемые аргументы:
    - ``dict[str, str]`` — атрибуты;
    - ``list[_Element]`` — дочерние элементы;
    - ``str`` — текст.
    """

    attrs: dict[str, str] = {}
    children: list[Any] = []
    text: str | None = None

    for arg in args:
        if isinstance(arg, dict):
            attrs.update(arg)
        elif isinstance(arg, list):
            children.extend(arg)
        elif isinstance(arg, str):
            text = arg

    element = OxmlElement(
        name,
        {(qn(key) if ":" in key else key): value for key, value in attrs.items()},
    )
    for child in children:
        element.append(child)
    if text is not None:
        element.text = text
    return element
