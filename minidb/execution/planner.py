"""
Query Execution Planner for MiniDB.

Transforms AST nodes into optimal execution plans and handles DML/DDL execution.
"""

import time
from typing import Dict, Any, List, Tuple, Optional
from minidb.catalog.catalog import Catalog, TableMetadata
from minidb.catalog.schema import TableSchema, Column
from minidb.storage.disk_manager import DiskManager
from minidb.storage.buffer_pool import BufferPoolManager
from minidb.parser.ast_nodes import (
    ASTNode, CreateTableStmt, CreateIndexStmt, InsertStmt,
    SelectStmt, UpdateStmt, DeleteStmt, DropTableStmt, ExplainStmt,
    BinaryOpExpr, ColumnExpr, LiteralExpr
)
from minidb.execution.operators import (
    Operator, SeqScanOperator, BTreeIndexScanOperator, HashIndexScanOperator,
    FilterOperator, ProjectionOperator, SortOperator, LimitOperator, AggregateOperator
)
from minidb.execution.types import evaluate_expr


class QueryResult:
    def __init__(self, columns: List[str], rows: List[Dict[str, Any]], execution_time_ms: float, plan_tree: Optional[dict] = None, message: Optional[str] = None):
        self.columns = columns
        self.rows = rows
        self.execution_time_ms = execution_time_ms
        self.plan_tree = plan_tree
        self.message = message

    def to_dict(self) -> dict:
        return {
            "columns": self.columns,
            "rows": self.rows,
            "row_count": len(self.rows),
            "execution_time_ms": round(self.execution_time_ms, 3),
            "plan_tree": self.plan_tree,
            "message": self.message
        }


class Planner:
    """Translates SQL AST into executable operator pipelines and executes DDL/DML."""

    def __init__(self, catalog: Catalog, base_dir: str = "./db_data"):
        self.catalog = catalog
        self.base_dir = base_dir

    def execute(self, ast: ASTNode) -> QueryResult:
        start_time = time.perf_counter()

        if isinstance(ast, ExplainStmt):
            plan_op = self.build_select_plan(ast.statement) if isinstance(ast.statement, SelectStmt) else None
            plan_tree = plan_op.get_plan_tree() if plan_op else {"info": "EXPLAIN unsupported for this statement"}
            elapsed = (time.perf_counter() - start_time) * 1000.0
            return QueryResult(
                columns=["Query Plan"],
                rows=[{"Query Plan": f"Visual Plan generated for {ast.statement.__class__.__name__}"}],
                execution_time_ms=elapsed,
                plan_tree=plan_tree
            )

        elif isinstance(ast, CreateTableStmt):
            cols = [Column(c.name, c.col_type, c.max_length, c.primary_key) for c in ast.columns]
            schema = TableSchema(ast.table_name, cols)
            db_path = f"{self.base_dir}/{ast.table_name.lower()}.db"
            disk_mgr = DiskManager(db_path)
            buf_mgr = BufferPoolManager(disk_mgr, capacity=16)
            
            # Create first page if empty
            if disk_mgr.num_pages == 0:
                buf_mgr.new_page(1)
                buf_mgr.flush_all()

            self.catalog.create_table(schema, disk_mgr, buf_mgr)
            elapsed = (time.perf_counter() - start_time) * 1000.0
            return QueryResult([], [], elapsed, message=f"Table '{ast.table_name}' created successfully.")

        elif isinstance(ast, CreateIndexStmt):
            index_obj = self.catalog.create_index(ast.table_name, ast.column_name, ast.index_type)
            elapsed = (time.perf_counter() - start_time) * 1000.0
            if index_obj:
                return QueryResult([], [], elapsed, message=f"Index '{ast.index_name}' ({ast.index_type}) created on {ast.table_name}({ast.column_name}).")
            else:
                return QueryResult([], [], elapsed, message=f"Failed to create index. Check table/column existence.")

        elif isinstance(ast, InsertStmt):
            meta = self.catalog.get_table(ast.table_name)
            if not meta:
                raise ValueError(f"Table '{ast.table_name}' does not exist.")

            # Map values to columns
            row_dict = {}
            if ast.columns:
                for col, val in zip(ast.columns, ast.values):
                    row_dict[col] = val
            else:
                for col, val in zip(meta.schema.columns, ast.values):
                    row_dict[col.name] = val

            encoded = meta.schema.encode_tuple(row_dict)

            # Find page with free space or create new page
            page_id = meta.disk_mgr.num_pages - 1
            if page_id < 0:
                page = meta.buffer_pool.new_page(1)
                page_id = page.page_id
            else:
                page = meta.buffer_pool.fetch_page(page_id)

            slot_id = page.insert_tuple(encoded)
            if slot_id is None:
                # Page full, create new page
                meta.buffer_pool.unpin_page(page_id, is_dirty=False)
                new_page = meta.buffer_pool.new_page(1)
                page_id = new_page.page_id
                slot_id = new_page.insert_tuple(encoded)

            meta.buffer_pool.unpin_page(page_id, is_dirty=True)
            meta.buffer_pool.flush_all()

            # Update indices
            rid = (page_id, slot_id)
            for col_name, (idx_type, idx_obj) in meta.indices.items():
                if col_name in row_dict:
                    idx_obj.insert(row_dict[col_name], rid)

            elapsed = (time.perf_counter() - start_time) * 1000.0
            return QueryResult([], [], elapsed, message=f"1 row inserted into '{ast.table_name}' at RID ({page_id}, {slot_id}).")

        elif isinstance(ast, SelectStmt):
            op_pipeline = self.build_select_plan(ast)
            op_pipeline.open()
            rows = []
            while True:
                r = op_pipeline.next()
                if r is None:
                    break
                rows.append(r)
            op_pipeline.close()

            elapsed = (time.perf_counter() - start_time) * 1000.0
            cols = list(rows[0].keys()) if rows else (ast.columns if ast.columns != ["*"] else ["Result"])
            return QueryResult(cols, rows, elapsed, plan_tree=op_pipeline.get_plan_tree())

        elif isinstance(ast, UpdateStmt):
            meta = self.catalog.get_table(ast.table_name)
            if not meta:
                raise ValueError(f"Table '{ast.table_name}' does not exist.")

            scan = SeqScanOperator(meta)
            scan.open()
            updated_count = 0
            while True:
                row = scan.next()
                if row is None:
                    break
                if ast.where_clause is None or evaluate_expr(ast.where_clause, row):
                    pid, slot = row["__rid__"]
                    # Apply updates
                    for col_name, new_val in ast.assignments:
                        row[col_name] = new_val
                    
                    new_bytes = meta.schema.encode_tuple({k: v for k, v in row.items() if k != "__rid__"})
                    page = meta.buffer_pool.fetch_page(pid)
                    if page:
                        page.update_tuple(slot, new_bytes)
                        meta.buffer_pool.unpin_page(pid, is_dirty=True)
                        # Re-index if indexed column changed
                        for cname, (itype, iobj) in meta.indices.items():
                            if cname in row:
                                iobj.insert(row[cname], (pid, slot))
                        updated_count += 1
            scan.close()
            meta.buffer_pool.flush_all()
            elapsed = (time.perf_counter() - start_time) * 1000.0
            return QueryResult([], [], elapsed, message=f"{updated_count} rows updated in '{ast.table_name}'.")

        elif isinstance(ast, DeleteStmt):
            meta = self.catalog.get_table(ast.table_name)
            if not meta:
                raise ValueError(f"Table '{ast.table_name}' does not exist.")

            scan = SeqScanOperator(meta)
            scan.open()
            deleted_count = 0
            while True:
                row = scan.next()
                if row is None:
                    break
                if ast.where_clause is None or evaluate_expr(ast.where_clause, row):
                    pid, slot = row["__rid__"]
                    page = meta.buffer_pool.fetch_page(pid)
                    if page:
                        page.delete_tuple(slot)
                        meta.buffer_pool.unpin_page(pid, is_dirty=True)
                        deleted_count += 1
            scan.close()
            meta.buffer_pool.flush_all()
            elapsed = (time.perf_counter() - start_time) * 1000.0
            return QueryResult([], [], elapsed, message=f"{deleted_count} rows deleted from '{ast.table_name}'.")

        elif isinstance(ast, DropTableStmt):
            ok = self.catalog.drop_table(ast.table_name)
            elapsed = (time.perf_counter() - start_time) * 1000.0
            return QueryResult([], [], elapsed, message=f"Table '{ast.table_name}' dropped." if ok else f"Table not found.")

        else:
            raise ValueError(f"Unsupported AST node {type(ast)}")

    def build_select_plan(self, ast: SelectStmt) -> Operator:
        meta = self.catalog.get_table(ast.table_name)
        if not meta:
            raise ValueError(f"Table '{ast.table_name}' does not exist.")

        # Analyze index eligibility from WHERE predicate
        root_scan: Optional[Operator] = None

        if ast.where_clause and isinstance(ast.where_clause, BinaryOpExpr):
            left = ast.where_clause.left
            op = ast.where_clause.op
            right = ast.where_clause.right

            if isinstance(left, ColumnExpr) and isinstance(right, LiteralExpr):
                col_name = left.name
                target_val = right.value
                idx_info = self.catalog.get_index(ast.table_name, col_name)

                if idx_info:
                    idx_type, idx_obj = idx_info
                    if idx_type == "HASH" and op == "=":
                        root_scan = HashIndexScanOperator(meta, col_name, target_val, idx_obj)
                    elif idx_type == "BTREE" and op in ("=", ">", "<", ">=", "<="):
                        root_scan = BTreeIndexScanOperator(meta, col_name, op, target_val, idx_obj)

        if root_scan is None:
            root_scan = SeqScanOperator(meta)
            if ast.where_clause:
                root_scan = FilterOperator(root_scan, ast.where_clause)

        curr: Operator = root_scan

        # Add Sorting if specified
        if ast.order_by:
            col, direction = ast.order_by
            curr = SortOperator(curr, col, direction)

        # Add Limit if specified
        if ast.limit:
            curr = LimitOperator(curr, ast.limit)

        # Add AggregateOperator if aggregate functions present
        has_agg = any("(" in col and col.endswith(")") for col in ast.columns)
        if has_agg:
            curr = AggregateOperator(curr, ast.columns)
        else:
            # Add Projection
            curr = ProjectionOperator(curr, ast.columns)

        return curr
