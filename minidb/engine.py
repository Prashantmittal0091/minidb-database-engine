"""
Top-level Database Engine interface for MiniDB.

Provides unified SQL query execution, pre-populated demo datasets,
visualizer inspection methods, and indexing performance benchmarks.
"""

import os
import random
import time
from typing import Dict, Any, List, Optional
from minidb.catalog.catalog import Catalog
from minidb.catalog.schema import Column, TableSchema
from minidb.storage.disk_manager import DiskManager
from minidb.storage.buffer_pool import BufferPoolManager
from minidb.parser.parser import parse_sql
from minidb.execution.planner import Planner, QueryResult


class DatabaseEngine:
    """Core MiniDB DBMS Instance."""

    def __init__(self, data_dir: str = "./db_data"):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.catalog = Catalog()
        self.planner = Planner(self.catalog, base_dir=data_dir)

    def execute_sql(self, sql_string: str) -> dict:
        """Parse and execute a raw SQL query string."""
        # Strip comments and trailing semicolons
        cleaned = sql_string.strip().rstrip(';')
        if not cleaned:
            return QueryResult([], [], 0.0, message="Empty query").to_dict()

        try:
            ast = parse_sql(cleaned)
            res = self.planner.execute(ast)
            return res.to_dict()
        except Exception as e:
            return {
                "columns": [],
                "rows": [],
                "row_count": 0,
                "execution_time_ms": 0.0,
                "error": str(e),
                "message": f"Error: {str(e)}"
            }

    def seed_sample_data(self):
        """Populate database with rich sample data for demonstration & benchmarks."""
        # Create 'products' table
        self.execute_sql("""
            CREATE TABLE products (
                id INT PRIMARY KEY,
                name VARCHAR(50),
                category VARCHAR(30),
                price FLOAT,
                stock INT
            )
        """)

        # Create indices on products
        self.execute_sql("CREATE INDEX idx_products_id ON products (id) USING BTREE")
        self.execute_sql("CREATE INDEX idx_products_category ON products (category) USING HASH")

        categories = ["Electronics", "Books", "Clothing", "Home", "Sports", "Toys"]
        product_names = ["Wireless Mouse", "Mechanical Keyboard", "HD Monitor", "Gaming Headset",
                         "USB-C Cable", "Desk Lamp", "Ergonomic Chair", "Backpack", "Smart Watch", "Water Bottle"]

        # Insert 100 sample products
        for i in range(1, 101):
            p_name = f"{random.choice(product_names)} {i}"
            cat = random.choice(categories)
            price = round(random.uniform(9.99, 499.99), 2)
            stock = random.randint(5, 200)
            self.execute_sql(f"INSERT INTO products VALUES ({i}, '{p_name}', '{cat}', {price}, {stock})")

        # Create 'users' table
        self.execute_sql("""
            CREATE TABLE users (
                id INT PRIMARY KEY,
                username VARCHAR(40),
                age INT,
                is_active BOOLEAN
            )
        """)
        self.execute_sql("CREATE INDEX idx_users_id ON users (id) USING BTREE")

        users_list = [
            (1, "Alice_Smith", 28, "TRUE"),
            (2, "Bob_Jones", 34, "TRUE"),
            (3, "Charlie_Brown", 22, "FALSE"),
            (4, "Diana_Prince", 29, "TRUE"),
            (5, "Evan_Wright", 41, "TRUE"),
            (6, "Fiona_Gallagher", 19, "FALSE"),
            (7, "George_Clark", 55, "TRUE"),
            (8, "Hannah_Abbott", 27, "TRUE")
        ]

        for u in users_list:
            self.execute_sql(f"INSERT INTO users VALUES ({u[0]}, '{u[1]}', {u[2]}, {u[3]})")

    def get_btree_visual(self, table_name: str, col_name: str) -> Optional[dict]:
        """Fetch JSON visual representation of B+ Tree index."""
        idx_info = self.catalog.get_index(table_name, col_name)
        if idx_info and idx_info[0] == "BTREE":
            return idx_info[1].get_visual_tree()
        return None

    def get_hash_visual(self, table_name: str, col_name: str) -> Optional[dict]:
        """Fetch JSON visual representation of Hash Index."""
        idx_info = self.catalog.get_index(table_name, col_name)
        if idx_info and idx_info[0] == "HASH":
            return idx_info[1].get_visual_hash()
        return None

    def get_buffer_pool_info(self, table_name: str) -> Optional[dict]:
        """Fetch active buffer pool state for table."""
        meta = self.catalog.get_table(table_name)
        if meta:
            return meta.buffer_pool.get_inspector_info()
        return None

    def get_page_info(self, table_name: str, page_id: int) -> Optional[dict]:
        """Fetch slotted page internals."""
        meta = self.catalog.get_table(table_name)
        if meta:
            page = meta.buffer_pool.fetch_page(page_id)
            if page:
                info = page.get_inspector_info()
                meta.buffer_pool.unpin_page(page_id, is_dirty=False)
                return info
        return None

    def run_benchmark_comparison(self, num_records: int = 500) -> dict:
        """
        Run performance benchmark comparing:
        1. Full Sequential Table Scan
        2. B+ Tree Index Scan (O(log N))
        3. Extendible Hash Index Scan (O(1))
        """
        table_name = "benchmark_test"
        self.execute_sql(f"DROP TABLE {table_name}")
        self.execute_sql(f"CREATE TABLE {table_name} (id INT PRIMARY KEY, val VARCHAR(20))")

        # Create BTree and Hash indices
        self.execute_sql(f"CREATE INDEX idx_bm_btree ON {table_name} (id) USING BTREE")
        self.execute_sql(f"CREATE INDEX idx_bm_hash ON {table_name} (id) USING HASH")

        # Insert records
        for i in range(1, num_records + 1):
            self.execute_sql(f"INSERT INTO {table_name} VALUES ({i}, 'val_{i}')")

        target_id = random.randint(1, num_records)

        # 1. Benchmark Sequential Scan (Force by bypassing index)
        meta = self.catalog.get_table(table_name)
        t0 = time.perf_counter()
        scan = self.planner.catalog.get_table(table_name)
        from minidb.execution.operators import SeqScanOperator
        seq_op = SeqScanOperator(meta)
        seq_op.open()
        found_seq = None
        while True:
            r = seq_op.next()
            if r is None:
                break
            if r.get("id") == target_id:
                found_seq = r
                break
        t_seq = (time.perf_counter() - t0) * 1000.0

        # 2. Benchmark B+ Tree Scan
        t0 = time.perf_counter()
        btree_res = self.execute_sql(f"SELECT * FROM {table_name} WHERE id = {target_id}")
        t_btree = btree_res["execution_time_ms"]

        # 3. Benchmark Hash Scan
        idx_hash = meta.indices["id"][1]
        from minidb.execution.operators import HashIndexScanOperator
        t0 = time.perf_counter()
        hash_op = HashIndexScanOperator(meta, "id", target_id, idx_hash)
        hash_op.open()
        found_hash = hash_op.next()
        t_hash = (time.perf_counter() - t0) * 1000.0

        return {
            "record_count": num_records,
            "target_key": target_id,
            "seq_scan_ms": round(t_seq, 4),
            "btree_scan_ms": round(t_btree, 4),
            "hash_scan_ms": round(t_hash, 4),
            "speedup_btree": round(t_seq / max(t_btree, 0.0001), 2),
            "speedup_hash": round(t_seq / max(t_hash, 0.0001), 2)
        }
