"""
SQL Tokenizer / Lexer for MiniDB.
"""

import re
from typing import List, NamedTuple, Optional

class TokenType:
    KEYWORD = "KEYWORD"
    IDENTIFIER = "IDENTIFIER"
    NUMBER = "NUMBER"
    STRING = "STRING"
    BOOLEAN = "BOOLEAN"
    OPERATOR = "OPERATOR"
    PUNCTUATION = "PUNCTUATION"
    EOF = "EOF"

class Token(NamedTuple):
    type: str
    value: str
    position: int

KEYWORDS = {
    "CREATE", "TABLE", "INDEX", "ON", "USING", "INSERT", "INTO", "VALUES",
    "SELECT", "FROM", "WHERE", "UPDATE", "SET", "DELETE", "DROP", "EXPLAIN",
    "BTREE", "HASH", "AND", "OR", "ORDER", "BY", "LIMIT", "ASC", "DESC",
    "PRIMARY", "KEY", "INT", "INTEGER", "VARCHAR", "FLOAT", "BOOLEAN", "TRUE", "FALSE",
    "LIKE", "IN", "IS", "NOT", "NULL", "COUNT", "SUM", "AVG", "MIN", "MAX"
}

TOKEN_SPEC = [
    ('NUMBER',   r'\d+(\.\d+)?'),            # Integer or decimal number
    ('STRING',   r"'[^']*'|\"[^\"]*\""),    # Single or double quoted string
    ('OPERATOR', r'!=|<=|>=|=|<|>'),        # Comparison operators
    ('PUNCTUATION', r'[\(\),\;\*]'),         # Parentheses, comma, semicolon, star
    ('IDENTIFIER', r'[a-zA-Z_][a-zA-Z0-9_]*'), # Identifiers
    ('SKIP',     r'[ \t\r\n]+'),            # Skip spaces and newlines
    ('MISMATCH', r'.'),                     # Any other character
]

def lex(sql: str) -> List[Token]:
    """Tokenize raw SQL string into token sequence."""
    tok_regex = '|'.join('(?P<%s>%s)' % pair for pair in TOKEN_SPEC)
    tokens = []
    
    for mo in re.finditer(tok_regex, sql):
        kind = mo.lastgroup
        value = mo.group()
        pos = mo.start()

        if kind == 'SKIP':
            continue
        elif kind == 'NUMBER':
            val = float(value) if '.' in value else int(value)
            tokens.append(Token(TokenType.NUMBER, str(val), pos))
        elif kind == 'STRING':
            # Strip quotes
            clean_str = value[1:-1]
            tokens.append(Token(TokenType.STRING, clean_str, pos))
        elif kind == 'IDENTIFIER':
            upper_val = value.upper()
            if upper_val in {"TRUE", "FALSE"}:
                tokens.append(Token(TokenType.BOOLEAN, upper_val, pos))
            elif upper_val in KEYWORDS:
                tokens.append(Token(TokenType.KEYWORD, upper_val, pos))
            else:
                tokens.append(Token(TokenType.IDENTIFIER, value, pos))
        elif kind == 'OPERATOR':
            tokens.append(Token(TokenType.OPERATOR, value, pos))
        elif kind == 'PUNCTUATION':
            tokens.append(Token(TokenType.PUNCTUATION, value, pos))
        elif kind == 'MISMATCH':
            raise SyntaxError(f"Unexpected character '{value}' at position {pos}")

    tokens.append(Token(TokenType.EOF, "", len(sql)))
    return tokens
