"""Command-line entrypoint: `dsa-trace`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .tracer import trace_source


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dsa-trace",
        description="Trace a Python program and emit Trace Event Protocol JSON.",
    )
    parser.add_argument("source", help="Path to the Python source file to trace.")
    parser.add_argument(
        "-o", "--output",
        help="Write trace JSON here (default: stdout).",
    )
    parser.add_argument(
        "--stdin",
        help="Path to a file used as stdin for the user program. Use '-' to read stdin of dsa-trace itself.",
    )
    parser.add_argument(
        "--max-events",
        type=int,
        default=5000,
        help="Hard cap on the number of trace events (default 5000).",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print the JSON.",
    )
    args = parser.parse_args(argv)

    src_path = Path(args.source)
    if not src_path.exists():
        print(f"dsa-trace: file not found: {src_path}", file=sys.stderr)
        return 2

    source = src_path.read_text(encoding="utf-8")

    stdin_str = ""
    if args.stdin == "-":
        stdin_str = sys.stdin.read()
    elif args.stdin:
        stdin_str = Path(args.stdin).read_text(encoding="utf-8")

    result = trace_source(source, stdin=stdin_str, max_events=args.max_events)

    indent = 2 if args.pretty else None
    payload = json.dumps(result, indent=indent, ensure_ascii=False)

    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        n = len(result["events"])
        print(f"dsa-trace: wrote {n} events to {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(payload)
        if not args.pretty:
            sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
