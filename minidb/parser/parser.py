"""
Recursive Descent SQL Parser for MiniDB.

Parses token streams into AST node structures.
"""

from typing import List, Optional, Tuple, Any
from minidb.parser.lexer import Token, TokenType, lex
from minidb.parser.ast_nodes import (
    ASTNode, ColumnDef, CreateTableStmt, CreateIndexStmt, InsertStmt,
    SelectStmt, UpdateStmt, DeleteStmt, DropTableStmt, ExplainStmt,
    BinaryOpExpr, UnaryOpExpr, InExpr, IsNullExpr, AggregateFuncExpr,
    LiteralExpr, ColumnExpr, Expr
)


class Parser:
    """SQL Recursive Descent Parser."""

    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos = 0

    def current(self) -> Token:
        return self.tokens[self.pos]

    def peek(self, offset: int = 1) -> Token:
        idx = self.pos + offset
        if idx < len(self.tokens):
            return self.tokens[idx]
        return self.tokens[-1]

    def match(self, token_type: str, value: Optional[str] = None) -> bool:
        tok = self.current()
        if tok.type != token_type:
            return False
        if value is not None and tok.value.upper() != value.upper():
            return False
        return True

    def consume(self, token_type: str, value: Optional[str] = None) -> Token:
        tok = self.current()
        if not self.match(token_type, value):
            expected = f"{token_type}('{value}')" if value else token_type
            raise SyntaxError(f"Expected {expected}, got {tok.type}('{tok.value}') at position {tok.position}")
        self.pos += 1
        return tok

    def parse(self) -> ASTNode:
        """Parse main statement."""
        tok = self.current()
        if self.match(TokenType.KEYWORD, "EXPLAIN"):
            self.consume(TokenType.KEYWORD, "EXPLAIN")
            stmt = self.parse()
            return ExplainStmt(stmt)
        elif self.match(TokenType.KEYWORD, "CREATE"):
            return self.parse_create()
        elif self.match(TokenType.KEYWORD, "INSERT"):
            return self.parse_insert()
        elif self.match(TokenType.KEYWORD, "SELECT"):
            return self.parse_select()
        elif self.match(TokenType.KEYWORD, "UPDATE"):
            return self.parse_update()
        elif self.match(TokenType.KEYWORD, "DELETE"):
            return self.parse_delete()
        elif self.match(TokenType.KEYWORD, "DROP"):
            return self.parse_drop()
        else:
            raise SyntaxError(f"Unexpected token '{tok.value}' at start of statement")

    def parse_create(self) -> ASTNode:
        self.consume(TokenType.KEYWORD, "CREATE")
        if self.match(TokenType.KEYWORD, "TABLE"):
            self.consume(TokenType.KEYWORD, "TABLE")
            table_name = self.consume(TokenType.IDENTIFIER).value

            self.consume(TokenType.PUNCTUATION, "(")
            columns = []
            while not self.match(TokenType.PUNCTUATION, ")"):
                col_name = self.consume(TokenType.IDENTIFIER).value
                col_type_tok = self.current()
                if not self.match(TokenType.KEYWORD):
                    raise SyntaxError(f"Expected data type for column {col_name}")
                col_type = self.consume(TokenType.KEYWORD).value

                max_len = 64
                if col_type == "VARCHAR":
                    if self.match(TokenType.PUNCTUATION, "("):
                        self.consume(TokenType.PUNCTUATION, "(")
                        max_len = int(self.consume(TokenType.NUMBER).value)
                        self.consume(TokenType.PUNCTUATION, ")")

                is_pk = False
                if self.match(TokenType.KEYWORD, "PRIMARY"):
                    self.consume(TokenType.KEYWORD, "PRIMARY")
                    self.consume(TokenType.KEYWORD, "KEY")
                    is_pk = True

                columns.append(ColumnDef(col_name, col_type, max_len, is_pk))

                if self.match(TokenType.PUNCTUATION, ","):
                    self.consume(TokenType.PUNCTUATION, ",")

            self.consume(TokenType.PUNCTUATION, ")")
            return CreateTableStmt(table_name, columns)

        elif self.match(TokenType.KEYWORD, "INDEX"):
            self.consume(TokenType.KEYWORD, "INDEX")
            idx_name = self.consume(TokenType.IDENTIFIER).value
            self.consume(TokenType.KEYWORD, "ON")
            table_name = self.consume(TokenType.IDENTIFIER).value

            self.consume(TokenType.PUNCTUATION, "(")
            col_name = self.consume(TokenType.IDENTIFIER).value
            self.consume(TokenType.PUNCTUATION, ")")

            idx_type = "BTREE"
            if self.match(TokenType.KEYWORD, "USING"):
                self.consume(TokenType.KEYWORD, "USING")
                idx_type = self.consume(TokenType.KEYWORD).value

            return CreateIndexStmt(idx_name, table_name, col_name, idx_type)
        else:
            raise SyntaxError("Expected TABLE or INDEX after CREATE")

    def parse_insert(self) -> InsertStmt:
        self.consume(TokenType.KEYWORD, "INSERT")
        self.consume(TokenType.KEYWORD, "INTO")
        table_name = self.consume(TokenType.IDENTIFIER).value

        columns = None
        if self.match(TokenType.PUNCTUATION, "("):
            self.consume(TokenType.PUNCTUATION, "(")
            columns = []
            while not self.match(TokenType.PUNCTUATION, ")"):
                columns.append(self.consume(TokenType.IDENTIFIER).value)
                if self.match(TokenType.PUNCTUATION, ","):
                    self.consume(TokenType.PUNCTUATION, ",")
            self.consume(TokenType.PUNCTUATION, ")")

        self.consume(TokenType.KEYWORD, "VALUES")
        self.consume(TokenType.PUNCTUATION, "(")
        values = []
        while not self.match(TokenType.PUNCTUATION, ")"):
            val_expr = self.parse_primary_expr()
            values.append(val_expr.value if isinstance(val_expr, LiteralExpr) else str(val_expr))
            if self.match(TokenType.PUNCTUATION, ","):
                self.consume(TokenType.PUNCTUATION, ",")
        self.consume(TokenType.PUNCTUATION, ")")

        return InsertStmt(table_name, columns, values)

    def parse_select(self) -> SelectStmt:
        self.consume(TokenType.KEYWORD, "SELECT")
        cols = []
        if self.match(TokenType.PUNCTUATION, "*"):
            self.consume(TokenType.PUNCTUATION, "*")
            cols = ["*"]
        else:
            while True:
                if self.match(TokenType.KEYWORD) and self.current().value.upper() in ("COUNT", "SUM", "AVG", "MIN", "MAX"):
                    fn = self.consume(TokenType.KEYWORD).value.upper()
                    self.consume(TokenType.PUNCTUATION, "(")
                    if self.match(TokenType.PUNCTUATION, "*"):
                        self.consume(TokenType.PUNCTUATION, "*")
                        arg = "*"
                    else:
                        arg = self.consume(TokenType.IDENTIFIER).value
                    self.consume(TokenType.PUNCTUATION, ")")
                    cols.append(f"{fn}({arg})")
                else:
                    cols.append(self.consume(TokenType.IDENTIFIER).value)

                if self.match(TokenType.PUNCTUATION, ","):
                    self.consume(TokenType.PUNCTUATION, ",")
                else:
                    break

        self.consume(TokenType.KEYWORD, "FROM")
        table_name = self.consume(TokenType.IDENTIFIER).value

        where_clause = None
        if self.match(TokenType.KEYWORD, "WHERE"):
            self.consume(TokenType.KEYWORD, "WHERE")
            where_clause = self.parse_expression()

        order_by = None
        if self.match(TokenType.KEYWORD, "ORDER"):
            self.consume(TokenType.KEYWORD, "ORDER")
            self.consume(TokenType.KEYWORD, "BY")
            ord_col = self.consume(TokenType.IDENTIFIER).value
            direction = "ASC"
            if self.match(TokenType.KEYWORD, "ASC"):
                self.consume(TokenType.KEYWORD, "ASC")
            elif self.match(TokenType.KEYWORD, "DESC"):
                self.consume(TokenType.KEYWORD, "DESC")
                direction = "DESC"
            order_by = (ord_col, direction)

        limit = None
        if self.match(TokenType.KEYWORD, "LIMIT"):
            self.consume(TokenType.KEYWORD, "LIMIT")
            limit = int(self.consume(TokenType.NUMBER).value)

        return SelectStmt(cols, table_name, where_clause, order_by, limit)

    def parse_update(self) -> UpdateStmt:
        self.consume(TokenType.KEYWORD, "UPDATE")
        table_name = self.consume(TokenType.IDENTIFIER).value
        self.consume(TokenType.KEYWORD, "SET")

        assignments = []
        while True:
            col_name = self.consume(TokenType.IDENTIFIER).value
            self.consume(TokenType.OPERATOR, "=")
            val_expr = self.parse_primary_expr()
            val = val_expr.value if isinstance(val_expr, LiteralExpr) else None
            assignments.append((col_name, val))
            if self.match(TokenType.PUNCTUATION, ","):
                self.consume(TokenType.PUNCTUATION, ",")
            else:
                break

        where_clause = None
        if self.match(TokenType.KEYWORD, "WHERE"):
            self.consume(TokenType.KEYWORD, "WHERE")
            where_clause = self.parse_expression()

        return UpdateStmt(table_name, assignments, where_clause)

    def parse_delete(self) -> DeleteStmt:
        self.consume(TokenType.KEYWORD, "DELETE")
        self.consume(TokenType.KEYWORD, "FROM")
        table_name = self.consume(TokenType.IDENTIFIER).value

        where_clause = None
        if self.match(TokenType.KEYWORD, "WHERE"):
            self.consume(TokenType.KEYWORD, "WHERE")
            where_clause = self.parse_expression()

        return DeleteStmt(table_name, where_clause)

    def parse_drop(self) -> DropTableStmt:
        self.consume(TokenType.KEYWORD, "DROP")
        self.consume(TokenType.KEYWORD, "TABLE")
        table_name = self.consume(TokenType.IDENTIFIER).value
        return DropTableStmt(table_name)

    def parse_expression(self) -> Expr:
        return self.parse_logic_or()

    def parse_logic_or(self) -> Expr:
        expr = self.parse_logic_and()
        while self.match(TokenType.KEYWORD, "OR"):
            op = self.consume(TokenType.KEYWORD, "OR").value
            right = self.parse_logic_and()
            expr = BinaryOpExpr(expr, op, right)
        return expr

    def parse_logic_and(self) -> Expr:
        expr = self.parse_comparison()
        while self.match(TokenType.KEYWORD, "AND"):
            op = self.consume(TokenType.KEYWORD, "AND").value
            right = self.parse_comparison()
            expr = BinaryOpExpr(expr, op, right)
        return expr

    def parse_comparison(self) -> Expr:
        if self.match(TokenType.KEYWORD, "NOT"):
            self.consume(TokenType.KEYWORD, "NOT")
            return UnaryOpExpr("NOT", self.parse_comparison())

        left = self.parse_primary_expr()

        if self.match(TokenType.OPERATOR):
            op = self.consume(TokenType.OPERATOR).value
            right = self.parse_primary_expr()
            return BinaryOpExpr(left, op, right)
        elif self.match(TokenType.KEYWORD, "LIKE"):
            self.consume(TokenType.KEYWORD, "LIKE")
            right = self.parse_primary_expr()
            return BinaryOpExpr(left, "LIKE", right)
        elif self.match(TokenType.KEYWORD, "IN"):
            self.consume(TokenType.KEYWORD, "IN")
            self.consume(TokenType.PUNCTUATION, "(")
            vals = []
            while not self.match(TokenType.PUNCTUATION, ")"):
                vals.append(self.parse_primary_expr())
                if self.match(TokenType.PUNCTUATION, ","):
                    self.consume(TokenType.PUNCTUATION, ",")
            self.consume(TokenType.PUNCTUATION, ")")
            return InExpr(left, vals, is_not=False)
        elif self.match(TokenType.KEYWORD, "IS"):
            self.consume(TokenType.KEYWORD, "IS")
            is_not = False
            if self.match(TokenType.KEYWORD, "NOT"):
                self.consume(TokenType.KEYWORD, "NOT")
                is_not = True
            if self.match(TokenType.KEYWORD, "NULL") or self.match(TokenType.IDENTIFIER, "NULL"):
                self.consume(self.current().type)
            return IsNullExpr(left, is_not=is_not)

        return left

    def parse_primary_expr(self) -> Expr:
        tok = self.current()
        if self.match(TokenType.NUMBER):
            val = float(tok.value) if '.' in tok.value else int(tok.value)
            self.consume(TokenType.NUMBER)
            return LiteralExpr(val)
        elif self.match(TokenType.STRING):
            val = tok.value
            self.consume(TokenType.STRING)
            return LiteralExpr(val)
        elif self.match(TokenType.BOOLEAN):
            val = tok.value.upper() == "TRUE"
            self.consume(TokenType.BOOLEAN)
            return LiteralExpr(val)
        elif self.match(TokenType.IDENTIFIER):
            name = tok.value
            self.consume(TokenType.IDENTIFIER)
            return ColumnExpr(name)
        elif self.match(TokenType.PUNCTUATION, "("):
            self.consume(TokenType.PUNCTUATION, "(")
            expr = self.parse_expression()
            self.consume(TokenType.PUNCTUATION, ")")
            return expr
        else:
            raise SyntaxError(f"Invalid expression token '{tok.value}' at position {tok.position}")


def parse_sql(sql_query: str) -> ASTNode:
    tokens = lex(sql_query)
    parser = Parser(tokens)
    return parser.parse()
