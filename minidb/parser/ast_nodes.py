"""
AST Node definitions for SQL parsing in MiniDB.
"""

from typing import List, Any, Optional, Tuple


class ASTNode:
    pass


class ColumnDef(ASTNode):
    def __init__(self, name: str, col_type: str, max_length: int = 64, primary_key: bool = False):
        self.name = name
        self.col_type = col_type
        self.max_length = max_length
        self.primary_key = primary_key


class Expr(ASTNode):
    pass


class LiteralExpr(Expr):
    def __init__(self, value: Any):
        self.value = value


class ColumnExpr(Expr):
    def __init__(self, name: str):
        self.name = name


class BinaryOpExpr(Expr):
    def __init__(self, left: Expr, op: str, right: Expr):
        self.left = left
        self.op = op  # =, !=, <, >, <=, >=, AND, OR, LIKE
        self.right = right


class UnaryOpExpr(Expr):
    def __init__(self, op: str, operand: Expr):
        self.op = op  # NOT
        self.operand = operand


class InExpr(Expr):
    def __init__(self, expr: Expr, values: List[Expr], is_not: bool = False):
        self.expr = expr
        self.values = values
        self.is_not = is_not


class IsNullExpr(Expr):
    def __init__(self, expr: Expr, is_not: bool = False):
        self.expr = expr
        self.is_not = is_not


class AggregateFuncExpr(Expr):
    def __init__(self, func_name: str, arg: str):
        self.func_name = func_name.upper()  # COUNT, SUM, AVG, MIN, MAX
        self.arg = arg  # '*' or column name


class CreateTableStmt(ASTNode):
    def __init__(self, table_name: str, columns: List[ColumnDef]):
        self.table_name = table_name
        self.columns = columns


class CreateIndexStmt(ASTNode):
    def __init__(self, index_name: str, table_name: str, column_name: str, index_type: str = "BTREE"):
        self.index_name = index_name
        self.table_name = table_name
        self.column_name = column_name
        self.index_type = index_type


class InsertStmt(ASTNode):
    def __init__(self, table_name: str, columns: Optional[List[str]], values: List[Any]):
        self.table_name = table_name
        self.columns = columns
        self.values = values


class SelectStmt(ASTNode):
    def __init__(self, columns: List[str], table_name: str, where_clause: Optional[Expr] = None, order_by: Optional[Tuple[str, str]] = None, limit: Optional[int] = None):
        self.columns = columns  # ['*'] or list of col names
        self.table_name = table_name
        self.where_clause = where_clause
        self.order_by = order_by  # (column, 'ASC'|'DESC')
        self.limit = limit


class UpdateStmt(ASTNode):
    def __init__(self, table_name: str, assignments: List[Tuple[str, Any]], where_clause: Optional[Expr] = None):
        self.table_name = table_name
        self.assignments = assignments
        self.where_clause = where_clause


class DeleteStmt(ASTNode):
    def __init__(self, table_name: str, where_clause: Optional[Expr] = None):
        self.table_name = table_name
        self.where_clause = where_clause


class DropTableStmt(ASTNode):
    def __init__(self, table_name: str):
        self.table_name = table_name


class ExplainStmt(ASTNode):
    def __init__(self, statement: ASTNode):
        self.statement = statement
