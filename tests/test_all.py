"""
Unit and Integration Test Suite for MiniDB.
"""

import unittest
import os
import shutil
from minidb.storage.page import SlottedPage, PAGE_SIZE
from minidb.storage.disk_manager import DiskManager
from minidb.storage.buffer_pool import BufferPoolManager
from minidb.indexing.b_tree import BTreeIndex
from minidb.indexing.hash_index import HashIndex
from minidb.catalog.schema import Column, TableSchema
from minidb.catalog.catalog import Catalog
from minidb.parser.parser import parse_sql
from minidb.engine import DatabaseEngine


class TestMiniDB(unittest.TestCase):

    def setUp(self):
        self.test_dir = "./tmp_test_db"
        os.makedirs(self.test_dir, exist_ok=True)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_slotted_page(self):
        page = SlottedPage(page_id=1)
        data1 = b"Hello MiniDB"
        data2 = b"Second Record Payload"

        slot1 = page.insert_tuple(data1)
        slot2 = page.insert_tuple(data2)

        self.assertEqual(slot1, 0)
        self.assertEqual(slot2, 1)

        self.assertEqual(page.read_tuple(slot1), data1)
        self.assertEqual(page.read_tuple(slot2), data2)

        page.delete_tuple(slot1)
        self.assertIsNone(page.read_tuple(slot1))

    def test_btree_index(self):
        btree = BTreeIndex(max_keys=4)
        records = [(10, (0, 1)), (20, (0, 2)), (5, (0, 3)), (15, (0, 4)), (25, (0, 5)), (30, (0, 6))]

        for k, rid in records:
            btree.insert(k, rid)

        self.assertEqual(btree.search(15), [(0, 4)])
        self.assertEqual(btree.search(99), [])

        # Range search [10, 25]
        range_res = btree.range_search(10, 25)
        keys = [k for k, rid in range_res]
        self.assertEqual(keys, [10, 15, 20, 25])

    def test_hash_index(self):
        h_idx = HashIndex(bucket_capacity=2)
        h_idx.insert("alpha", (0, 1))
        h_idx.insert("beta", (0, 2))
        h_idx.insert("gamma", (0, 3))
        h_idx.insert("delta", (0, 4))

        self.assertEqual(h_idx.search("alpha"), [(0, 1)])
        self.assertEqual(h_idx.search("beta"), [(0, 2)])
        self.assertEqual(h_idx.search("nonexistent"), [])

    def test_sql_execution_end_to_end(self):
        engine = DatabaseEngine(data_dir=self.test_dir)

        # 1. Create table
        r1 = engine.execute_sql("CREATE TABLE users (id INT PRIMARY KEY, name VARCHAR(30), age INT)")
        self.assertIn("created successfully", r1["message"])

        # 2. Create indices
        engine.execute_sql("CREATE INDEX idx_users_id ON users (id) USING BTREE")
        engine.execute_sql("CREATE INDEX idx_users_name ON users (name) USING HASH")

        # 3. Insert records
        engine.execute_sql("INSERT INTO users VALUES (1, 'Alice', 25)")
        engine.execute_sql("INSERT INTO users VALUES (2, 'Bob', 30)")
        engine.execute_sql("INSERT INTO users VALUES (3, 'Charlie', 35)")

        # 4. Query with BTree Index Scan
        q1 = engine.execute_sql("SELECT * FROM users WHERE id = 2")
        self.assertEqual(len(q1["rows"]), 1)
        self.assertEqual(q1["rows"][0]["name"], "Bob")
        self.assertEqual(q1["plan_tree"]["name"], "Projection (*)")

        # 5. Query with Hash Index Scan
        q2 = engine.execute_sql("SELECT * FROM users WHERE name = 'Alice'")
        self.assertEqual(len(q2["rows"]), 1)
        self.assertEqual(q2["rows"][0]["age"], 25)

        # 6. Update
        engine.execute_sql("UPDATE users SET age = 26 WHERE name = 'Alice'")
        q3 = engine.execute_sql("SELECT * FROM users WHERE id = 1")
        self.assertEqual(q3["rows"][0]["age"], 26)

        # 7. Delete
        engine.execute_sql("DELETE FROM users WHERE id = 3")
        q4 = engine.execute_sql("SELECT * FROM users")
        self.assertEqual(len(q4["rows"]), 2)

    def test_aggregates_and_expressions(self):
        engine = DatabaseEngine(data_dir=self.test_dir)
        engine.execute_sql("CREATE TABLE items (id INT PRIMARY KEY, title VARCHAR(40), price FLOAT)")
        engine.execute_sql("INSERT INTO items VALUES (1, 'Apple Watch', 299.99)")
        engine.execute_sql("INSERT INTO items VALUES (2, 'AirPods Pro', 199.99)")
        engine.execute_sql("INSERT INTO items VALUES (3, 'Anker Charger', 29.99)")

        # Aggregates
        q_cnt = engine.execute_sql("SELECT COUNT(*) FROM items")
        self.assertEqual(q_cnt["rows"][0]["COUNT(*)"], 3)

        q_sum = engine.execute_sql("SELECT SUM(price), AVG(price) FROM items")
        self.assertAlmostEqual(q_sum["rows"][0]["SUM(price)"], 529.97, places=2)

        # LIKE expression
        q_like = engine.execute_sql("SELECT * FROM items WHERE title LIKE 'Air%'")
        self.assertEqual(len(q_like["rows"]), 1)
        self.assertEqual(q_like["rows"][0]["title"], "AirPods Pro")

        # IN expression
        q_in = engine.execute_sql("SELECT * FROM items WHERE id IN (1, 3)")
        self.assertEqual(len(q_in["rows"]), 2)

    def test_buffer_pool_eviction(self):
        disk_mgr = DiskManager(f"{self.test_dir}/evict_test.db")
        bp = BufferPoolManager(disk_mgr, capacity=2)

        p1 = bp.new_page(1)
        pid1 = p1.page_id
        bp.unpin_page(pid1, is_dirty=True)

        p2 = bp.new_page(1)
        pid2 = p2.page_id
        bp.unpin_page(pid2, is_dirty=True)

        # Triggers eviction of pid1
        p3 = bp.new_page(1)
        pid3 = p3.page_id

        self.assertNotIn(pid1, bp.page_table)
        self.assertIn(pid2, bp.page_table)
        self.assertIn(pid3, bp.page_table)


if __name__ == "__main__":
    unittest.main()
