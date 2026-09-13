"""Юнит-тесты для :mod:`markdown_gost.render.latex_math` (T015).

LaTeX → MathML (latex2mathml) → OMML (XSLT). Хорошие LaTeX выражения
дают валидный ``<m:oMath>``-элемент; плохие — поднимают
:class:`EquationError` (callers переводят в красный плейсхолдер).
"""

from __future__ import annotations

import pytest

_OMML_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"


def _qn(tag: str) -> str:
    return f"{{{_OMML_NS}}}{tag}"


def test_simple_equation_returns_omath_root():
    from markdown_gost.render.latex_math import latex_to_omml

    el = latex_to_omml("2+2=4")
    assert el.tag == _qn("oMath"), el.tag
    runs = el.findall(f".//{_qn('r')}")
    assert runs, "ожидаем хотя бы один <m:r> внутри <m:oMath>"


def test_fraction_produces_m_f():
    from markdown_gost.render.latex_math import latex_to_omml

    el = latex_to_omml(r"\frac{a}{b}")
    fractions = el.findall(f".//{_qn('f')}")
    assert fractions, "ожидаем <m:f> для \\frac"


def test_invalid_latex_raises_equation_error():
    from markdown_gost.render.latex_math import EquationError, latex_to_omml

    with pytest.raises(EquationError):
        # `\frac` без аргументов — latex2mathml бросает NoAvailableTokensError.
        latex_to_omml(r"\frac")


def test_dollars_around_input_are_stripped():
    """``$$E=mc^2$$`` ≡ ``E=mc^2`` — лишние ``$`` снимаются."""

    from markdown_gost.render.latex_math import latex_to_omml

    el = latex_to_omml("$$E=mc^2$$")
    assert el.tag == _qn("oMath")


def test_apply_run_props_writes_size_in_half_points():
    from markdown_gost.render.latex_math import apply_run_props, latex_to_omml

    el = latex_to_omml("a+b")
    apply_run_props(el, font_pt=14, font_name="Times New Roman")

    w_ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    runs = el.findall(f".//{_qn('r')}")
    assert runs
    sz_values = []
    for r in runs:
        sz = r.find(f"{_qn('rPr')}/{{{w_ns}}}rPr/{{{w_ns}}}sz")
        assert sz is not None
        sz_values.append(sz.get(f"{{{w_ns}}}val"))
    assert all(v == "28" for v in sz_values), sz_values


def test_nary_operands_are_absorbed_into_e():
    """``\\sum_a^b x``: оператор и операнд в OMML — сиблинги; XSLT пишет
    пустой ``<m:e/>``. Нужно перетянуть всё, что после ``<m:nary>``,
    внутрь ``<m:e>`` — иначе LibreOffice показывает □-плейсхолдер.
    """

    from markdown_gost.render.latex_math import latex_to_omml

    el = latex_to_omml(r"\sum_{i=1}^n x_i")
    nary = el.find(_qn("nary"))
    assert nary is not None
    e = nary.find(_qn("e"))
    assert e is not None
    assert len(e) > 0, "ожидаем, что <m:e> заполнен операндом x_i"
    # После nary не должно остаться сиблингов внутри oMath.
    assert el.index(nary) == len(list(el)) - 1


def test_integral_with_differential_absorbs_full_tail():
    """``\\int_0^1 x^2 dx`` — ``x²`` и ``dx`` оба «съедаются» под integral."""

    from markdown_gost.render.latex_math import latex_to_omml

    el = latex_to_omml(r"\int_0^1 x^2 \, dx")
    nary = el.find(_qn("nary"))
    e = nary.find(_qn("e"))
    # Под интегралом должны оказаться и x² (sSup), и dx (run).
    has_ssup = e.find(_qn("sSup")) is not None
    has_dx_run = any(
        (r.find(_qn("t")) is not None and "dx" in (r.find(_qn("t")).text or ""))
        for r in e.findall(_qn("r"))
    )
    assert has_ssup
    assert has_dx_run


def _base_text(s_script):
    """Собрать весь текст внутри ``<m:e>`` ``sSup``/``sSub``/``sSubSup``."""
    e = s_script.find(_qn("e"))
    assert e is not None
    return "".join((t.text or "") for t in e.iter(_qn("t")))


def test_paren_group_power_rebalanced_into_msup_base():
    """``(x - M)^2``: latex2mathml ставит в базу ``msup`` только ``)``,
    из-за чего LibreOffice рендерит OMML как красный ``¿``. Перебалансируем
    MathML так, чтобы базой стало ``(x - M)`` целиком.
    """

    from markdown_gost.render.latex_math import latex_to_omml

    el = latex_to_omml(r"(x - M)^2")
    s_sup = el.find(_qn("sSup"))
    assert s_sup is not None, "ожидаем <m:sSup> для ^2"
    base_text = _base_text(s_sup)
    assert base_text.startswith("(") and base_text.endswith(")"), (
        f"база sSup должна содержать всю группу `(x − M)`, получили: "
        f"{base_text!r}"
    )
    assert "x" in base_text and "M" in base_text


def test_bracket_group_power_rebalanced():
    """То же для ``[a+b]^n`` — квадратные скобки тоже группируются."""

    from markdown_gost.render.latex_math import latex_to_omml

    el = latex_to_omml(r"[a + b]^n")
    s_sup = el.find(_qn("sSup"))
    assert s_sup is not None
    base_text = _base_text(s_sup)
    assert base_text.startswith("[") and base_text.endswith("]"), base_text


def test_subscript_with_paren_group_is_rebalanced():
    """``(a+b)_n`` — подстрочный индекс тоже должен видеть всю группу."""

    from markdown_gost.render.latex_math import latex_to_omml

    el = latex_to_omml(r"(a + b)_n")
    s_sub = el.find(_qn("sSub"))
    assert s_sub is not None
    base_text = _base_text(s_sub)
    assert base_text.startswith("(") and base_text.endswith(")"), base_text


def test_simple_msup_without_brackets_is_untouched():
    """``x^2`` остаётся как был — никакого ребаланса не должно произойти.
    Регрессионный страховщик: правило срабатывает ТОЛЬКО на голую скобку.
    """

    from markdown_gost.render.latex_math import latex_to_omml

    el = latex_to_omml(r"x^2")
    s_sup = el.find(_qn("sSup"))
    assert s_sup is not None
    assert _base_text(s_sup) == "x"


def test_apply_run_props_writes_font_family():
    from markdown_gost.render.latex_math import apply_run_props, latex_to_omml

    el = latex_to_omml("a")
    apply_run_props(el, font_pt=14, font_name="Times New Roman")

    w_ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    rfonts = el.find(
        f".//{_qn('r')}/{_qn('rPr')}/{{{w_ns}}}rPr/{{{w_ns}}}rFonts"
    )
    assert rfonts is not None
    assert rfonts.get(f"{{{w_ns}}}ascii") == "Times New Roman"
