"""SymPy-backed LaTeX oralizer migrated from demo_parse_latex.py."""

from __future__ import annotations

import re
from typing import Any, Optional

from sympy import Add, Eq, Function, Integer, Mul, Pow, Rational, Symbol
from sympy.core.function import AppliedUndef
from sympy.core.relational import Relational
from sympy.parsing.latex import parse_latex


def normalize_latex_for_parser(text: str) -> str:
    s = text.strip()
    s = re.sub(r"^\$\$(.*)\$\$$", r"\1", s, flags=re.DOTALL)
    s = re.sub(r"^\$(.*)\$$", r"\1", s, flags=re.DOTALL)
    # 把粘连写法拆开：\partialQ -> \partial Q, \partialx -> \partial x
    s = re.sub(r"\\partial(?![\s\^_\\{])([A-Za-z])", r"\\partial \1", s)
    s = re.sub(r"\\partial\s+([A-Za-z])(?=[A-Za-z])", r"\\partial \1", s)

    s = re.sub(
        r"\\(sin|cos|tan|cot)\s+([A-Za-z])\s*\^\s*(\{[^{}]+\}|[A-Za-z0-9]+)",
        r"\\\1(\2^\3)",
        s,
    )
    s = re.sub(
        r"\\(sin|cos|tan|cot)\s+([A-Za-z0-9]+)",
        r"\\\1(\2)",
        s,
    )
    s = s.replace(r"\dfrac", r"\frac").replace(r"\tfrac", r"\frac")
    s = re.sub(
        r"\\underset\s*\{([^{}]+)\}\s*\{\s*\\mathop\s*\{\s*\\lim\s*\}\s*\}",
        lambda m: fr"\lim_{{{m.group(1).strip()}}}",
        s,
    )
    s = re.sub(
        r"\\underset\s*\{([^{}]+)\}\s*\{\s*\\lim\s*\}",
        lambda m: fr"\lim_{{{m.group(1).strip()}}}",
        s,
    )
    s = re.sub(r"\\mathop\s*\{\s*\\lim\s*\}", lambda _m: r"\lim", s)
    s = re.sub(r"\\,|\\;|\\!|\\quad|\\qquad", " ", s)
    s = re.sub(r"\\mathrm\s*\{\s*e\s*\}", "e", s)
    s = re.sub(r"\\mathrm\s*\{\s*d\s*\}", "d", s)
    s = re.sub(r"\bd\s*x\b", "dx", s)
    s = re.sub(r"\bd\s*y\b", "dy", s)
    s = re.sub(r"\bd\s*z\b", "dz", s)
    s = re.sub(r"\bd\s*s\b", "ds", s)
    s = re.sub(r"=\s*$", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def strip_outer_latex_wrappers(text: str) -> str:
    s = text.strip()
    m = re.fullmatch(r"\\left\((.*)\\right\)", s, flags=re.DOTALL)
    if m:
        return m.group(1).strip()
    if s.startswith("(") and s.endswith(")"):
        inner = s[1:-1].strip()
        if inner.count("(") == inner.count(")"):
            return inner
    if s.startswith("{") and s.endswith("}"):
        inner = s[1:-1].strip()
        if inner.count("{") == inner.count("}"):
            return inner
    return s


def normalize_region_name(raw: str) -> str:
    s = raw.strip()
    mapping = {
        r"\Omega": "Ω",
        r"\omega": "ω",
        r"\Gamma": "Γ",
        r"\gamma": "γ",
        r"\Sigma": "Σ",
        r"\sigma": "σ",
        r"\pi": "π",
    }
    for key, value in mapping.items():
        s = s.replace(key, value)
    return s


def normalize_exponent_for_speech(exp):
    """
    把指数尽量规整成 Rational。
    例如：
    -1/2
    Mul(-1, Rational(1,2))
    都尽量变成 Rational(-1, 2)
    """
    try:
        if getattr(exp, "is_Rational", False):
            return Rational(exp)
    except Exception:
        pass

    if isinstance(exp, Mul):
        coeff = Rational(1, 1)
        others = []

        for arg in exp.args:
            if getattr(arg, "is_Rational", False):
                coeff *= Rational(arg)
            else:
                others.append(arg)

        if not others:
            return coeff

        if len(others) == 1:
            candidate = coeff * others[0]
            try:
                if getattr(candidate, "is_Rational", False):
                    return Rational(candidate)
            except Exception:
                pass

    return exp


def speak_atom_text(text: str) -> str:
    s = text.strip()
    replacements = {
        r"\infty": "无穷大",
        "∞": "无穷大",
        r"\to": "趋近于",
        r"\leq": "小于等于",
        r"\geq": "大于等于",
        r"\neq": "不等于",
        r"\sin": "正弦",
        r"\cos": "余弦",
        r"\tan": "正切",
        r"\cot": "余切",
        r"\ln": "自然对数",
        r"\pi": "π",
        r"\Gamma": "Γ",
        r"\gamma": "γ",
        r"\Omega": "Ω",
        r"\omega": "ω",
        r"\Sigma": "Σ",
        r"\sigma": "σ",
    }
    for key, value in replacements.items():
        s = s.replace(key, value)
    s = re.sub(r"\s+", "", s)
    return s


def oralize_fragment(text: str) -> str:
    s = strip_outer_latex_wrappers(text.strip())
    try:
        return oralize_latex(s)
    except Exception:
        return _fallback_oralize_plain_text(s)


def oralize_bound(text: str) -> str:
    s = strip_outer_latex_wrappers(text.strip())
    if s in {r"\pi", r"\infty", r"\Omega", r"\Gamma", r"\omega"}:
        return speak_atom_text(s)
    try:
        return oralize_latex(s)
    except Exception:
        return _fallback_oralize_plain_text(s)


def try_render_derivative_composite(latex: str) -> Optional[str]:
    DERIV_FRACTION_PATTERN = re.compile(
        r"\\frac\s*\{d\s*([^{}]+)\}\s*\{d\s*([^{}]+)\}"
    )
    if r"\frac" not in latex or r"\partial" in latex:
        return None

    def repl(m: re.Match) -> str:
        body = oralize_fragment(m.group(1).strip())
        var = oralize_fragment(m.group(2).strip())
        return f"{body}对{var}的导数"

    replaced = DERIV_FRACTION_PATTERN.sub(repl, latex)
    if replaced == latex:
        return None

    replaced = re.sub(r"\s*\+\s*", "加", replaced)
    replaced = re.sub(r"\s*-\s*", "减", replaced)
    replaced = re.sub(r"\s+", "", replaced)
    return replaced


def try_render_partial_composite(latex: str) -> Optional[str]:
    PARTIAL_FRACTION_PATTERN = re.compile(
        r"\\frac\s*\{\\partial\s*([^{}]+)\}\s*\{\\partial\s*([^{}]+)\}"
    )

    if r"\frac" not in latex or r"\partial" not in latex:
        return None

    def repl(m: re.Match) -> str:
        body = oralize_fragment(m.group(1).strip())
        var = oralize_fragment(m.group(2).strip())
        return f"{body}对{var}的偏导"

    replaced = PARTIAL_FRACTION_PATTERN.sub(repl, latex)

    if replaced == latex:
        return None

    # 把剩余运算符口播化
    replaced = re.sub(r"\s*\+\s*", "加", replaced)
    replaced = re.sub(r"\s*-\s*", "减", replaced)
    replaced = re.sub(r"\s+", "", replaced)
    return replaced


def try_render_greek_symbol(latex: str) -> Optional[str]:
    mapping = {
        r"\Omega": "欧米伽",
        r"\omega": "欧米伽",
        r"\Gamma": "伽马",
        r"\gamma": "伽马",
        r"\Sigma": "西格玛",
        r"\sigma": "西格玛",
        r"\pi": "派",
    }
    return mapping.get(latex.strip())


def try_render_limit(latex: str) -> Optional[str]:
    m = re.fullmatch(r"\\lim_\{([^{}]+)\\to([^{}]+)\}(.+)", latex)
    if not m:
        return None
    var = speak_atom_text(m.group(1))
    target = speak_atom_text(m.group(2))
    body_text = oralize_fragment(m.group(3).strip())
    return f"当{var}趋近于{target}时，{body_text}"


def try_render_cases(latex: str) -> Optional[str]:
    m = re.search(r"\\begin\{cases\}(.*?)\\end\{cases\}", latex, flags=re.DOTALL)
    if not m:
        return None
    rows = [row.strip() for row in re.split(r"\\\\", m.group(1).strip()) if row.strip()]
    spoken_rows: list[str] = []
    for row in rows:
        parts = [part.strip() for part in row.split("&") if part.strip()]
        if len(parts) == 2:
            spoken_rows.append(
                f"当{oralize_fragment(parts[1])}时，函数值是{oralize_fragment(parts[0])}"
            )
        else:
            spoken_rows.append(oralize_fragment(row))
    return "分段函数。" + "；".join(spoken_rows)


def try_render_matrix(latex: str) -> Optional[str]:
    m = re.search(r"\\begin\{([pbvBV]?matrix)\}(.*?)\\end\{\1\}", latex, flags=re.DOTALL)
    if not m:
        return None
    matrix_type = m.group(1)
    rows = [row.strip() for row in re.split(r"\\\\", m.group(2).strip()) if row.strip()]
    parsed_rows = [[oralize_fragment(col.strip()) for col in row.split("&")] for row in rows]
    row_n = len(parsed_rows)
    col_n = max((len(row) for row in parsed_rows), default=0)
    prefix = f"这是一个{row_n}行{col_n}列行列式" if matrix_type in {"vmatrix",
                                                                    "Vmatrix"} else f"这是一个{row_n}行{col_n}列矩阵"
    parts = [prefix]
    for index, row in enumerate(parsed_rows, start=1):
        parts.append(f"第{index}行是" + "，".join(row))
    return "。".join(parts)


def try_render_integral(latex: str) -> Optional[str]:
    m = re.fullmatch(r"\\oint_(?:\{([^{}]+)\}|([A-Za-z]+|\\[A-Za-z]+))\s*(.+)", latex)
    if m:
        contour = normalize_region_name((m.group(1) or m.group(2)).strip())
        body = m.group(3).strip()
        m2 = re.fullmatch(r"(.+?)dx\s*\+\s*(.+?)dy", body)
        if m2:
            return (
                f"沿{contour}的闭合曲线积分，第一部分是{oralize_fragment(m2.group(1).strip())}对x积分，"
                f"第二部分是{oralize_fragment(m2.group(2).strip())}对y积分"
            )
        if body.endswith("dx"):
            return f"沿{contour}的闭合曲线积分，{oralize_fragment(body[:-2].strip())}对x积分"
        return f"沿{contour}的闭合曲线积分，{oralize_fragment(body)}"

    m = re.fullmatch(r"\\int_(?:\{([^{}]+)\}|([A-Za-z]+|\\[A-Za-z]+))\s*(.+)\s*ds", latex)
    if m:
        contour = normalize_region_name((m.group(1) or m.group(2)).strip())
        return f"沿{contour}的曲线积分，{oralize_fragment(m.group(3).strip())}对弧长s积分"

    m = re.fullmatch(r"\\int_\{?(.+?)\}?\^\{?(.+?)\}?\s*(.+)", latex)
    if m:
        lower = oralize_bound(m.group(1).strip())
        upper = oralize_bound(m.group(2).strip())
        body = m.group(3).strip()
        if body.endswith("dx"):
            return f"从{lower}到{upper}，{oralize_fragment(body[:-2].strip())}对x的定积分"
        if body.endswith("dy"):
            return f"从{lower}到{upper}，{oralize_fragment(body[:-2].strip())}对y的定积分"
        if body.endswith("dz"):
            return f"从{lower}到{upper}，{oralize_fragment(body[:-2].strip())}对z的定积分"
        return f"从{lower}到{upper}的定积分，积分函数是{oralize_fragment(body)}"

    m = re.fullmatch(r"\\iint_(?:\{([^{}]+)\}|([A-Za-z]+|\\[A-Za-z]+))\s*(.+)", latex)
    if m:
        region = normalize_region_name((m.group(1) or m.group(2)).strip())
        body = m.group(3).strip()
        if body.endswith("dxdy"):
            return f"在{region}上，{oralize_fragment(body[:-4].strip())}的二重积分，d x d y"
        if body.endswith("dydx"):
            return f"在{region}上，{oralize_fragment(body[:-4].strip())}的二重积分，d y d x"
        return f"在{region}上的二重积分，积分函数是{oralize_fragment(body)}"

    m = re.fullmatch(r"\\iiint_(?:\{([^{}]+)\}|([A-Za-z]+|\\[A-Za-z]+))\s*(.+)", latex)
    if m:
        region = normalize_region_name((m.group(1) or m.group(2)).strip())
        body = m.group(3).strip()
        if body.endswith("dxdydz"):
            return f"在{region}上，{oralize_fragment(body[:-6].strip())}的三重积分，d x d y d z"
        if body.endswith("dzdydx"):
            return f"在{region}上，{oralize_fragment(body[:-6].strip())}的三重积分，d z d y d x"
        return f"在{region}上的三重积分，积分函数是{oralize_fragment(body)}"
    return None


def try_render_derivative(latex: str) -> Optional[str]:
    m = re.fullmatch(
        r"\\frac\s*\{d\^\{?([0-9]+)\}?\s+([^{}]+)\}\s*\{d\s*([A-Za-z]+)\^\{?([0-9]+)\}?\}",
        latex,
    )
    if m and m.group(1) == m.group(4):
        return f"{oralize_fragment(m.group(2).strip())}对{oralize_fragment(m.group(3).strip())}的{m.group(1)}阶导数"

    m = re.fullmatch(r"\\frac\s*\{d\}\s*\{d\s*([A-Za-z]+)\}\s*(.+)", latex)
    if m:
        return f"{oralize_fragment(m.group(2).strip())}对{oralize_fragment(m.group(1).strip())}的导数"

    m = re.fullmatch(r"\\frac\s*\{d\s*([^{}]+)\}\s*\{d\s*([^{}]+)\}", latex)
    if m:
        return f"{oralize_fragment(m.group(1).strip())}对{oralize_fragment(m.group(2).strip())}的导数"

    for suffix, order in (("'''", "三"), ("''", "二"), ("'", "一")):
        m = re.fullmatch(rf"([A-Za-z]+){re.escape(suffix)}\(([^()]*)\)", latex)
        if m:
            return f"{m.group(1)}关于{oralize_fragment(m.group(2).strip())}的{order}阶导数"
    return None


def try_render_partial(latex: str) -> Optional[str]:
    m = re.fullmatch(
        r"\\frac\s*\{\\partial\^\{?([0-9]+)\}?\s+([^{}]+)\}\s*\{\\partial\s*([A-Za-z]+)\s*\\partial\s*([A-Za-z]+)\}",
        latex,
    )
    if m and m.group(1) == "2":
        return f"{oralize_fragment(m.group(2).strip())}先对{oralize_fragment(m.group(3).strip())}再对{oralize_fragment(m.group(4).strip())}的二阶混合偏导"

    m = re.fullmatch(
        r"\\frac\s*\{\\partial\^\{?([0-9]+)\}?\s+([^{}]+)\}\s*\{\\partial\s*([A-Za-z]+)\^\{?([0-9]+)\}?\s*\\partial\s*([A-Za-z]+)\}",
        latex,
    )
    if m:
        return (
            f"{oralize_fragment(m.group(2).strip())}对{oralize_fragment(m.group(3).strip())}的{m.group(4).strip()}阶，"
            f"再对{oralize_fragment(m.group(5).strip())}的一阶，共{m.group(1)}阶偏导"
        )

    m = re.fullmatch(
        r"\\frac\s*\{\\partial\^\{?([0-9]+)\}?\s+([^{}]+)\}\s*\{\\partial\s*([A-Za-z]+)\^\{?([0-9]+)\}?\}",
        latex,
    )
    if m and m.group(1) == m.group(4):
        return f"{oralize_fragment(m.group(2).strip())}对{oralize_fragment(m.group(3).strip())}的{m.group(1)}阶偏导"

    m = re.fullmatch(r"\\frac\s*\{\\partial\s*([^{}]+)\}\s*\{\\partial\s*([^{}]+)\}", latex)
    if m:
        return f"{oralize_fragment(m.group(1).strip())}对{oralize_fragment(m.group(2).strip())}的偏导"

    m = re.fullmatch(r"\\frac\s*\{\\partial\}\s*\{\\partial\s*([A-Za-z]+)\}\s*(.+)", latex)
    if m:
        return f"{oralize_fragment(m.group(2).strip())}对{oralize_fragment(m.group(1).strip())}的偏导"
    return None


def oralize_inline_formula(text: str) -> str:
    s = strip_outer_latex_wrappers(text.strip())
    s = re.sub(
        r"([A-Za-z]+)_\{([^{}]+)\}",
        lambda m: f"{m.group(1)}下标{oralize_fragment(m.group(2).strip())}",
        s,
    )
    s = re.sub(
        r"([A-Za-z]+)_([A-Za-z0-9]+)",
        lambda m: f"{m.group(1)}下标{m.group(2)}",
        s,
    )
    try:
        return oralize_latex(s)
    except Exception:
        return _fallback_oralize_plain_text(s)


def _fallback_oralize_plain_text(text: str) -> str:
    s = normalize_latex_for_parser(strip_outer_latex_wrappers(text))
    if not s:
        return s
    s = _replace_fraction_fallback(s)
    s = _replace_sqrt_fallback(s)
    s = _replace_superscript_fallback(s)
    s = _replace_subscript_fallback(s)
    s = _replace_symbol_tokens_fallback(s)
    s = s.replace("{", " ").replace("}", " ").replace("&", " ")
    s = s.replace("\\", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _replace_fraction_fallback(text: str) -> str:
    pattern = re.compile(r"\\frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}")
    while True:
        updated = pattern.sub(
            lambda
                m: f"{_fallback_oralize_plain_text(m.group(2).strip())}分之{_fallback_oralize_plain_text(m.group(1).strip())}",
            text,
        )
        if updated == text:
            return updated
        text = updated


def _replace_sqrt_fallback(text: str) -> str:
    pattern = re.compile(r"\\sqrt\s*\{([^{}]+)\}")
    while True:
        updated = pattern.sub(
            lambda m: f"根号下{_fallback_oralize_plain_text(m.group(1).strip())}",
            text,
        )
        if updated == text:
            return updated
        text = updated


def _replace_superscript_fallback(text: str) -> str:
    text = re.sub(r"([A-Za-z0-9\)\]])\^\{2\}", r"\1的平方", text)
    text = re.sub(r"([A-Za-z0-9\)\]])\^\{3\}", r"\1的立方", text)
    text = re.sub(
        r"([A-Za-z0-9\)\]])\^\{([^{}]+)\}",
        lambda m: f"{m.group(1)}的{_fallback_oralize_plain_text(m.group(2).strip())}次方",
        text,
    )
    text = re.sub(r"([A-Za-z0-9\)\]])\^2\b", r"\1的平方", text)
    text = re.sub(r"([A-Za-z0-9\)\]])\^3\b", r"\1的立方", text)
    text = re.sub(r"([A-Za-z0-9\)\]])\^([A-Za-z0-9]+)", lambda m: f"{m.group(1)}的{m.group(2)}次方", text)
    return text


def _replace_subscript_fallback(text: str) -> str:
    text = re.sub(
        r"([A-Za-z]+)_\{([^{}]+)\}",
        lambda m: f"{m.group(1)}下标{_fallback_oralize_plain_text(m.group(2).strip())}",
        text,
    )
    text = re.sub(r"([A-Za-z]+)_([A-Za-z0-9]+)", lambda m: f"{m.group(1)}下标{m.group(2)}", text)
    return text


def _replace_symbol_tokens_fallback(text: str) -> str:
    replacements = {
        r"\to": "趋近于",
        r"\ge": "大于等于",
        r"\geq": "大于等于",
        r"\le": "小于等于",
        r"\leq": "小于等于",
        r"\neq": "不等于",
        r"\times": "乘",
        r"\cdot": "乘",
        r"\sin": "正弦",
        r"\cos": "余弦",
        r"\tan": "正切",
        r"\cot": "余切",
        r"\ln": "自然对数",
        r"\infty": "无穷大",
        r"\pi": "派",
        r"\alpha": "阿尔法",
        r"\beta": "贝塔",
        r"\gamma": "伽马",
        r"\theta": "西塔",
        "=": "等于",
        "+": "加",
        "-": "减",
    }
    updated = text
    for key, value in replacements.items():
        updated = updated.replace(key, value)
    return updated


def try_render_sumprod(latex: str) -> Optional[str]:
    m = re.fullmatch(r"\\sum_\{([^{}]+)=([^{}]+)\}\^\{([^{}]+)\}\s*(.+)", latex)
    if m:
        return (
            f"从{oralize_fragment(m.group(1).strip())}等于{oralize_fragment(m.group(2).strip())}"
            f"到{oralize_fragment(m.group(3).strip())}求和，求和项是{oralize_inline_formula(m.group(4).strip())}"
        )
    m = re.fullmatch(r"\\prod_\{([^{}]+)=([^{}]+)\}\^\{([^{}]+)\}\s*(.+)", latex)
    if m:
        return (
            f"从{oralize_fragment(m.group(1).strip())}等于{oralize_fragment(m.group(2).strip())}"
            f"到{oralize_fragment(m.group(3).strip())}连乘，连乘项是{oralize_inline_formula(m.group(4).strip())}"
        )
    return None


def try_render_subscript_only(latex: str) -> Optional[str]:
    s = latex.strip()
    if s.startswith((
            r"\lim", r"\int", r"\iint", r"\iiint", r"\oint", r"\sum", r"\prod", r"\frac", r"\partial", r"\sqrt",
            r"\begin")):
        return None
    m = re.fullmatch(r"([A-Za-z]+)_\{([^{}]+)\}", s)
    if m:
        return f"{m.group(1)}下标{speak_atom_text(m.group(2).strip().replace(',', '逗号'))}"
    m = re.fullmatch(r"([A-Za-z]+)_([A-Za-z0-9]+)", s)
    if m:
        return f"{m.group(1)}下标{m.group(2)}"
    if "_" in s:
        updated = re.sub(
            r"([A-Za-z]+)_\{([^{}]+)\}",
            lambda m: f"{m.group(1)}下标{speak_atom_text(m.group(2).strip().replace(',', '逗号'))}",
            s,
        )
        updated = re.sub(
            r"([A-Za-z]+)_([A-Za-z0-9]+)",
            lambda m: f"{m.group(1)}下标{m.group(2)}",
            updated,
        )
        try:
            return oralize_latex(updated) if updated != latex else updated
        except Exception:
            return updated
    return None


def is_negative_expr(expr) -> bool:
    if expr.is_number and expr.is_negative:
        return True
    if isinstance(expr, Mul) and expr.args and expr.args[0] == -1:
        return True
    return False


def speak_relational(expr: Relational) -> str:
    op_map = {"<": "小于", ">": "大于", "<=": "小于等于", ">=": "大于等于", "=": "等于", "==": "等于", "!=": "不等于"}
    return f"{speak_expr(expr.lhs)}{op_map.get(expr.rel_op, expr.rel_op)}{speak_expr(expr.rhs)}"


def join_add_terms(expr: Add) -> str:
    parts: list[str] = []
    for index, arg in enumerate(expr.args):
        text = speak_expr(arg)
        if index == 0:
            parts.append(text)
        elif is_negative_expr(arg):
            parts.append(f"减{speak_expr(-arg)}")
        else:
            parts.append(f"加{text}")
    return "".join(parts)


def speak_symbol_name(name: str) -> str:
    mapping = {
        "E": "e",
        "pi": "π",
        "oo": "无穷大",
        "Omega": "欧米伽",
        "omega": "欧米伽",
        "Gamma": "伽马",
        "gamma": "伽马",
        "Sigma": "西格玛",
        "sigma": "西格玛",
    }
    if name in mapping:
        return mapping[name]
    m = re.fullmatch(r"([A-Za-z]+)_\{([^{}]+)\}", name)
    if m:
        return f"{m.group(1)}下标{oralize_fragment(m.group(2).strip())}"
    m = re.fullmatch(r"([A-Za-z]+)_([A-Za-z0-9]+)", name)
    if m:
        return f"{m.group(1)}下标{m.group(2)}"
    return speak_atom_text(name)


def speak_power(base_text: str, exp) -> str:
    exp = normalize_exponent_for_speech(exp)

    if exp == Integer(2):
        return f"{base_text}的平方"

    if exp == Integer(3):
        return f"{base_text}的3次方"

    if getattr(exp, "is_Rational", False):
        return f"{base_text}的{speak_rational_exponent(exp)}次方"

    return f"{base_text}的{speak_expr(exp)}次方"


def maybe_reorder_linear_text(text: str) -> str:
    text = re.sub(r"^负1加([A-Za-z\u4e00-\u9fa5]+)$", r"\1减1", text)
    text = re.sub(r"^1加([A-Za-z\u4e00-\u9fa5]+)$", r"\1加1", text)
    return text


def speak_fraction(numer, denom) -> str:
    num_text = maybe_reorder_linear_text(speak_expr(numer))
    den_text = maybe_reorder_linear_text(speak_expr(denom))
    if getattr(numer, "is_Integer", False) and getattr(denom, "is_Integer", False):
        return f"{den_text}分之{num_text}"
    if getattr(denom, "is_Symbol", False) or getattr(denom, "is_Integer", False):
        return f"{den_text}分之{num_text}"
    if isinstance(denom, Mul) and not any(isinstance(arg, Add) for arg in denom.args):
        return f"{den_text}分之{num_text}"
    return f"{num_text}除以{den_text}"


def speak_mul(expr: Mul) -> str:
    if expr.args and expr.args[0] == -1:
        if len(expr.args) == 2:
            return f"负{speak_expr(expr.args[1])}"
        return f"负{speak_expr(Mul(*expr.args[1:]))}"
    parts = [speak_expr(arg) for arg in expr.args]
    if len(parts) == 2:
        return f"{parts[0]}{parts[1]}"
    return "乘".join(parts)


def speak_function(expr) -> str:
    name = expr.func.__name__
    args = expr.args
    fn_map = {
        "sin": "sine ",
        "cos": "cosine ",
        "tan": "tangent ",
        "cot": "co-tangent ",
        "sec": "secant ",
        "csc": "co-secant ",
        "log": "log ",
        "exp": "e ",
    }
    zh_name = fn_map.get(name, name)
    if name == "log" and len(args) == 2:
        arg_text = speak_expr(args[0])
        base_text = speak_expr(args[1])
        if base_text in {"E", "e"}:
            return f"自然对数{arg_text}"
        return f"以{base_text}为底的对数{arg_text}"
    if len(args) == 1:
        return f"{zh_name}{speak_expr(args[0])}"
    return f"{zh_name}（{'，'.join(speak_expr(arg) for arg in args)}）"


def speak_applied_undef(expr: AppliedUndef) -> str:
    return f"{expr.func.__name__}（{'，'.join(speak_expr(arg) for arg in expr.args)}）"


def speak_eq(expr: Eq) -> str:
    return f"{speak_expr(expr.lhs)}等于{speak_expr(expr.rhs)}"


def try_speak_fraction(expr) -> Optional[str]:
    # Pow 不在这里拆成分数，保留指数语义
    if isinstance(expr, (Add, Eq, Relational, Pow)):
        return None

    if not hasattr(expr, "as_numer_denom"):
        return None

    numer, denom = expr.as_numer_denom()
    if denom == 1:
        return None

    return speak_fraction(numer, denom)


def zh_num(n: int) -> str:
    mapping = {
        0: "零",
        1: "一",
        2: "二",
        3: "三",
        4: "四",
        5: "五",
        6: "六",
        7: "七",
        8: "八",
        9: "九",
        10: "十",
    }
    return mapping.get(n, str(n))


def speak_rational_exponent(exp) -> str:
    exp = Rational(exp)
    p = int(exp.p)
    q = int(exp.q)

    sign = "负" if p < 0 else ""
    p = abs(p)

    if q == 1:
        return f"{sign}{zh_num(p)}"

    if p == 1:
        return f"{sign}{zh_num(q)}分之一"

    return f"{sign}{zh_num(q)}分之{zh_num(p)}"


def speak_expr(expr) -> str:
    if isinstance(expr, Relational):
        return speak_relational(expr)
    if isinstance(expr, Eq):
        return speak_eq(expr)
    if isinstance(expr, AppliedUndef):
        return speak_applied_undef(expr)
    if isinstance(expr, Symbol):
        return speak_symbol_name(str(expr))
    if getattr(expr, "is_Integer", False):
        value = int(expr)
        return f"负{abs(value)}" if value < 0 else str(value)
    if getattr(expr, "is_Number", False):
        try:
            if float(expr) < 0:
                return f"负{str(expr)[1:]}"
        except Exception:
            pass
        return str(expr)

    if isinstance(expr, Add):
        return join_add_terms(expr)

    # Pow 必须先于 fraction
    if isinstance(expr, Pow):
        base, exp = expr.args

        if exp == Rational(1, 2):
            return f"根号下{speak_expr(base)}"

        base_text = speak_expr(base)
        return speak_power(base_text, exp)

    fraction_text = try_speak_fraction(expr)
    if fraction_text is not None:
        return fraction_text

    if isinstance(expr, Mul):
        return speak_mul(expr)
    if isinstance(expr, Function):
        return speak_function(expr)
    return str(expr)


def oralize_latex_with_trace(latex: str) -> tuple[str, dict[str, Any]]:
    normalized = normalize_latex_for_parser(latex)
    for fn in (
            try_render_greek_symbol,
            try_render_cases,
            try_render_matrix,
            try_render_derivative_composite,
            try_render_derivative,
            try_render_partial_composite,  # 新增，放在单个偏导规则前面
            try_render_partial,
            try_render_sumprod,
            try_render_integral,
            try_render_limit,
            try_render_subscript_only,
    ):
        result = fn(normalized)
        if result:
            return result, {
                "backend": "math_latex_oralizer",
                "normalized_text": normalized,
                "mode": "rule",
                "fallback_used": False,
            }
    try:
        return speak_expr(parse_latex(normalized, backend="antlr")), {
            "backend": "math_latex_oralizer",
            "normalized_text": normalized,
            "mode": "sympy_ast",
            "fallback_used": False,
        }
    except Exception as exc:
        return _fallback_oralize_plain_text(normalized), {
            "backend": "math_latex_oralizer",
            "normalized_text": normalized,
            "mode": "fallback",
            "fallback_used": True,
            "fallback_reason": f"{type(exc).__name__}: {exc}",
        }


def oralize_latex(latex: str) -> str:
    spoken, _trace = oralize_latex_with_trace(latex)
    return spoken


__all__ = [
    "normalize_latex_for_parser",
    "oralize_latex",
    "oralize_latex_with_trace",
    "strip_outer_latex_wrappers",
]
