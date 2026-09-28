"""
MiniDB - Database Engine from Scratch.

Entry point for launching the Web-based DBMS Visualizer & Workbench,
or interactive REPL CLI shell.
"""

import sys
import argparse
from minidb.web_server import start_web_server
from minidb.cli import run_cli


def main():
    parser = argparse.ArgumentParser(description="MiniDB - Database Engine from Scratch")
    parser.add_argument("--cli", action="store_true", help="Launch interactive CLI REPL shell")
    parser.add_argument("--port", type=int, default=5000, help="Web server port (default: 5000)")
    args = parser.parse_args()

    if args.cli:
        run_cli()
    else:
        print("=" * 70)
        print(" MiniDB - Lightweight Database Engine from Scratch (v1.0)")
        print(f" Starting Web-based DBMS Visualizer & Workbench on http://127.0.0.1:{args.port}")
        print("=" * 70)
        start_web_server(port=args.port)


if __name__ == "__main__":
    main()
