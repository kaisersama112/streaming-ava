"""SymPy-backed LaTeX oralizer migrated from demo_parse_latex.py."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from sympy.parsing.latex import parse_latex
from sympy import Integer, Rational, Symbol, Eq, Add, Mul, Pow, Function
from sympy.core.function import AppliedUndef
from sympy.core.relational import Relational

from .latex_speech_config import (
    FUNCTION_SPOKEN,
    GREEK_SPOKEN,
    REL_OP_SPOKEN,
    REPLACEMENTS,
)


# =========================
# 0. preprocess / normalize
# =========================


def is_command_optional_bracket(text: str, index: int) -> bool:
    """判断方括号是否属于 LaTeX 命令的可选参数。"""
    cursor = index - 1
    while cursor >= 0 and text[cursor].isspace():
        cursor -= 1

    end = cursor
    while cursor >= 0 and text[cursor].isalpha():
        cursor -= 1

    return end >= 0 and cursor >= 0 and text[cursor] == "\\"


def normalize_grouping_brackets(text: str) -> str:
    """把纯分组用途的方括号归一化成圆括号。"""
    chars = list(text)
    stack: list[tuple[int, bool]] = []
    pairs: list[tuple[int, int]] = []

    for index, char in enumerate(chars):
        if char == "[":
            stack.append((index, not is_command_optional_bracket(text, index)))
        elif char == "]" and stack:
            open_index, replaceable = stack.pop()
            if replaceable:
                pairs.append((open_index, index))

    for open_index, close_index in pairs:
        chars[open_index] = "("
        chars[close_index] = ")"

    return "".join(chars)


def normalize_latex_for_parser(text: str) -> str:
    """在进入解析器前清理排版命令并统一常见写法。"""
    s = text.strip()
    s = s.replace(r"\left", "").replace(r"\right", "")
    s = normalize_grouping_brackets(s)

    s = re.sub(
        r"\\(sin|cos|tan)\s+([A-Za-z])\s*\^\s*(\{[^{}]+\}|[A-Za-z0-9]+)",
        r"\\\1(\2^\3)",
        s,
    )
    s = re.sub(
        r"\\(sin|cos|tan)\s+([A-Za-z0-9]+)",
        r"\\\1(\2)",
        s,
    )

    s = re.sub(r"^\$\$(.*)\$\$$", r"\1", s, flags=re.DOTALL)
    s = re.sub(r"^\$(.*)\$$", r"\1", s, flags=re.DOTALL)

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
    s = re.sub(r"\\mathop\s*\{\s*\\lim\s*\}", r"\\lim", s)

    s = re.sub(r"\\,|\\;|\\!|\\quad|\\qquad", " ", s)
    s = re.sub(r"\\mathrm\s*\{\s*e\s*\}", "e", s)
    s = re.sub(r"\\mathrm\s*\{\s*d\s*\}", "d", s)
    s = re.sub(r"\bd\s*x\b", "dx", s)
    s = re.sub(r"\bd\s*y\b", "dy", s)
    s = re.sub(r"\bd\s*z\b", "dz", s)
    s = re.sub(r"=\s*$", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s



# =========================
# 1. semantic IR
# =========================


@dataclass(frozen=True)
class SemanticIR:
    kind: str


@dataclass(frozen=True)
class ExprIR(SemanticIR):
    latex: str
    expr: object


@dataclass(frozen=True)
class LimitIR(SemanticIR):
    variable: str
    target: str
    body: str


@dataclass(frozen=True)
class DerivativeIR(SemanticIR):
    body: str
    variable: str
    order: int = 1
    partial: bool = False
    mixed: tuple[tuple[str, int], ...] = ()
    prime_style: bool = False
    function_name: Optional[str] = None
    function_arg: Optional[str] = None


@dataclass(frozen=True)
class SumProdIR(SemanticIR):
    op: str
    variable: str
    lower: str
    upper: str
    body: str


@dataclass(frozen=True)
class IntegralIR(SemanticIR):
    op: str
    region: Optional[str] = None
    lower: Optional[str] = None
    upper: Optional[str] = None
    body: str = ""
    differentials: tuple[str, ...] = ()


@dataclass(frozen=True)
class CasesIR(SemanticIR):
    rows: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class MatrixIR(SemanticIR):
    matrix_type: str
    rows: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class SymbolIR(SemanticIR):
    name: str


@dataclass(frozen=True)
class BoxedIR(SemanticIR):
    body: str


@dataclass(frozen=True)
class AssignmentIR(SemanticIR):
    lhs: str
    rhs: str


@dataclass(frozen=True)
class SubscriptIR(SemanticIR):
    base: str
    subscript: str


@dataclass(frozen=True)
class AnnotatedIR(SemanticIR):
    body: SemanticIR
    notes: tuple[str, ...]


# =========================
# 2. helpers
# =========================


def split_top_level(text: str, sep: str) -> list[str]:
    """按顶层分隔符拆分字符串，忽略括号内部内容。"""
    parts: list[str] = []
    depth_brace = depth_paren = depth_bracket = 0
    start = 0
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "{":
            depth_brace += 1
        elif ch == "}":
            depth_brace -= 1
        elif ch == "(":
            depth_paren += 1
        elif ch == ")":
            depth_paren -= 1
        elif ch == "[":
            depth_bracket += 1
        elif ch == "]":
            depth_bracket -= 1
        elif text.startswith(sep, i) and depth_brace == depth_paren == depth_bracket == 0:
            parts.append(text[start:i])
            start = i + len(sep)
            i = start
            continue
        i += 1
    parts.append(text[start:])
    return parts


def split_diff_suffix(text: str) -> tuple[str, tuple[str, ...]]:
    """从表达式末尾提取 dx、dy 这类微分后缀。"""
    rest = text.strip()
    match = re.search(r"\s*((?:d[A-Za-z]\s*)+)$", rest)
    if not match:
        return rest, ()
    suffix = match.group(1)
    diffs = tuple(re.findall(r"d([A-Za-z])", suffix))
    return rest[:match.start()].rstrip(), diffs


def extract_trailing_text_annotations(text: str) -> tuple[str, tuple[str, ...]]:
    """提取公式尾部的 \\text 注释块。"""
    rest = text.strip()
    notes: list[str] = []

    while True:
        match = re.search(r"\s*\\text\{([^{}]*)\}\s*$", rest)
        if not match:
            break
        notes.insert(0, match.group(1).strip())
        rest = rest[:match.start()].rstrip()

    return rest, tuple(notes)


def normalize_region_name(raw: str) -> str:
    """把区域名里的希腊字母替换成可口播字符。"""
    s = raw.strip()
    for source, target in GREEK_SPOKEN.items():
        s = s.replace(source, target)
    return s


def speak_atom_text(text: str) -> str:
    """口播最小文本单元，如趋近符号和关系符。"""
    s = text.strip()
    for source, target in GREEK_SPOKEN.items():
        s = s.replace(source, target)
    for source, target in REPLACEMENTS.items():
        s = s.replace(source, target)
    return re.sub(r"\s+", "", s)





def oralize_bound(text: str) -> str:
    """口播积分上下限或极限目标。"""
    stripped = text.strip()
    if stripped in GREEK_SPOKEN:
        return GREEK_SPOKEN[stripped]
    return oralize_latex(stripped)


def oralize_inline_formula(text: str) -> str:
    """优先按完整公式口播，失败时退化为行内替换。"""
    s = text.strip()
    try:
        return oralize_latex(s)
    except Exception:
        pass

    s = re.sub(
        r"([A-Za-z]+)_\{([^{}]+)\}",
        lambda m: f"{m.group(1)}下标{m.group(2).strip().replace(',', '逗号').replace('*', '')}",
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
        return s


def speak_symbol_name(name: str) -> str:
    """把符号名转成更自然的中文口播形式。"""
    m = re.fullmatch(r"([A-Za-z]+)_\{(.+)\}", name)
    if m:
        base = m.group(1)
        sub = m.group(2).replace("*", "")
        sub = sub.replace(",", "逗号")
        return f"{base}下标{oralize_inline_formula(sub)}"

    m = re.fullmatch(r"([A-Za-z]+)_([A-Za-z0-9]+)", name)
    if m:
        return f"{m.group(1)}下标{m.group(2)}"

    return name


def strip_outer_parens(text: str) -> str:
    """安全去掉最外层一对完整包裹的圆括号。"""
    s = text.strip()
    while s.startswith("(") and s.endswith(")"):
        depth = 0
        balanced = True
        for index, char in enumerate(s):
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0 and index != len(s) - 1:
                    balanced = False
                    break
        if balanced:
            s = s[1:-1].strip()
        else:
            break
    return s


# =========================
# 3. syntax -> semantic IR
# =========================


def try_build_limit_ir(latex: str) -> Optional[LimitIR]:
    """识别极限结构并构造成 LimitIR。"""
    m = re.fullmatch(r"\\lim_\{([^{}]+)\\to([^{}]+)\}(.+)", latex)
    if not m:
        return None
    return LimitIR(
        kind="limit",
        variable=m.group(1).strip(),
        target=m.group(2).strip(),
        body=m.group(3).strip(),
    )


def try_build_assignment_ir(latex: str) -> Optional[AssignmentIR]:
    """识别顶层等号表达式并构造成赋值 IR。"""
    if latex.startswith(r"\begin{"):
        return None
    parts = split_top_level(latex, "=")
    if len(parts) != 2:
        return None
    lhs = parts[0].strip()
    rhs = parts[1].strip()
    if not lhs or not rhs:
        return None
    return AssignmentIR(kind="assignment", lhs=lhs, rhs=rhs)


def try_build_subscript_ir(latex: str) -> Optional[SubscriptIR]:
    """识别纯下标表达式并构造成 SubscriptIR。"""
    m = re.fullmatch(r"([A-Za-z]+)_\{([^{}]+)\}", latex)
    if m:
        return SubscriptIR(kind="subscript", base=m.group(1), subscript=m.group(2).strip())
    m = re.fullmatch(r"([A-Za-z]+)_([A-Za-z0-9]+)", latex)
    if m:
        return SubscriptIR(kind="subscript", base=m.group(1), subscript=m.group(2).strip())
    return None


def try_build_cases_ir(latex: str) -> Optional[CasesIR]:
    """识别 cases 环境并构造成分段函数 IR。"""
    m = re.search(r"\\begin\{cases\}(.*?)\\end\{cases\}", latex, flags=re.DOTALL)
    if not m:
        return None
    rows = [r.strip() for r in re.split(r"\\\\", m.group(1).strip()) if r.strip()]
    parsed: list[tuple[str, str]] = []
    for row in rows:
        parts = [p.strip() for p in row.split("&") if p.strip()]
        if len(parts) == 2:
            parsed.append((parts[0], parts[1]))
    if not parsed:
        return None
    return CasesIR(kind="cases", rows=tuple(parsed))


def try_build_matrix_ir(latex: str) -> Optional[MatrixIR]:
    """识别常见矩阵环境并构造成 MatrixIR。"""
    m = re.search(r"\\begin\{([A-Za-z]+matrix)\}(.*?)\\end\{\1\}", latex, flags=re.DOTALL)
    if not m:
        return None
    rows = [r.strip() for r in re.split(r"\\\\", m.group(2).strip()) if r.strip()]
    parsed_rows = tuple(tuple(cell.strip() for cell in row.split("&")) for row in rows)
    return MatrixIR(kind="matrix", matrix_type=m.group(1), rows=parsed_rows)


def try_build_greek_symbol_ir(latex: str) -> Optional[SymbolIR]:
    """识别单独出现的希腊字母符号。"""
    if latex.strip() in GREEK_SPOKEN:
        return SymbolIR(kind="symbol", name=latex.strip())
    return None


def try_build_boxed_ir(latex: str) -> Optional[BoxedIR]:
    """识别 boxed 包装结构。"""
    m = re.fullmatch(r"\\boxed\{(.+)\}", latex)
    if not m:
        return None
    return BoxedIR(kind="boxed", body=m.group(1).strip())


def try_build_sumprod_ir(latex: str) -> Optional[SumProdIR]:
    """识别求和与连乘结构。"""
    m = re.fullmatch(r"\\(sum|prod)_\{([^{}]+)=([^{}]+)\}\^\{([^{}]+)\}\s*(.+)", latex)
    if not m:
        return None
    return SumProdIR(
        kind="sumprod",
        op=m.group(1),
        variable=m.group(2).strip(),
        lower=m.group(3).strip(),
        upper=m.group(4).strip(),
        body=m.group(5).strip(),
    )


def try_build_integral_ir(latex: str) -> Optional[IntegralIR]:
    """识别单积分、重积分与曲线积分结构。"""
    m = re.fullmatch(r"\\oint_(?:\{([^{}]+)\}|([A-Za-z]+|\\[A-Za-z]+))\s*(.+)", latex)
    if m:
        region = (m.group(1) or m.group(2)).strip()
        body = m.group(3).strip()
        pair = re.fullmatch(r"(.+?)d([A-Za-z])\s*\+\s*(.+?)d([A-Za-z])", body)
        if pair:
            return IntegralIR(
                kind="integral",
                op="oint",
                region=region,
                body=body,
                differentials=(pair.group(2), pair.group(4)),
            )
        body, diffs = split_diff_suffix(body)
        return IntegralIR(kind="integral", op="oint", region=region, body=body, differentials=diffs)

    m = re.fullmatch(r"\\int_(?:\{([^{}]+)\}|([A-Za-z]+|\\[A-Za-z]+))\s*(.+)\s*ds", latex)
    if m:
        region = (m.group(1) or m.group(2)).strip()
        return IntegralIR(kind="integral", op="curve", region=region, body=m.group(3).strip(), differentials=("s",))

    m = re.fullmatch(
        r"\\int_(?:\{([^{}]+)\}|([^\s^]+))\^(?:\{([^{}]+)\}|([^\s]+))\s*(.+)",
        latex,
    )
    if m:
        body, diffs = split_diff_suffix(m.group(5).strip())
        return IntegralIR(
            kind="integral",
            op="int",
            lower=(m.group(1) or m.group(2)).strip(),
            upper=(m.group(3) or m.group(4)).strip(),
            body=body,
            differentials=diffs,
        )

    m = re.fullmatch(r"\\iint_(?:\{([^{}]+)\}|([A-Za-z]+|\\[A-Za-z]+))\s*(.+)", latex)
    if m:
        body, diffs = split_diff_suffix(m.group(3).strip())
        return IntegralIR(kind="integral", op="iint", region=(m.group(1) or m.group(2)).strip(), body=body, differentials=diffs)

    m = re.fullmatch(r"\\iiint_(?:\{([^{}]+)\}|([A-Za-z]+|\\[A-Za-z]+))\s*(.+)", latex)
    if m:
        body, diffs = split_diff_suffix(m.group(3).strip())
        return IntegralIR(kind="integral", op="iiint", region=(m.group(1) or m.group(2)).strip(), body=body, differentials=diffs)

    return None


def try_build_derivative_ir(latex: str) -> Optional[DerivativeIR]:
    """识别常见常微分写法。"""
    m = re.fullmatch(
        r"\\frac\s*\{d\^\{?([0-9]+)\}?\s+([^{}]+)\}\s*\{d\s*([A-Za-z]+)\^\{?([0-9]+)\}?\}",
        latex,
    )
    if m and m.group(1) == m.group(4):
        return DerivativeIR(kind="derivative", body=m.group(2).strip(), variable=m.group(3).strip(), order=int(m.group(1)))

    m = re.fullmatch(r"\\frac\s*\{d\}\s*\{d\s*([A-Za-z]+)\}\s*(.+)", latex)
    if m:
        return DerivativeIR(kind="derivative", body=m.group(2).strip(), variable=m.group(1).strip())

    m = re.fullmatch(r"\\frac\s*\{d\s*([^{}]+)\}\s*\{d\s*([^{}]+)\}", latex)
    if m:
        return DerivativeIR(kind="derivative", body=m.group(1).strip(), variable=m.group(2).strip())

    m = re.fullmatch(r"([A-Za-z]+)('{1,})\(([^()]*)\)", latex)
    if m:
        return DerivativeIR(
            kind="derivative",
            body=m.group(1),
            variable=m.group(3).strip(),
            order=len(m.group(2)),
            prime_style=True,
            function_name=m.group(1),
            function_arg=m.group(3).strip(),
        )

    return None


def try_build_partial_ir(latex: str) -> Optional[DerivativeIR]:
    """识别常见偏导和混合偏导写法。"""
    m = re.fullmatch(
        r"\\frac\s*\{\\partial\^\{?([0-9]+)\}?\s+([^{}]+)\}\s*\{\\partial\s*([A-Za-z]+)\s*\\partial\s*([A-Za-z]+)\}",
        latex,
    )
    if m:
        return DerivativeIR(
            kind="derivative",
            body=m.group(2).strip(),
            variable="",
            order=int(m.group(1)),
            partial=True,
            mixed=((m.group(3).strip(), 1), (m.group(4).strip(), 1)),
        )

    m = re.fullmatch(
        r"\\frac\s*\{\\partial\^\{?([0-9]+)\}?\s+([^{}]+)\}\s*\{\\partial\s*([A-Za-z]+)\^\{?([0-9]+)\}?\s*\\partial\s*([A-Za-z]+)\}",
        latex,
    )
    if m:
        return DerivativeIR(
            kind="derivative",
            body=m.group(2).strip(),
            variable="",
            order=int(m.group(1)),
            partial=True,
            mixed=((m.group(3).strip(), int(m.group(4))), (m.group(5).strip(), 1)),
        )

    m = re.fullmatch(
        r"\\frac\s*\{\\partial\^\{?([0-9]+)\}?\s+([^{}]+)\}\s*\{\\partial\s*([A-Za-z]+)\^\{?([0-9]+)\}?\}",
        latex,
    )
    if m and m.group(1) == m.group(4):
        return DerivativeIR(kind="derivative", body=m.group(2).strip(), variable=m.group(3).strip(), order=int(m.group(1)), partial=True)

    m = re.fullmatch(r"\\frac\s*\{\\partial\s*([^{}]+)\}\s*\{\\partial\s*([^{}]+)\}", latex)
    if m:
        return DerivativeIR(kind="derivative", body=m.group(1).strip(), variable=m.group(2).strip(), partial=True)

    m = re.fullmatch(r"\\frac\s*\{\\partial\}\s*\{\\partial\s*([A-Za-z]+)\}\s*(.+)", latex)
    if m:
        return DerivativeIR(kind="derivative", body=m.group(2).strip(), variable=m.group(1).strip(), partial=True)

    return None


def build_semantic_ir(
    latex: str,
    *,
    _normalized: bool = False,
    _allow_annotations: bool = True,
) -> SemanticIR:
    """把 LaTeX 文本转换成统一的语义中间层。"""
    normalized = latex if _normalized else normalize_latex_for_parser(latex)

    if _allow_annotations:
        core, notes = extract_trailing_text_annotations(normalized)
        if notes:
            return AnnotatedIR(
                kind="annotated",
                body=build_semantic_ir(
                    core,
                    _normalized=True,
                    _allow_annotations=False,
                ),
                notes=notes,
            )

    for builder in (
        try_build_greek_symbol_ir,
        try_build_boxed_ir,
        try_build_assignment_ir,
        try_build_subscript_ir,
        try_build_cases_ir,
        try_build_matrix_ir,
        try_build_derivative_ir,
        try_build_partial_ir,
        try_build_sumprod_ir,
        try_build_integral_ir,
        try_build_limit_ir,
    ):
        result = builder(normalized)
        if result is not None:
            return result

    expr = parse_latex(normalized, backend="antlr")
    return ExprIR(kind="expr", latex=normalized, expr=expr)


# =========================
# 4. expr speech helpers
# =========================


def is_negative_expr(expr) -> bool:
    """判断表达式是否带有显式负号。"""
    if expr.is_number and expr.is_negative:
        return True
    if isinstance(expr, Mul) and expr.args and expr.args[0] == -1:
        return True
    return False


def join_add_terms(expr: Add) -> str:
    """按加减顺序拼接加法表达式的口播文本。"""
    parts = []
    for index, arg in enumerate(expr.args):
        text = speak_expr(arg)
        if index == 0:
            parts.append(text)
        elif is_negative_expr(arg):
            parts.append(f"减{speak_expr(-arg)}")
        else:
            parts.append(f"加{text}")
    return "".join(parts)


def speak_relational(expr: Relational) -> str:
    """口播关系表达式。"""
    op = REL_OP_SPOKEN.get(expr.rel_op, expr.rel_op)
    return f"{speak_expr(expr.lhs)}{op}{speak_expr(expr.rhs)}"


def speak_power(base_text: str, exp) -> str:
    """口播幂运算，优先处理常见特殊指数。"""
    if exp == Integer(2):
        return f"{base_text}的平方"
    if exp == Integer(3):
        return f"{base_text}的3次方"
    if exp == Rational(1, 2):
        return f"{base_text}的2分之1次方"
    if exp == Integer(-1):
        return f"{base_text}分之1"
    if exp == Integer(-2):
        return f"1除以{base_text}的平方"
    return f"{base_text}的{speak_expr(exp)}次方"


def speak_fraction(numer, denom) -> str:
    """口播分式，按复杂度选择“分之”或“除以”。"""
    num_text = speak_expr(numer)
    den_text = speak_expr(denom)
    if getattr(numer, "is_Integer", False) and getattr(denom, "is_Integer", False):
        return f"{den_text}分之{num_text}"
    if isinstance(denom, (Add, Mul, Pow, Function)):
        return f"{num_text}除以{den_text}"
    return f"{den_text}分之{num_text}"


def speak_mul(expr: Mul) -> str:
    """口播乘法表达式，并保留负号语义。"""
    if expr.args and expr.args[0] == -1:
        if len(expr.args) == 2:
            return f"负{speak_expr(expr.args[1])}"
        return f"负{speak_expr(Mul(*expr.args[1:]))}"
    parts = [speak_expr(arg) for arg in expr.args]
    if len(parts) == 2:
        return f"{parts[0]}{parts[1]}"
    return "乘以".join(parts)


def speak_function(expr) -> str:
    """口播函数调用表达式。"""
    name = expr.func.__name__
    args = expr.args
    zh_name = FUNCTION_SPOKEN.get(name, name)
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
    """口播未定义函数的调用形式。"""
    name = expr.func.__name__
    return f"{name}（{'，'.join(speak_expr(arg) for arg in expr.args)}）"


def speak_eq(expr: Eq) -> str:
    """口播等式表达式。"""
    return f"{speak_expr(expr.lhs)}等于{speak_expr(expr.rhs)}"


def try_speak_fraction(expr) -> Optional[str]:
    """尝试把一般表达式降级为分式口播。"""
    if isinstance(expr, (Add, Eq, Relational)) or not hasattr(expr, "as_numer_denom"):
        return None
    numer, denom = expr.as_numer_denom()
    if denom == 1:
        return None
    return speak_fraction(numer, denom)


def speak_expr(expr) -> str:
    """把 SymPy 表达式递归转换成中文口播。"""
    if isinstance(expr, Relational):
        return speak_relational(expr)
    if isinstance(expr, Eq):
        return speak_eq(expr)
    if isinstance(expr, AppliedUndef):
        return speak_applied_undef(expr)
    if isinstance(expr, Symbol):
        return speak_symbol_name(str(expr))
    if getattr(expr, "is_Integer", False):
        n = int(expr)
        return f"负{abs(n)}" if n < 0 else str(n)
    if getattr(expr, "is_Number", False):
        return str(expr)
    if isinstance(expr, Add):
        return join_add_terms(expr)
    fraction_text = try_speak_fraction(expr)
    if fraction_text is not None:
        return fraction_text
    if isinstance(expr, Pow):
        base, exp = expr.args
        if exp == Rational(1, 2):
            return f"根号下{speak_expr(base)}"
        base_text = speak_expr(base)
        if isinstance(base, (Add, Eq)):
            base_text = f"括号{base_text}"
        return speak_power(base_text, exp)
    if isinstance(expr, Mul):
        return speak_mul(expr)
    if isinstance(expr, Function):
        return speak_function(expr)
    return str(expr)


# =========================
# 5. IR -> speech
# =========================


def render_derivative_ir(ir: DerivativeIR) -> str:
    """把导数 IR 渲染成中文口播。"""
    body = oralize_latex(strip_outer_parens(ir.body))
    if ir.prime_style and ir.function_name and ir.function_arg is not None:
        order_map = {1: "一阶", 2: "二阶", 3: "三阶"}
        return f"{ir.function_name}关于{oralize_latex(ir.function_arg)}的{order_map.get(ir.order, str(ir.order) + '阶')}导数"

    if ir.partial:
        if ir.mixed:
            if len(ir.mixed) == 2 and ir.mixed[0][1] == 1 and ir.mixed[1][1] == 1 and ir.order == 2:
                var1 = oralize_latex(ir.mixed[0][0])
                var2 = oralize_latex(ir.mixed[1][0])
                return f"{body}先对{var1}再对{var2}的二阶混合偏导"
            parts = []
            for var, order in ir.mixed:
                var_text = oralize_latex(var)
                if order == 1:
                    parts.append(f"对{var_text}的一阶")
                else:
                    parts.append(f"对{var_text}的{order}阶")
            return f"{body}{'，'.join(parts)}，共{ir.order}阶偏导"
        if ir.order == 1:
            return f"{body}对{oralize_latex(ir.variable)}的偏导"
        return f"{body}对{oralize_latex(ir.variable)}的{ir.order}阶偏导"

    if ir.order == 1:
        return f"{body}对{oralize_latex(ir.variable)}的导数"
    return f"{body}对{oralize_latex(ir.variable)}的{ir.order}阶导数"


def render_integral_ir(ir: IntegralIR) -> str:
    """把积分 IR 渲染成中文口播。"""
    body_text = oralize_latex(ir.body) if ir.body else ""
    diff_text = " ".join(f"d {item}" for item in ir.differentials)

    if ir.op == "oint":
        region = normalize_region_name(ir.region or "")
        if ir.differentials == ("x", "y"):
            pair = re.fullmatch(r"(.+?)d([A-Za-z])\s*\+\s*(.+?)d([A-Za-z])", ir.body)
            if pair:
                first = pair.group(1).strip()
                second = pair.group(3).strip()
                return f"沿{region}的闭合曲线积分，第一部分是{oralize_latex(first)}对x积分，第二部分是{oralize_latex(second)}对y积分"
        return f"沿{region}的闭合曲线积分，{body_text}{'，' + diff_text if diff_text else ''}"

    if ir.op == "curve":
        return f"沿{normalize_region_name(ir.region or '')}的曲线积分，{body_text}对弧长s积分"

    if ir.op == "int":
        lower = oralize_bound(ir.lower or "")
        upper = oralize_bound(ir.upper or "")
        if ir.differentials:
            return f"从{lower}到{upper}，{body_text}对{''.join(ir.differentials)}的定积分"
        return f"从{lower}到{upper}的定积分，积分函数是{body_text}"

    if ir.op == "iint":
        return f"在{normalize_region_name(ir.region or '')}上，{body_text}的二重积分，{diff_text}"

    if ir.op == "iiint":
        return f"在{normalize_region_name(ir.region or '')}上，{body_text}的三重积分，{diff_text}"

    return body_text


def render_semantic_ir(ir: SemanticIR) -> str:
    """把任意语义 IR 渲染成最终中文口播。"""
    if isinstance(ir, AnnotatedIR):
        body_text = render_semantic_ir(ir.body)
        note_text = "；".join(f"注释：{note}" for note in ir.notes)
        return f"{body_text}；{note_text}" if body_text else note_text
    if isinstance(ir, SymbolIR):
        return GREEK_SPOKEN[ir.name]
    if isinstance(ir, BoxedIR):
        return f"方框中的{oralize_latex(ir.body)}"
    if isinstance(ir, AssignmentIR):
        return f"{oralize_latex(ir.lhs)}等于{oralize_latex(strip_outer_parens(ir.rhs))}"
    if isinstance(ir, SubscriptIR):
        subscript = ir.subscript.replace(",", "逗号").replace("*", "")
        return f"{ir.base}下标{oralize_inline_formula(subscript)}"
    if isinstance(ir, LimitIR):
        return f"当{speak_atom_text(ir.variable)}趋近于{speak_atom_text(ir.target)}时，{oralize_latex(ir.body)}"
    if isinstance(ir, CasesIR):
        parts = [f"当{oralize_latex(cond)}时，函数值是{oralize_latex(value)}" for value, cond in ir.rows]
        return "分段函数。" + "；".join(parts)
    if isinstance(ir, MatrixIR):
        row_n = len(ir.rows)
        col_n = max((len(row) for row in ir.rows), default=0)
        noun = "行列式" if ir.matrix_type == "vmatrix" else "矩阵"
        pieces = [f"这是一个{row_n}行{col_n}列{noun}"]
        for index, row in enumerate(ir.rows, start=1):
            pieces.append(f"第{index}行是{'，'.join(oralize_inline_formula(cell) for cell in row)}")
        return "。".join(pieces)
    if isinstance(ir, DerivativeIR):
        return render_derivative_ir(ir)
    if isinstance(ir, SumProdIR):
        op_text = "求和" if ir.op == "sum" else "连乘"
        item_text = "求和项" if ir.op == "sum" else "连乘项"
        return f"从{oralize_latex(ir.variable)}等于{oralize_latex(ir.lower)}到{oralize_latex(ir.upper)}{op_text}，{item_text}是{oralize_inline_formula(ir.body)}"
    if isinstance(ir, IntegralIR):
        return render_integral_ir(ir)
    if isinstance(ir, ExprIR):
        return speak_expr(ir.expr)
    raise TypeError(f"Unsupported IR: {type(ir)!r}")


# =========================
# 6. public API
# =========================


def oralize_latex(latex: str) -> str:
    """对外暴露的 LaTeX 转中文口播入口。"""
    return render_semantic_ir(build_semantic_ir(latex))


def oralize_latex_with_trace(latex: str) -> tuple[str, dict[str, object]]:
    """返回口播结果与调试追踪信息，供上层适配器记录。"""
    normalized_text = normalize_latex_for_parser(latex)
    trace: dict[str, object] = {
        "backend": "math_latex_oralizer",
        "mode": "semantic_ir",
        "fallback_used": False,
        "fallback_reason": "",
        "normalized_text": normalized_text,
    }

    try:
        ir = build_semantic_ir(latex)
        trace["ir_kind"] = ir.kind
        return render_semantic_ir(ir), trace
    except Exception as exc:
        trace["mode"] = "normalized_fallback"
        trace["fallback_used"] = True
        trace["fallback_reason"] = f"{type(exc).__name__}: {exc}"
        return normalized_text or latex.strip(), trace


def demo(latex: str) -> None:
    """打印单条样例的归一化结果与中文口播。"""
    try:
        ir = build_semantic_ir(latex)
        spoken = render_semantic_ir(ir)
    except Exception as e:
        spoken = f"[解析失败] {e}"

    print("=" * 100)
    print("LaTeX   :", latex)
    print("Normalize:", normalize_latex_for_parser(latex))
    print("中文口播 :", spoken)






__all__ = [
    "normalize_latex_for_parser",
    "oralize_latex",
    "oralize_latex_with_trace",
]
