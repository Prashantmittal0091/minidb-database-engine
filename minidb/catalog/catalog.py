"""
System Catalog Manager for MiniDB.

Maintains table schemas, active disk/buffer managers, and registered index objects.
"""

import os
from typing import Dict, Any, List, Optional, Union, Tuple
from minidb.catalog.schema import TableSchema, Column
from minidb.storage.disk_manager import DiskManager
from minidb.storage.buffer_pool import BufferPoolManager
from minidb.indexing.b_tree import BTreeIndex
from minidb.indexing.hash_index import HashIndex


class TableMetadata:
    """Holds runtime managers and metadata for a database table."""

    def __init__(self, schema: TableSchema, disk_mgr: DiskManager, buffer_pool: BufferPoolManager):
        self.schema: TableSchema = schema
        self.disk_mgr: DiskManager = disk_mgr
        self.buffer_pool: BufferPoolManager = buffer_pool
        # Index map: col_name -> (index_type: 'BTREE'|'HASH', index_obj)
        self.indices: Dict[str, Tuple[str, Union[BTreeIndex, HashIndex]]] = {}


class Catalog:
    """Global database metadata catalog."""

    def __init__(self):
        self.tables: Dict[str, TableMetadata] = {}

    def create_table(self, schema: TableSchema, disk_mgr: DiskManager, buffer_pool: BufferPoolManager) -> TableMetadata:
        """Register a new table in system catalog."""
        table_name = schema.table_name.lower()
        meta = TableMetadata(schema, disk_mgr, buffer_pool)
        self.tables[table_name] = meta
        return meta

    def get_table(self, table_name: str) -> Optional[TableMetadata]:
        """Fetch table metadata by name."""
        return self.tables.get(table_name.lower())

    def drop_table(self, table_name: str) -> bool:
        """Drop table from catalog and delete associated disk file."""
        t_name = table_name.lower()
        if t_name in self.tables:
            meta = self.tables[t_name]
            meta.buffer_pool.flush_all()
            db_path = meta.disk_mgr.db_filepath
            del self.tables[t_name]
            if os.path.exists(db_path):
                try:
                    os.remove(db_path)
                except OSError:
                    pass
            return True
        return False

    def create_index(self, table_name: str, col_name: str, index_type: str = "BTREE") -> Optional[Union[BTreeIndex, HashIndex]]:
        """Create B+ Tree or Hash index on a table column."""
        meta = self.get_table(table_name)
        if not meta or col_name not in meta.schema.col_map:
            return None

        idx_type = index_type.upper()
        if idx_type == "BTREE":
            index_obj = BTreeIndex(max_keys=4)
        elif idx_type == "HASH":
            index_obj = HashIndex(bucket_capacity=4)
        else:
            raise ValueError(f"Unknown index type: {index_type}")

        meta.indices[col_name] = (idx_type, index_obj)

        # Build index over existing records in table
        # We perform a full table scan to populate index
        page_id = 0
        while page_id < meta.disk_mgr.num_pages:
            page = meta.buffer_pool.fetch_page(page_id)
            if page:
                for slot_id in range(page.num_slots):
                    raw = page.read_tuple(slot_id)
                    if raw is not None:
                        row = meta.schema.decode_tuple(raw)
                        val = row.get(col_name)
                        if val is not None:
                            rid = (page_id, slot_id)
                            index_obj.insert(val, rid)
                meta.buffer_pool.unpin_page(page_id, is_dirty=False)
            page_id += 1

        return index_obj

    def get_index(self, table_name: str, col_name: str) -> Optional[Tuple[str, Union[BTreeIndex, HashIndex]]]:
        """Fetch index for (table_name, col_name) if available."""
        meta = self.get_table(table_name)
        if meta and col_name in meta.indices:
            return meta.indices[col_name]
        return None

    def list_tables(self) -> List[dict]:
        """Return table summary for schema inspector."""
        res = []
        for name, meta in self.tables.items():
            res.append({
                "name": meta.schema.table_name,
                "columns": [col.to_dict() for col in meta.schema.columns],
                "num_pages": meta.disk_mgr.num_pages,
                "indices": list(meta.indices.keys())
            })
        return res
