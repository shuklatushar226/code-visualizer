"""CLI for the C++ tracer (skeleton)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .cpp_tracer import trace_source


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dsa-trace-cpp")
    parser.add_argument("source", help="C++ source file")
    parser.add_argument("-o", "--output", help="trace output file (default stdout)")
    parser.add_argument("--stdin", help="path to a file used as stdin (or '-' for stdin)")
    parser.add_argument("--max-events", type=int, default=5000)
    args = parser.parse_args(argv)

    src = Path(args.source).read_text(encoding="utf-8")
    stdin_str = ""
    if args.stdin == "-":
        stdin_str = sys.stdin.read()
    elif args.stdin:
        stdin_str = Path(args.stdin).read_text(encoding="utf-8")

    try:
        result = trace_source(src, stdin=stdin_str, max_events=args.max_events)
    except Exception as e:
        print(f"dsa-trace-cpp: {e}", file=sys.stderr)
        return 1

    payload = json.dumps(result, indent=2)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
