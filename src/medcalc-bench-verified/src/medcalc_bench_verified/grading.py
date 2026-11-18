"""Run the unchanged upstream scorer with a restricted arithmetic evaluator.

Only the unused imports are omitted. Calls/attributes/names in untrusted numeric
answers are rejected rather than executed. Valid arithmetic retains Python's
rounding, tuple and inclusive-bound behavior. Infrastructure errors propagate.
"""
import ast
from datetime import datetime
import math
import re


def numeric_eval(text):
    if len(str(text)) > 128:
        raise ValueError("Answer too long")
    tree = ast.parse(str(text), mode="eval")
    allowed = (ast.Expression, ast.Constant, ast.Tuple, ast.Load, ast.BinOp,
               ast.UnaryOp, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.USub, ast.UAdd)
    if any(not isinstance(n, allowed) for n in ast.walk(tree)):
        raise ValueError("Unsupported numeric expression")
    value = eval(compile(tree, "<answer>", "eval"), {"__builtins__": {}})
    values = value if isinstance(value, tuple) else (value,)
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
        raise ValueError("Non-finite or non-numeric answer")
    return value


def load_scorer(source, restricted=True):
    module = ast.parse(source)
    function = next(n for n in module.body if isinstance(n, ast.FunctionDef)
                    and n.name == "check_correctness")
    namespace = {"re": re, "datetime": datetime}
    if restricted:
        namespace["eval"] = numeric_eval
    exec(compile(ast.Module(body=[function], type_ignores=[]), "upstream/evaluate.py", "exec"), namespace)
    return namespace["check_correctness"]


def score_answer(answer, gold, scorer):
    try:
        return int(scorer(answer, gold["Ground Truth Answer"], gold["Calculator ID"],
                          gold["Upper Limit"], gold["Lower Limit"]))
    except (ValueError, SyntaxError, TypeError, ZeroDivisionError, OverflowError, AttributeError):
        return 0
