"""
Volcano Iterator Model Query Execution Operators for MiniDB.
"""

from typing import Optional, Dict, Any, List, Tuple
from minidb.catalog.catalog import TableMetadata
from minidb.parser.ast_nodes import Expr
from minidb.execution.types import evaluate_expr


class Operator:
    """Base Volcano Operator interface."""

    def open(self):
        pass

    def next(self) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def close(self):
        pass

    def get_plan_tree(self) -> dict:
        """Return execution node hierarchy for visualizer profiling."""
        return {"name": self.__class__.__name__, "children": []}


class SeqScanOperator(Operator):
    """Full Sequential Table Scan Operator."""

    def __init__(self, table_meta: TableMetadata):
        self.meta = table_meta
        self.curr_page_id = 0
        self.curr_slot_id = 0

    def open(self):
        self.curr_page_id = 0
        self.curr_slot_id = 0

    def next(self) -> Optional[Dict[str, Any]]:
        while self.curr_page_id < self.meta.disk_mgr.num_pages:
            page = self.meta.buffer_pool.fetch_page(self.curr_page_id)
            if not page:
                self.curr_page_id += 1
                self.curr_slot_id = 0
                continue

            while self.curr_slot_id < page.num_slots:
                slot_id = self.curr_slot_id
                self.curr_slot_id += 1
                raw = page.read_tuple(slot_id)
                if raw is not None:
                    row = self.meta.schema.decode_tuple(raw)
                    row["__rid__"] = (self.curr_page_id, slot_id)
                    self.meta.buffer_pool.unpin_page(self.curr_page_id, is_dirty=False)
                    return row

            self.meta.buffer_pool.unpin_page(self.curr_page_id, is_dirty=False)
            self.curr_page_id += 1
            self.curr_slot_id = 0

        return None

    def get_plan_tree(self) -> dict:
        return {
            "name": "Sequential Scan",
            "table": self.meta.schema.table_name,
            "cost": f"O(N) - Pages: {self.meta.disk_mgr.num_pages}",
            "children": []
        }


class BTreeIndexScanOperator(Operator):
    """B+ Tree Index Scan Operator."""

    def __init__(self, table_meta: TableMetadata, col_name: str, op: str, target_val: Any, btree_index):
        self.meta = table_meta
        self.col_name = col_name
        self.op = op
        self.target_val = target_val
        self.btree_index = btree_index
        self.rids: List[Tuple[int, int]] = []
        self.rid_idx = 0

    def open(self):
        self.rid_idx = 0
        if self.op == "=":
            self.rids = self.btree_index.search(self.target_val)
        elif self.op in (">", ">="):
            pairs = self.btree_index.range_search(self.target_val, None)
            if self.op == ">":
                self.rids = [rid for k, rid in pairs if k > self.target_val]
            else:
                self.rids = [rid for k, rid in pairs]
        elif self.op in ("<", "<="):
            pairs = self.btree_index.range_search(None, self.target_val)
            if self.op == "<":
                self.rids = [rid for k, rid in pairs if k < self.target_val]
            else:
                self.rids = [rid for k, rid in pairs]
        else:
            self.rids = []

    def next(self) -> Optional[Dict[str, Any]]:
        while self.rid_idx < len(self.rids):
            page_id, slot_id = self.rids[self.rid_idx]
            self.rid_idx += 1

            page = self.meta.buffer_pool.fetch_page(page_id)
            if page:
                raw = page.read_tuple(slot_id)
                self.meta.buffer_pool.unpin_page(page_id, is_dirty=False)
                if raw is not None:
                    row = self.meta.schema.decode_tuple(raw)
                    row["__rid__"] = (page_id, slot_id)
                    return row
        return None

    def get_plan_tree(self) -> dict:
        return {
            "name": "B+ Tree Index Scan",
            "column": self.col_name,
            "operator": self.op,
            "cost": f"O(log N + K) - Matched RIDs: {len(self.rids)}",
            "children": []
        }


class HashIndexScanOperator(Operator):
    """Hash Index Scan Operator."""

    def __init__(self, table_meta: TableMetadata, col_name: str, target_val: Any, hash_index):
        self.meta = table_meta
        self.col_name = col_name
        self.target_val = target_val
        self.hash_index = hash_index
        self.rids: List[Tuple[int, int]] = []
        self.rid_idx = 0

    def open(self):
        self.rid_idx = 0
        self.rids = self.hash_index.search(self.target_val)

    def next(self) -> Optional[Dict[str, Any]]:
        while self.rid_idx < len(self.rids):
            page_id, slot_id = self.rids[self.rid_idx]
            self.rid_idx += 1

            page = self.meta.buffer_pool.fetch_page(page_id)
            if page:
                raw = page.read_tuple(slot_id)
                self.meta.buffer_pool.unpin_page(page_id, is_dirty=False)
                if raw is not None:
                    row = self.meta.schema.decode_tuple(raw)
                    row["__rid__"] = (page_id, slot_id)
                    return row
        return None

    def get_plan_tree(self) -> dict:
        return {
            "name": "Hash Index Scan",
            "column": self.col_name,
            "cost": f"O(1) Exact Lookup - Matched RIDs: {len(self.rids)}",
            "children": []
        }


class FilterOperator(Operator):
    """Evaluates predicate expression filter on child operator rows."""

    def __init__(self, child: Operator, predicate: Expr):
        self.child = child
        self.predicate = predicate

    def open(self):
        self.child.open()

    def next(self) -> Optional[Dict[str, Any]]:
        while True:
            row = self.child.next()
            if row is None:
                return None
            if evaluate_expr(self.predicate, row):
                return row

    def close(self):
        self.child.close()

    def get_plan_tree(self) -> dict:
        return {
            "name": "Filter Predicate",
            "children": [self.child.get_plan_tree()]
        }


class ProjectionOperator(Operator):
    """Filters requested output columns."""

    def __init__(self, child: Operator, columns: List[str]):
        self.child = child
        self.columns = columns

    def open(self):
        self.child.open()

    def next(self) -> Optional[Dict[str, Any]]:
        row = self.child.next()
        if row is None:
            return None

        if self.columns == ["*"]:
            # Omit internal __rid__ from output
            return {k: v for k, v in row.items() if k != "__rid__"}

        proj_row = {}
        for col in self.columns:
            # Case-insensitive column resolution
            matched = False
            for k, v in row.items():
                if k.lower() == col.lower():
                    proj_row[k] = v
                    matched = True
                    break
            if not matched:
                proj_row[col] = None
        return proj_row

    def close(self):
        self.child.close()

    def get_plan_tree(self) -> dict:
        return {
            "name": f"Projection ({', '.join(self.columns)})",
            "children": [self.child.get_plan_tree()]
        }


class SortOperator(Operator):
    """Sorts all rows yielded by child operator."""

    def __init__(self, child: Operator, sort_col: str, direction: str = "ASC"):
        self.child = child
        self.sort_col = sort_col
        self.reverse = direction.upper() == "DESC"
        self.sorted_rows: List[Dict[str, Any]] = []
        self.idx = 0

    def open(self):
        self.child.open()
        all_rows = []
        while True:
            r = self.child.next()
            if r is None:
                break
            all_rows.append(r)
        
        self.sorted_rows = sorted(
            all_rows,
            key=lambda x: (x.get(self.sort_col) is None, x.get(self.sort_col)),
            reverse=self.reverse
        )
        self.idx = 0

    def next(self) -> Optional[Dict[str, Any]]:
        if self.idx < len(self.sorted_rows):
            r = self.sorted_rows[self.idx]
            self.idx += 1
            return r
        return None

    def close(self):
        self.child.close()

    def get_plan_tree(self) -> dict:
        return {
            "name": f"Sort ({self.sort_col} {'DESC' if self.reverse else 'ASC'})",
            "children": [self.child.get_plan_tree()]
        }


class LimitOperator(Operator):
    """Limits output row count."""

    def __init__(self, child: Operator, limit: int):
        self.child = child
        self.limit = limit
        self.count = 0

    def open(self):
        self.child.open()
        self.count = 0

    def next(self) -> Optional[Dict[str, Any]]:
        if self.count >= self.limit:
            return None
        r = self.child.next()
        if r is not None:
            self.count += 1
        return r

    def close(self):
        self.child.close()

    def get_plan_tree(self) -> dict:
        return {
            "name": f"Limit ({self.limit})",
            "children": [self.child.get_plan_tree()]
        }


class AggregateOperator(Operator):
    """Computes SQL Aggregate functions (COUNT, SUM, AVG, MIN, MAX)."""

    def __init__(self, child: Operator, columns: List[str]):
        self.child = child
        self.columns = columns
        self.yielded = False
        self.result_row: Optional[Dict[str, Any]] = None

    def open(self):
        self.child.open()
        self.yielded = False

        has_agg = any("(" in col and col.endswith(")") for col in self.columns)
        if not has_agg:
            return

        rows = []
        while True:
            r = self.child.next()
            if r is None:
                break
            rows.append(r)

        res = {}
        for col_expr in self.columns:
            if "(" in col_expr and col_expr.endswith(")"):
                fn_name, arg = col_expr[:-1].split("(", 1)
                fn_name = fn_name.strip().upper()
                arg = arg.strip()

                if fn_name == "COUNT":
                    if arg == "*":
                        res[col_expr] = len(rows)
                    else:
                        res[col_expr] = sum(1 for r in rows if r.get(arg) is not None)
                elif fn_name in ("SUM", "AVG"):
                    vals = [r.get(arg) for r in rows if r.get(arg) is not None and isinstance(r.get(arg), (int, float))]
                    if fn_name == "SUM":
                        res[col_expr] = round(sum(vals), 4) if vals else 0
                    else:
                        res[col_expr] = round(sum(vals) / len(vals), 4) if vals else 0.0
                elif fn_name == "MIN":
                    vals = [r.get(arg) for r in rows if r.get(arg) is not None]
                    res[col_expr] = min(vals) if vals else None
                elif fn_name == "MAX":
                    vals = [r.get(arg) for r in rows if r.get(arg) is not None]
                    res[col_expr] = max(vals) if vals else None
                else:
                    res[col_expr] = None
            else:
                res[col_expr] = rows[0].get(col_expr) if rows else None

        self.result_row = res

    def next(self) -> Optional[Dict[str, Any]]:
        has_agg = any("(" in col and col.endswith(")") for col in self.columns)
        if has_agg:
            if not self.yielded and self.result_row is not None:
                self.yielded = True
                return self.result_row
            return None
        return self.child.next()

    def close(self):
        self.child.close()

    def get_plan_tree(self) -> dict:
        has_agg = any("(" in col and col.endswith(")") for col in self.columns)
        if has_agg:
            return {
                "name": f"Aggregate ({', '.join(self.columns)})",
                "children": [self.child.get_plan_tree()]
            }
        return self.child.get_plan_tree()
