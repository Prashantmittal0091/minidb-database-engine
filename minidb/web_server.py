"""
Flask Web Server for MiniDB DBMS Visualizer & Workbench.

Exposes REST APIs for SQL execution, live B+ Tree and Hash Index visual graphs,
slotted page byte inspector, buffer pool LRU metrics, and index benchmark runner.
"""

import os
from flask import Flask, jsonify, request, send_from_directory
from minidb.engine import DatabaseEngine

app = Flask(__name__, static_folder="web_ui")

# Global engine instance initialized with seed data
engine = DatabaseEngine(data_dir="./web_db_data")
engine.seed_sample_data()


@app.route("/")
def index():
    return send_from_directory("web_ui", "index.html")


@app.route("/<path:path>")
def static_files(path):
    return send_from_directory("web_ui", path)


@app.route("/api/query", methods=["POST"])
def execute_query():
    data = request.get_json() or {}
    sql = data.get("sql", "")
    res = engine.execute_sql(sql)
    return jsonify(res)


@app.route("/api/tables", methods=["GET"])
def list_tables():
    tables = engine.catalog.list_tables()
    return jsonify({"tables": tables})


@app.route("/api/visual/btree", methods=["GET"])
def get_btree_visual():
    table = request.args.get("table", "products")
    column = request.args.get("column", "id")
    tree = engine.get_btree_visual(table, column)
    return jsonify({"table": table, "column": column, "tree": tree})


@app.route("/api/visual/hash", methods=["GET"])
def get_hash_visual():
    table = request.args.get("table", "products")
    column = request.args.get("column", "category")
    hash_data = engine.get_hash_visual(table, column)
    return jsonify({"table": table, "column": column, "hash": hash_data})


@app.route("/api/visual/bufferpool", methods=["GET"])
def get_buffer_pool():
    table = request.args.get("table", "products")
    bp_info = engine.get_buffer_pool_info(table)
    return jsonify({"table": table, "buffer_pool": bp_info})


@app.route("/api/visual/page", methods=["GET"])
def get_page_details():
    table = request.args.get("table", "products")
    page_id = int(request.args.get("page_id", 0))
    page_info = engine.get_page_info(table, page_id)
    return jsonify({"table": table, "page_id": page_id, "page": page_info})


@app.route("/api/benchmark", methods=["POST"])
def run_benchmark():
    data = request.get_json() or {}
    count = int(data.get("records", 500))
    res = engine.run_benchmark_comparison(num_records=count)
    return jsonify(res)


def start_web_server(host="127.0.0.1", port=5000):
    print(f"[*] Starting MiniDB Web Server on http://{host}:{port}")
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    start_web_server()
