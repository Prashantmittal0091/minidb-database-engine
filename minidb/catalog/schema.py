"""
Schema and Tuple Encoding/Decoding for MiniDB.

Supports INT, FLOAT, VARCHAR, and BOOLEAN column types with binary struct serialization.
"""

import struct
from typing import List, Dict, Any, Tuple, Optional


class Column:
    """Column definition within a table schema."""

    def __init__(self, name: str, col_type: str, max_length: int = 64, primary_key: bool = False):
        self.name: str = name
        self.col_type: str = col_type.upper()  # INT, FLOAT, VARCHAR, BOOLEAN
        self.max_length: int = max_length
        self.primary_key: bool = primary_key

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "col_type": self.col_type,
            "max_length": self.max_length,
            "primary_key": self.primary_key
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'Column':
        return cls(
            name=d["name"],
            col_type=d["col_type"],
            max_length=d.get("max_length", 64),
            primary_key=d.get("primary_key", False)
        )


class TableSchema:
    """Manages table definition and binary tuple encoding/decoding."""

    def __init__(self, table_name: str, columns: List[Column]):
        self.table_name: str = table_name
        self.columns: List[Column] = columns
        self.col_map: Dict[str, Column] = {col.name: col for col in columns}
        self.primary_key: Optional[str] = next((col.name for col in columns if col.primary_key), None)

    def to_dict(self) -> dict:
        return {
            "table_name": self.table_name,
            "columns": [c.to_dict() for c in self.columns]
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'TableSchema':
        columns = [Column.from_dict(c) for c in d["columns"]]
        return cls(d["table_name"], columns)

    def encode_tuple(self, row_dict: Dict[str, Any]) -> bytes:
        """Serialize dictionary row into binary payload."""
        parts = []
        for col in self.columns:
            val = row_dict.get(col.name)

            if col.col_type == "INT":
                ival = int(val) if val is not None else 0
                parts.append(struct.pack("!i", ival))
            elif col.col_type == "FLOAT":
                fval = float(val) if val is not None else 0.0
                parts.append(struct.pack("!d", fval))
            elif col.col_type == "BOOLEAN":
                bval = 1 if bool(val) else 0
                parts.append(struct.pack("!B", bval))
            elif col.col_type == "VARCHAR":
                sval = str(val) if val is not None else ""
                s_bytes = sval.encode('utf-8')[:col.max_length]
                # Length prefix (2 bytes) + string content
                parts.append(struct.pack("!H", len(s_bytes)) + s_bytes)
            else:
                raise ValueError(f"Unsupported column type: {col.col_type}")

        return b"".join(parts)

    def decode_tuple(self, raw_bytes: bytes) -> Dict[str, Any]:
        """Deserialize binary payload into dictionary row."""
        offset = 0
        row = {}
        for col in self.columns:
            if col.col_type == "INT":
                val = struct.unpack_from("!i", raw_bytes, offset)[0]
                offset += 4
            elif col.col_type == "FLOAT":
                val = struct.unpack_from("!d", raw_bytes, offset)[0]
                offset += 8
            elif col.col_type == "BOOLEAN":
                val = bool(struct.unpack_from("!B", raw_bytes, offset)[0])
                offset += 1
            elif col.col_type == "VARCHAR":
                strlen = struct.unpack_from("!H", raw_bytes, offset)[0]
                offset += 2
                val = raw_bytes[offset : offset + strlen].decode('utf-8', errors='replace')
                offset += strlen
            else:
                val = None
            row[col.name] = val
        return row
