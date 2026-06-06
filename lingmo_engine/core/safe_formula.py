"""安全公式求值器 — 基于 AST 白名单的数学表达式求值。

替换 ability_generator 中不安全的 eval() 调用。
仅允许：数字、变量、算术运算符、比较运算符、以及 abs/min/max/floor/ceil 函数。
"""

from __future__ import annotations

import ast
import math
import operator
from typing import Any

# 允许的二元运算符
_ALLOWED_OPS: dict[type, Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

# 允许的比较运算符
_ALLOWED_COMPARE: dict[type, Any] = {
    ast.Gt: operator.gt,
    ast.Lt: operator.lt,
    ast.GtE: operator.ge,
    ast.LtE: operator.le,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
}

# 允许的函数白名单
_ALLOWED_FUNCTIONS: dict[str, Any] = {
    "abs": abs,
    "max": max,
    "min": min,
    "floor": math.floor,
    "ceil": math.ceil,
}


def _eval_node(node: ast.AST, namespace: dict[str, Any]) -> Any:
    """递归求值 AST 节点，仅允许白名单中的操作。"""
    if isinstance(node, ast.Constant):
        return node.value

    if isinstance(node, ast.Name):
        if node.id in namespace:
            return namespace[node.id]
        raise ValueError(f"公式中引用了未定义的变量: '{node.id}'")

    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _ALLOWED_OPS:
            raise ValueError(f"公式中包含不允许的运算符: {op_type.__name__}")
        left = _eval_node(node.left, namespace)
        right = _eval_node(node.right, namespace)
        return _ALLOWED_OPS[op_type](left, right)

    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.USub):
            return -_eval_node(node.operand, namespace)
        if isinstance(node.op, ast.UAdd):
            return +_eval_node(node.operand, namespace)
        raise ValueError("公式中包含不允许的一元运算符")

    if isinstance(node, ast.Compare):
        if len(node.ops) != 1 or len(node.comparators) != 1:
            raise ValueError("公式中仅支持单一比较运算")
        op_type = type(node.ops[0])
        if op_type not in _ALLOWED_COMPARE:
            raise ValueError(f"公式中包含不允许的比较运算符: {op_type.__name__}")
        left = _eval_node(node.left, namespace)
        right = _eval_node(node.comparators[0], namespace)
        return _ALLOWED_COMPARE[op_type](left, right)

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError("公式中仅支持直接函数调用")
        func_name = node.func.id
        if func_name not in _ALLOWED_FUNCTIONS:
            raise ValueError(f"公式中调用了不允许的函数: '{func_name}'")
        func = _ALLOWED_FUNCTIONS[func_name]
        args = [_eval_node(arg, namespace) for arg in node.args]
        return func(*args)

    raise ValueError(f"公式中包含不允许的语法节点: {type(node).__name__}")


def safe_eval(formula: str, namespace: dict[str, Any]) -> Any:
    """安全求值一个数学公式字符串。

    Args:
        formula: 数学公式字符串，例如 "power * 2 + modifier"
        namespace: 变量名到值的映射

    Returns:
        求值结果（通常为数值）

    Raises:
        ValueError: 公式中包含不允许的语法
        SyntaxError: 公式语法错误
    """
    tree = ast.parse(formula.strip(), mode="eval")
    return _eval_node(tree.body, namespace)
