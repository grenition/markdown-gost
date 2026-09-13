"""LaTeX → OMML конверсия (T015).

Pipeline: ``latex2mathml.converter.convert`` → MathML → XSLT
(``mml2omml.xsl`` из MS Office, asset под ``_assets/``) → OMML
(``<m:oMath>``). Возвращаем чистый ``lxml`` element — caller вставляет
его в ``<w:p>`` (block) либо в ``<w:r>``-параграф (inline).

Why XSLT а не свой рукописный конвертер: XSLT покрывает почти весь
объём latex2mathml-вывода и стабильно работает с MS Word. Стилус-
шит — Microsoft public asset, ~150 КБ XSLT 1.0.

Невалидный LaTeX → :class:`EquationError` (любые exception'ы из
latex2mathml/lxml оборачиваем). Caller'ы (block ``Equation``,
inline path в ``Paragraph``) показывают красный плейсхолдер +
warning, конвертация не падает.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from importlib.resources import files
from typing import Any

from lxml import etree

_log = logging.getLogger(__name__)

_OMML_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_MML_NS = "http://www.w3.org/1998/Math/MathML"

# `(...)^N`, `[...]^N`, `{...}^N` — latex2mathml кладёт в базу msup только
# закрывающий `)`/`]`/`}`. LibreOffice такой OMML <m:sSup> с голой скобкой
# в базе рендерит как красный `¿`. Перед XSLT перегруппируем такие узлы:
# открывающую скобку, всё между ними и закрывающую — в `<mrow>` как базу.
_CLOSE_TO_OPEN = {")": "(", "]": "[", "}": "{"}


class EquationError(ValueError):
    """LaTeX, который не удалось конвертировать в OMML."""


@lru_cache(maxsize=1)
def _load_xslt() -> etree.XSLT:
    asset = files("markdown_gost.render") / "_assets" / "mml2omml.xsl"
    with asset.open("rb") as fh:
        tree = etree.parse(fh)
    return etree.XSLT(tree)


def latex_to_mathml(latex: str) -> str:
    """LaTeX → MathML (string).

    Используется как для OMML-конвертации (DOCX), так и для HTML preview
    (``<math>`` inline). :raises EquationError: для пустого / битого LaTeX.
    """

    expr = latex.strip()
    while expr.startswith("$") and expr.endswith("$"):
        expr = expr[1:-1]
    if not expr:
        raise EquationError("empty equation")

    try:
        import latex2mathml.converter

        return latex2mathml.converter.convert(expr)
    except Exception as exc:  # latex2mathml бросает разное
        raise EquationError(f"failed to convert LaTeX: {exc}") from exc


def latex_to_omml(latex: str) -> Any:
    """LaTeX → ``<m:oMath>`` lxml element.

    :raises EquationError: если latex2mathml / XSLT отвалились.
    """

    mathml = latex_to_mathml(latex)
    try:
        mathml_tree = etree.fromstring(mathml.encode("utf-8"))
        _rebalance_bracket_scripts(mathml_tree)
        omml_tree = _load_xslt()(mathml_tree)
        omml = omml_tree.getroot()
    except Exception as exc:
        raise EquationError(f"failed to convert LaTeX: {exc}") from exc

    _absorb_nary_operands(omml)
    return omml


def _rebalance_bracket_scripts(root: Any) -> None:
    """Перенести скобочную группу `(a)^2` целиком в базу ``<msup>``.

    latex2mathml для ``(x - M)^2`` выдаёт «плоскую» MathML:

        <mo>(</mo> ... <mo>)</mo>
        <msup><mo>)</mo><mn>2</mn></msup>

    — то есть базой ``msup`` остаётся только ``)``. После XSLT это даёт
    ``<m:sSup><m:e><m:r><m:t>)</m:t></m:r></m:e>…``, который LibreOffice
    отказывается превращать в StarMath и заменяет на красный ``¿``.

    Фикс: для каждого ``<msup>/<msub>/<msubsup>``, чья база — это ``<mo>``
    с одиночной закрывающей скобкой, идём по предыдущим сиблингам назад,
    находим парную открывающую и переносим всё это в ``<mrow>``, который
    становится новой базой. XSLT затем нормально переводит ``<mrow><mo>(</mo>
    …<mo>)</mo></mrow>`` в ``<m:d>`` (delimiter), и LO рендерит группу.
    """

    qn_mo = f"{{{_MML_NS}}}mo"
    qn_mrow = f"{{{_MML_NS}}}mrow"
    script_tags = {
        f"{{{_MML_NS}}}msup",
        f"{{{_MML_NS}}}msub",
        f"{{{_MML_NS}}}msubsup",
    }

    # iter() выдаёт элементы в document order; собираем в список заранее,
    # потому что мутируем родителей по ходу.
    for node in list(root.iter()):
        if node.tag not in script_tags:
            continue
        children = list(node)
        if not children:
            continue
        base = children[0]
        if base.tag != qn_mo:
            continue
        close_char = (base.text or "").strip()
        open_char = _CLOSE_TO_OPEN.get(close_char)
        if open_char is None:
            continue

        parent = node.getparent()
        if parent is None:
            continue
        idx = parent.index(node)

        # Идём назад по сиблингам node, ищем парную открывающую скобку.
        depth = 1
        start_idx: int | None = None
        for j in range(idx - 1, -1, -1):
            sib = parent[j]
            if sib.tag != qn_mo:
                continue
            text = (sib.text or "").strip()
            if text == close_char:
                depth += 1
            elif text == open_char:
                depth -= 1
                if depth == 0:
                    start_idx = j
                    break
        if start_idx is None:
            continue

        # parent[start_idx:idx] + base → новая база-mrow.
        new_base = etree.Element(qn_mrow)
        preceding = list(parent)[start_idx:idx]
        for sib in preceding:
            parent.remove(sib)
            new_base.append(sib)
        node.remove(base)
        new_base.append(base)
        node.insert(0, new_base)


def _absorb_nary_operands(omml: Any) -> None:
    """Перетянуть следующих сиблингов внутрь пустого ``<m:e/>`` у ``<m:nary>``.

    XSLT (mml2omml) транслирует ``\\sum_a^b x_i``/``\\int_0^1 f\\,dx`` в:

        <m:nary> ... <m:e/></m:nary>
        <m:r>...x...</m:r>
        ...

    LibreOffice рендерит пустой ``<m:e/>`` как пустой плейсхолдер-□.
    Нужно перенести всё, что идёт после ``<m:nary>`` (до конца его
    родителя) внутрь ``<m:e>``. Это совпадает с TeX-конвенцией «ny ∑/∫
    «жадно» съедает оставшийся expression».
    """

    nsmap = {"m": _OMML_NS}
    for nary in omml.xpath(".//m:nary", namespaces=nsmap):
        e = nary.find(f"{{{_OMML_NS}}}e")
        if e is None or len(e) > 0:
            continue
        parent = nary.getparent()
        if parent is None:
            continue
        idx = parent.index(nary)
        siblings = list(parent)[idx + 1 :]
        for sib in siblings:
            parent.remove(sib)
            e.append(sib)


def apply_run_props(omml: Any, *, font_pt: float, font_name: str | None = None) -> None:
    """Прописать ``<w:rPr>`` (sz, font) в каждый ``<m:r>`` OMML-дерева.

    LibreOffice исторически игнорирует размер math-runs и берёт дефолт
    StarMath (~10pt) — в MS Word всё OK. Тем не менее проставляем:
    в Word'е это даёт корректный 14pt; для LO — best-effort.
    """

    half_points = str(int(round(font_pt * 2)))
    nsmap = {"m": _OMML_NS, "w": _W_NS}
    runs = omml.xpath(".//m:r", namespaces=nsmap)
    for r in runs:
        rpr = r.find(f"{{{_OMML_NS}}}rPr")
        if rpr is None:
            rpr = etree.SubElement(r, f"{{{_OMML_NS}}}rPr")
            r.insert(0, rpr)
        # Внутри m:rPr допустим w:rPr — Word'ом это понимается.
        w_rpr = rpr.find(f"{{{_W_NS}}}rPr")
        if w_rpr is None:
            w_rpr = etree.SubElement(rpr, f"{{{_W_NS}}}rPr")
        # size
        sz = w_rpr.find(f"{{{_W_NS}}}sz")
        if sz is None:
            sz = etree.SubElement(w_rpr, f"{{{_W_NS}}}sz")
        sz.set(f"{{{_W_NS}}}val", half_points)
        sz_cs = w_rpr.find(f"{{{_W_NS}}}szCs")
        if sz_cs is None:
            sz_cs = etree.SubElement(w_rpr, f"{{{_W_NS}}}szCs")
        sz_cs.set(f"{{{_W_NS}}}val", half_points)
        # font
        if font_name:
            rfonts = w_rpr.find(f"{{{_W_NS}}}rFonts")
            if rfonts is None:
                rfonts = etree.SubElement(w_rpr, f"{{{_W_NS}}}rFonts")
            rfonts.set(f"{{{_W_NS}}}ascii", font_name)
            rfonts.set(f"{{{_W_NS}}}hAnsi", font_name)
            rfonts.set(f"{{{_W_NS}}}cs", font_name)
