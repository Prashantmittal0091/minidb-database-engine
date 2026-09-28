"""
Interactive CLI / REPL Shell for MiniDB.

Provides SQL query execution, tabular ASCII output formatting,
meta commands (\\d, \\dt, \\di, \\bp, \\benchmark, \\help), and query timing.
"""

import sys
import os
from typing import List, Dict, Any
from minidb.engine import DatabaseEngine


def print_ascii_table(columns: List[str], rows: List[Dict[str, Any]]):
    """Render rows in clean ASCII border table format."""
    if not columns:
        return

    # Calculate column widths
    col_widths = {col: len(str(col)) for col in columns}
    for row in rows:
        for col in columns:
            val_str = str(row.get(col, ""))
            if len(val_str) > col_widths[col]:
                col_widths[col] = len(val_str)

    # Format header
    header_cells = [f" {col.ljust(col_widths[col])} " for col in columns]
    header_line = "|" + "|".join(header_cells) + "|"
    divider = "+" + "+".join(["-" * (col_widths[col] + 2) for col in columns]) + "+"

    print(divider)
    print(header_line)
    print(divider)

    for row in rows:
        cells = [f" {str(row.get(col, '')).ljust(col_widths[col])} " for col in columns]
        print("|" + "|".join(cells) + "|")

    print(divider)


def run_cli():
    """Start interactive MiniDB REPL."""
    print("=" * 65)
    print(" MiniDB - Lightweight Database Engine from Scratch (v1.0)")
    print(" Type '\\help' for meta-commands or '\\exit' to quit.")
    print("=" * 65)

    engine = DatabaseEngine()
    engine.seed_sample_data()
    print(" [✓] Sample dataset 'products' and 'users' loaded successfully.\n")

    sql_buffer = []

    while True:
        try:
            prompt = "minidb> " if not sql_buffer else "   ...  "
            line = input(prompt).strip()

            if not line:
                continue

            # Meta-commands
            if line.startswith("\\"):
                cmd_parts = line.split()
                meta_cmd = cmd_parts[0].lower()

                if meta_cmd in ("\\exit", "\\quit"):
                    print("Goodbye!")
                    break

                elif meta_cmd in ("\\dt", "\\d"):
                    if len(cmd_parts) > 1:
                        tbl_name = cmd_parts[1]
                        meta = engine.catalog.get_table(tbl_name)
                        if meta:
                            print(f"\nTable: {meta.schema.table_name}")
                            cols_data = []
                            for c in meta.schema.columns:
                                cols_data.append({
                                    "Column": c.name,
                                    "Type": c.col_type,
                                    "Length": c.max_length,
                                    "Primary Key": "YES" if c.primary_key else "NO"
                                })
                            print_ascii_table(["Column", "Type", "Length", "Primary Key"], cols_data)
                        else:
                            print(f"Table '{tbl_name}' not found.")
                    else:
                        tables = engine.catalog.list_tables()
                        print("\nList of relations:")
                        print_ascii_table(["Name", "Columns Count", "Disk Pages", "Indices"], [
                            {
                                "Name": t["name"],
                                "Columns Count": len(t["columns"]),
                                "Disk Pages": t["num_pages"],
                                "Indices": ", ".join(t["indices"]) if t["indices"] else "None"
                            } for t in tables
                        ])

                elif meta_cmd == "\\di":
                    tables = engine.catalog.list_tables()
                    idx_rows = []
                    for t in tables:
                        for col in t["indices"]:
                            idx_info = engine.catalog.get_index(t["name"], col)
                            if idx_info:
                                idx_rows.append({
                                    "Table": t["name"],
                                    "Column": col,
                                    "Index Type": idx_info[0]
                                })
                    print("\nList of registered indices:")
                    print_ascii_table(["Table", "Column", "Index Type"], idx_rows)

                elif meta_cmd == "\\bp":
                    tbl_name = cmd_parts[1] if len(cmd_parts) > 1 else "products"
                    bp_info = engine.get_buffer_pool_info(tbl_name)
                    if bp_info:
                        print(f"\nBuffer Pool State for '{tbl_name}':")
                        print(f" Capacity: {bp_info['capacity']} frames | Used: {bp_info['used_frames']} | Hit Ratio: {bp_info['hit_ratio_percent']}%")
                        if bp_info['frames']:
                            print_ascii_table(["page_id", "page_type", "pin_count", "is_dirty", "free_bytes"], bp_info['frames'])
                    else:
                        print(f"Table '{tbl_name}' not found.")

                elif meta_cmd == "\\benchmark":
                    print("\nRunning indexing benchmark comparison (Sequential Scan vs B+ Tree vs Hash Index)...")
                    bm = engine.run_benchmark_comparison(num_records=500)
                    print(f" Benchmark Result (Dataset: {bm['record_count']} records, Search Target: {bm['target_key']}):")
                    print(f" ├─ Sequential Scan Time : {bm['seq_scan_ms']} ms")
                    print(f" ├─ B+ Tree Index Scan   : {bm['btree_scan_ms']} ms  ({bm['speedup_btree']}x faster)")
                    print(f" └─ Extendible Hash Scan : {bm['hash_scan_ms']} ms  ({bm['speedup_hash']}x faster)\n")

                elif meta_cmd == "\\help":
                    print("\nMiniDB Meta-Commands:")
                    print("  \\dt, \\d          : List all tables")
                    print("  \\d <table_name>  : Describe table schema")
                    print("  \\di              : List registered indices")
                    print("  \\bp <table_name> : Inspect buffer pool frame status")
                    print("  \\benchmark       : Run performance benchmark comparison")
                    print("  \\help            : Show this help message")
                    print("  \\exit, \\quit     : Exit MiniDB shell\n")

                else:
                    print(f"Unknown meta-command '{meta_cmd}'. Type '\\help' for available commands.")
                continue

            # Accumulate SQL
            sql_buffer.append(line)
            if line.endswith(";"):
                sql = " ".join(sql_buffer)
                sql_buffer = []

                res = engine.execute_sql(sql)
                if "error" in res:
                    print(f"ERROR: {res['error']}")
                elif res.get("message"):
                    print(f"{res['message']} ({res['execution_time_ms']} ms)")
                else:
                    print_ascii_table(res["columns"], res["rows"])
                    print(f"({res['row_count']} row{'s' if res['row_count'] != 1 else ''} retrieved in {res['execution_time_ms']} ms)")
                    if res.get("plan_tree"):
                        print(f"[Query Plan]: {res['plan_tree']['name']}")

        except KeyboardInterrupt:
            print("\nUse \\exit to quit.")
            sql_buffer = []
        except EOFError:
            break


if __name__ == "__main__":
    run_cli()
