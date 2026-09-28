"""
Expression evaluation engine for MiniDB.
"""

import re
from typing import Dict, Any
from minidb.parser.ast_nodes import Expr, LiteralExpr, ColumnExpr, BinaryOpExpr, UnaryOpExpr, InExpr, IsNullExpr


def evaluate_expr(expr: Expr, row: Dict[str, Any]) -> Any:
    """Evaluate AST expression node against a tuple row dict."""
    if isinstance(expr, LiteralExpr):
        return expr.value
    elif isinstance(expr, ColumnExpr):
        col_name = expr.name.lower()
        # Case insensitive match for row keys
        for key, val in row.items():
            if key.lower() == col_name:
                return val
        return None
    elif isinstance(expr, UnaryOpExpr):
        val = evaluate_expr(expr.operand, row)
        if expr.op.upper() == "NOT":
            return not bool(val)
        return val
    elif isinstance(expr, IsNullExpr):
        val = evaluate_expr(expr.expr, row)
        is_null = val is None
        return not is_null if expr.is_not else is_null
    elif isinstance(expr, InExpr):
        target = evaluate_expr(expr.expr, row)
        in_list = [evaluate_expr(v, row) for v in expr.values]
        found = target in in_list
        return not found if expr.is_not else found
    elif isinstance(expr, BinaryOpExpr):
        left_val = evaluate_expr(expr.left, row)
        right_val = evaluate_expr(expr.right, row)
        op = expr.op.upper()

        if op == "=":
            return left_val == right_val
        elif op == "!=":
            return left_val != right_val
        elif op == "<":
            return left_val < right_val if (left_val is not None and right_val is not None) else False
        elif op == ">":
            return left_val > right_val if (left_val is not None and right_val is not None) else False
        elif op == "<=":
            return left_val <= right_val if (left_val is not None and right_val is not None) else False
        elif op == ">=":
            return left_val >= right_val if (left_val is not None and right_val is not None) else False
        elif op == "AND":
            return bool(left_val) and bool(right_val)
        elif op == "OR":
            return bool(left_val) or bool(right_val)
        elif op == "LIKE":
            if left_val is None or right_val is None:
                return False
            # Convert SQL LIKE pattern (% -> .*, _ -> .) to regex
            raw_pat = str(right_val).replace("%", "\x00").replace("_", "\x01")
            escaped_pat = re.escape(raw_pat).replace("\x00", ".*").replace("\x01", ".")
            pattern = "^" + escaped_pat + "$"
            return bool(re.match(pattern, str(left_val), re.IGNORECASE))
        else:
            raise ValueError(f"Unsupported operator {op}")
    else:
        raise ValueError(f"Unknown expression type {type(expr)}")
