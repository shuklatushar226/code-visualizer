#!/usr/bin/env python3
# ruff: noqa: E501 -- inline programs are intentionally complete test fixtures
"""Run 1,000 deterministic HTTP cases against the production trace API."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

EVENT_KINDS = {"step", "call", "return", "exception", "stdout"}
EXIT_STATUSES = {"ok", "error", "timeout"}
VALUE_KINDS = {"int", "float", "bool", "str", "none", "ref"}
HEAP_KINDS = {"list", "tuple", "set", "dict", "object", "str"}


@dataclass(frozen=True)
class Case:
    case_id: str
    category: str
    payload: dict[str, Any]
    http_status: int = 200
    exit_status: str | None = "ok"
    stdout: str | None = None
    require_events: bool = True


@dataclass
class Result:
    case_id: str
    category: str
    language: str
    passed: bool
    latency_ms: float
    http_status: int
    event_count: int = 0
    error: str = ""


def python_case(index: int) -> Case:
    variant, n = index % 10, index + 3
    prefix = f"py-{index:04d}"
    if variant == 0:
        a, b = n % 97, (n * 7) % 101
        src = f"a = {a}\nb = {b}\nprint(a * b + a - b)\n"
        return Case(
            prefix, "python/arithmetic", {"language": "python", "source": src, "stdin": ""}, stdout=f"{a * b + a - b}\n"
        )
    if variant == 1:
        limit = n % 30 + 5
        src = f"total = 0\nfor i in range({limit}):\n    total += i * i\nprint(total)\n"
        return Case(
            prefix,
            "python/loops",
            {"language": "python", "source": src, "stdin": ""},
            stdout=f"{sum(i * i for i in range(limit))}\n",
        )
    if variant == 2:
        values = [n % 11, (n + 3) % 11, (n * 2) % 11, n % 11]
        src = f"values = {values!r}\nunique = sorted(set(values))\ncounts = {{x: values.count(x) for x in unique}}\nprint(sum(counts.values()), unique)\n"
        return Case(
            prefix,
            "python/collections",
            {"language": "python", "source": src, "stdin": ""},
            stdout=f"4 {sorted(set(values))}\n",
        )
    if variant == 3:
        text = f"resume-case-{n}"
        src = "text = input().strip()\nprint(text[::-1].upper())\n"
        return Case(
            prefix,
            "python/stdin",
            {"language": "python", "source": src, "stdin": text + "\n"},
            stdout=text[::-1].upper() + "\n",
        )
    if variant == 4:
        depth = n % 6 + 1
        src = f"def factorial(x):\n    if x <= 1:\n        return 1\n    return x * factorial(x - 1)\nprint(factorial({depth}))\n"
        return Case(
            prefix,
            "python/recursion",
            {"language": "python", "source": src, "stdin": ""},
            stdout=f"{math.factorial(depth)}\n",
        )
    if variant == 5:
        values = [n, n + 1, n + 2, n + 3]
        src = (
            "class Node:\n    def __init__(self, val, next=None):\n        self.val = val\n        self.next = next\n\ndef reverse(head):\n    prev = None\n    cur = head\n    while cur is not None:\n        nxt = cur.next\n        cur.next = prev\n        prev = cur\n        cur = nxt\n    return prev\n\n"
            + f"head = Node({values[0]}, Node({values[1]}, Node({values[2]}, Node({values[3]}))))\nhead = reverse(head)\nout = []\nwhile head:\n    out.append(head.val)\n    head = head.next\nprint(out)\n"
        )
        return Case(
            prefix,
            "python/linked-list",
            {"language": "python", "source": src, "stdin": ""},
            stdout=f"{list(reversed(values))}\n",
        )
    if variant == 6:
        width = n % 5 + 3
        src = f"graph = {{i: [i + 1] for i in range({width - 1})}}\ngraph[{width - 1}] = []\nqueue = [0]\nseen = []\nwhile queue:\n    node = queue.pop(0)\n    if node not in seen:\n        seen.append(node)\n        queue.extend(graph[node])\nprint(seen)\n"
        return Case(
            prefix, "python/graph", {"language": "python", "source": src, "stdin": ""}, stdout=f"{list(range(width))}\n"
        )
    if variant == 7:
        values = [(n * m) % 23 for m in (7, 3, 11, 2, 5)]
        src = f"values = {values!r}\nfor i in range(len(values)):\n    for j in range(len(values) - i - 1):\n        if values[j] > values[j + 1]:\n            values[j], values[j + 1] = values[j + 1], values[j]\nprint(values)\n"
        return Case(
            prefix, "python/sorting", {"language": "python", "source": src, "stdin": ""}, stdout=f"{sorted(values)}\n"
        )
    if variant == 8:
        src = f"value = {n}\nraise ValueError('expected-' + str(value))\n"
        return Case(
            prefix,
            "python/runtime-error",
            {"language": "python", "source": src, "stdin": ""},
            exit_status="error",
            stdout="",
            require_events=False,
        )
    src = f"value = {n}\nif value > 0 print(value)\n"
    return Case(
        prefix,
        "python/syntax-error",
        {"language": "python", "source": src, "stdin": ""},
        exit_status="error",
        stdout="",
        require_events=False,
    )


def javascript_case(index: int) -> Case:
    variant, n = index % 6, index + 5
    prefix = f"js-{index:04d}"
    if variant == 0:
        src = f"const values = [{n % 13}, {(n * 3) % 17}, {(n * 5) % 19}];\nconst total = values.reduce((a, b) => a + b, 0);\nconsole.log(total);\n"
        category = "javascript/arrays"
    elif variant == 1:
        src = f"function fib(n) {{ return n < 2 ? n : fib(n - 1) + fib(n - 2); }}\nconsole.log(fib({n % 7 + 2}));\n"
        category = "javascript/recursion"
    elif variant == 2:
        src = f"const node = {{ value: {n}, next: {{ value: {n + 1}, next: null }} }};\nlet sum = 0;\nfor (let cur = node; cur; cur = cur.next) sum += cur.value;\nconsole.log(sum);\n"
        category = "javascript/objects"
    elif variant == 3:
        src = f'const map = new Map([["a", {n}], ["b", {n + 2}]]);\nconsole.log([...map.values()].join(\',\'));\n'
        category = "javascript/map"
    elif variant == 4:
        src = f"let total = 0;\nfor (let i = 0; i < {n % 20 + 5}; i++) total += i * 2;\nconsole.log(total);\n"
        category = "javascript/loops"
    else:
        src = f"const value = {n};\nthrow new Error('expected-' + value);\n"
        return Case(
            prefix,
            "javascript/runtime-error",
            {"language": "javascript", "source": src, "stdin": ""},
            exit_status="error",
            require_events=False,
        )
    return Case(prefix, category, {"language": "javascript", "source": src, "stdin": ""})


def cpp_case(index: int) -> Case:
    variant, n = index % 5, index + 7
    prefix = f"cpp-{index:04d}"
    if variant == 0:
        src = f"#include <iostream>\nint main() {{ int a = {n}; int b = {n + 3}; std::cout << a + b << '\\n'; return 0; }}\n"
        category = "cpp/arithmetic"
    elif variant == 1:
        src = f"#include <vector>\n#include <algorithm>\nint main() {{ std::vector<int> v{{{n % 9}, {(n * 3) % 11}, {(n * 5) % 13}}}; std::sort(v.begin(), v.end()); return v.empty(); }}\n"
        category = "cpp/vector"
    elif variant == 2:
        src = f"int main() {{ int total = 0; for (int i = 0; i < {n % 15 + 3}; ++i) total += i; return total < 0; }}\n"
        category = "cpp/loops"
    elif variant == 3:
        src = f"int sum(int n) {{ return n <= 0 ? 0 : n + sum(n - 1); }}\nint main() {{ int result = sum({n % 6 + 2}); return result < 0; }}\n"
        category = "cpp/recursion"
    else:
        src = f"int main() {{ int value = {n} return value; }}\n"
        return Case(
            prefix,
            "cpp/compile-error",
            {"language": "cpp", "source": src, "stdin": ""},
            exit_status="error",
            require_events=False,
        )
    return Case(prefix, category, {"language": "cpp", "source": src, "stdin": ""})


def validation_cases() -> list[Case]:
    cases = [
        Case(
            f"api-unsupported-{i}",
            "api/unsupported-language",
            {"language": lang, "source": "main", "stdin": ""},
            400,
            None,
            require_events=False,
        )
        for i, lang in enumerate(("rust", "go", "ruby", "brainfuck"))
    ]
    cases += [
        Case(
            f"api-missing-{i}",
            "api/missing-field",
            {"language": "python", "stdin": ""},
            422,
            None,
            require_events=False,
        )
        for i in range(3)
    ]
    invalid = [
        {"language": 42, "source": ["bad"], "stdin": ""},
        {"language": "python", "source": None, "stdin": ""},
        {"language": "python", "source": "x=1", "stdin": ["bad"]},
    ]
    cases += [
        Case(f"api-invalid-{i}", "api/invalid-type", payload, 422, None, require_events=False)
        for i, payload in enumerate(invalid)
    ]
    return cases


def build_suite() -> list[Case]:
    cases = (
        [python_case(i) for i in range(870)]
        + [javascript_case(i) for i in range(90)]
        + [cpp_case(i) for i in range(30)]
        + validation_cases()
    )
    assert len(cases) == len({case.case_id for case in cases}) == 1000
    return cases


def assert_value(value: Any, where: str) -> None:
    if not isinstance(value, dict) or value.get("kind") not in VALUE_KINDS:
        raise AssertionError(f"{where}: invalid encoded value {value!r}")
    kind = value["kind"]
    if kind == "ref" and not isinstance(value.get("id"), str):
        raise AssertionError(f"{where}: ref id must be a string")
    if kind not in {"none", "ref"} and "v" not in value:
        raise AssertionError(f"{where}: {kind} value is missing v")


def assert_trace(trace: Any, case: Case) -> int:
    if not isinstance(trace, dict) or trace.get("version") != "0.1":
        raise AssertionError("invalid trace object or protocol version")
    expected_language = "javascript" if case.payload["language"] == "js" else case.payload["language"]
    if trace.get("language") != expected_language or trace.get("source") != case.payload["source"]:
        raise AssertionError("response language/source does not match submission")
    for field in ("stdin", "stdout", "stderr"):
        if not isinstance(trace.get(field, ""), str):
            raise AssertionError(f"{field} is not a string")
    exit_info = trace.get("exit")
    if not isinstance(exit_info, dict) or exit_info.get("status") not in EXIT_STATUSES:
        raise AssertionError("invalid exit object")
    if case.exit_status is not None and exit_info["status"] != case.exit_status:
        raise AssertionError(f"expected exit {case.exit_status}, got {exit_info['status']}: {exit_info.get('message')}")
    if case.stdout is not None and trace.get("stdout", "") != case.stdout:
        raise AssertionError(f"stdout mismatch: expected {case.stdout!r}, got {trace.get('stdout', '')!r}")
    events = trace.get("events")
    if not isinstance(events, list) or len(events) > 5000:
        raise AssertionError("events is invalid or exceeds the configured limit")
    if case.require_events and not events:
        raise AssertionError("successful program returned no trace events")
    for index, event in enumerate(events):
        if not isinstance(event, dict) or event.get("t") != index or event.get("kind") not in EVENT_KINDS:
            raise AssertionError(f"event {index} has invalid identity/kind")
        if not isinstance(event.get("line"), int) or event["line"] < 0 or not isinstance(event.get("file"), str):
            raise AssertionError(f"event {index} has invalid source position")
        stack, heap = event.get("stack"), event.get("heap")
        if not isinstance(stack, list) or not isinstance(heap, dict):
            raise AssertionError(f"event {index} has invalid stack or heap")
        for frame_index, frame in enumerate(stack):
            if (
                not isinstance(frame, dict)
                or not isinstance(frame.get("func"), str)
                or not isinstance(frame.get("file"), str)
                or not isinstance(frame.get("line"), int)
                or not isinstance(frame.get("locals"), dict)
            ):
                raise AssertionError(f"event {index} frame {frame_index} is invalid")
            for name, value in frame["locals"].items():
                assert_value(value, f"event {index} local {name}")
        for object_id, obj in heap.items():
            if not isinstance(object_id, str) or not isinstance(obj, dict) or obj.get("kind") not in HEAP_KINDS:
                raise AssertionError(f"event {index} has invalid heap object {object_id!r}")
    return len(events)


def run_case(base_url: str, case: Case, timeout: float, retries: int = 4) -> Result:
    started = time.perf_counter()
    request = urllib.request.Request(
        base_url.rstrip("/") + "/trace",
        data=json.dumps(case.payload).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "code-visualizer-soak/1.0"},
        method="POST",
    )
    status, body = 0, None
    try:
        for attempt in range(retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    status, body = response.status, json.loads(response.read().decode())
                break
            except urllib.error.HTTPError as exc:
                status = exc.code
                raw = exc.read().decode()
                body = json.loads(raw) if raw else None
                if status in {429, 503} and attempt < retries:
                    time.sleep(0.15 * (attempt + 1))
                    continue
                break
        if status != case.http_status:
            raise AssertionError(f"expected HTTP {case.http_status}, got {status}: {body!r}")
        count = assert_trace(body, case) if status == 200 else 0
        return Result(
            case.case_id,
            case.category,
            str(case.payload.get("language", "invalid")),
            True,
            (time.perf_counter() - started) * 1000,
            status,
            count,
        )
    except Exception as exc:
        return Result(
            case.case_id,
            case.category,
            str(case.payload.get("language", "invalid")),
            False,
            (time.perf_counter() - started) * 1000,
            status,
            error=f"{type(exc).__name__}: {exc}",
        )


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, math.ceil(len(ordered) * fraction) - 1))]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:18080")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--report", type=Path, default=Path("artifacts/soak-report.json"))
    args = parser.parse_args()
    cases = build_suite()
    if args.limit is not None:
        if not 1 <= args.limit <= 1000:
            parser.error("--limit must be between 1 and 1000")
        cases = cases[: args.limit]
    print(f"Running {len(cases)} cases against {args.base_url} with {args.workers} workers", flush=True)
    started, results = time.perf_counter(), []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(run_case, args.base_url, case, args.timeout) for case in cases]
        for completed, future in enumerate(as_completed(futures), 1):
            results.append(future.result())
            if completed % 100 == 0 or completed == len(cases):
                print(
                    f"  completed {completed}/{len(cases)} ({sum(not r.passed for r in results)} failures)", flush=True
                )
    duration = time.perf_counter() - started
    latencies = [result.latency_ms for result in results]
    failures = sorted((result for result in results if not result.passed), key=lambda result: result.case_id)
    report = {
        "suite": "code-visualizer-production-http-soak-v1",
        "base_url": args.base_url,
        "total": len(results),
        "passed": len(results) - len(failures),
        "failed": len(failures),
        "duration_seconds": round(duration, 3),
        "latency_ms": {
            "mean": round(statistics.fmean(latencies), 3),
            "p50": round(percentile(latencies, 0.5), 3),
            "p95": round(percentile(latencies, 0.95), 3),
            "max": round(max(latencies), 3),
        },
        "languages": dict(sorted(Counter(r.language for r in results).items())),
        "categories": dict(sorted(Counter(r.category for r in results).items())),
        "events_validated": sum(r.event_count for r in results),
        "failures": [asdict(r) for r in failures],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                key: report[key]
                for key in ("total", "passed", "failed", "duration_seconds", "latency_ms", "events_validated")
            },
            indent=2,
        )
    )
    print(f"Full report: {args.report.resolve()}")
    for failure in failures[:20]:
        print(f"FAIL {failure.case_id} [{failure.category}]: {failure.error}", file=sys.stderr)
    if len(failures) > 20:
        print(f"... and {len(failures) - 20} more", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
