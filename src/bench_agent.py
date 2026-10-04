#!/usr/bin/env python3
"""Fixed, offline programming fixture for Omarchy Bench.

This module does not invoke an AI provider. ``run_local_replay`` is a deterministic
local tool-workflow replay, NOT an agent reasoning benchmark. A caller may launch
an explicitly selected real agent in the generated project, then call
``evaluate_agent_workspace``. A working directory is not a security sandbox.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time

FIXTURE_VERSION = "telemetry-v1"
DATA_ROWS = 30000

PROMPT = """Complete this fixed programming benchmark in the current directory.
Only modify this disposable project. Do not access other projects, install
packages, use the network, change system settings, or change benchmark metadata.
Use Python standard library only. Read README.md and inspect the existing source.

Repair telemetry/parser.py and implement telemetry/summary.py and telemetry/cli.py:
1. parse_line(line) accepts a JSON object with service (nonempty string, stripped),
   status (integer 100..599, bool forbidden), and duration_ms (int/float finite and
   >=0, bool forbidden). It returns only those three normalized fields (duration
   as float), or None for invalid input. Zero duration is valid. Extra fields
   may be ignored. Empty lines and malformed JSON are invalid.
2. summarize(lines, service=None) processes a stream of JSONL strings. Count all
   invalid lines in invalid_lines. An optional exact, case-sensitive service
   filter applies to valid normalized records only; report excluded valid rows
   in filtered_lines. Return exactly: count, errors (status>=500), total_ms,
   mean_ms, p95_ms, services (per-service counts), invalid_lines, filtered_lines.
   p95 uses nearest-rank ceil(0.95*n), one-based, after sorting durations. Empty
   results have zero for all numeric aggregate values and {} for services.
3. `python -m telemetry PATH [--service NAME]` reads a UTF-8 JSONL file and emits
   exactly one JSON report to stdout. PATH `-` reads stdin. No debug stdout.
4. Add or extend tests for zero duration, invalid records, service filtering, and
   p95. Run tests and the CLI. Finish with a short summary of what changed.

Do not remove or edit catalog/, docs/, or data/. Public tests are examples; the
benchmark will separately run its own original acceptance checks.
"""

PARSER_START = '''import json

def parse_line(line):
    try:
        record = json.loads(line)
        if not record.get("duration_ms"):
            return None
        return record
    except (ValueError, AttributeError):
        return None
'''

SUMMARY_START = '''from .parser import parse_line

def summarize(lines, service=None):
    records = [r for line in lines if (r := parse_line(line)) is not None]
    values = sorted(r["duration_ms"] for r in records)
    total = sum(values)
    return {"count": len(records), "errors": 0, "total_ms": total,
            "mean_ms": total / len(records) if records else 0,
            "p95_ms": values[-1] if values else 0, "services": {},
            "invalid_lines": 0, "filtered_lines": 0}
'''

CLI_START = '''import argparse
import json
from .summary import summarize

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    args = parser.parse_args()
    with open(args.path, encoding="utf-8") as stream:
        print(json.dumps(summarize(stream), sort_keys=True))
'''

PARSER_REFERENCE = '''import json
import math

def parse_line(line):
    try:
        record = json.loads(line)
        if not isinstance(record, dict):
            return None
        service = record.get("service")
        status = record.get("status")
        duration = record.get("duration_ms")
        if not isinstance(service, str) or not service.strip():
            return None
        if isinstance(status, bool) or not isinstance(status, int) or not 100 <= status <= 599:
            return None
        if isinstance(duration, bool) or not isinstance(duration, (int, float)):
            return None
        duration = float(duration)
        if not math.isfinite(duration) or duration < 0:
            return None
        return {"service": service.strip(), "status": status, "duration_ms": duration}
    except (ValueError, TypeError, OverflowError):
        return None
'''

SUMMARY_REFERENCE = '''import math
from .parser import parse_line

def summarize(lines, service=None):
    durations = []
    errors = invalid = filtered = 0
    services = {}
    for line in lines:
        record = parse_line(line)
        if record is None:
            invalid += 1
            continue
        if service is not None and record["service"] != service:
            filtered += 1
            continue
        durations.append(record["duration_ms"])
        errors += int(record["status"] >= 500)
        services[record["service"]] = services.get(record["service"], 0) + 1
    durations.sort()
    count = len(durations)
    total = math.fsum(durations)
    return {"count": count, "errors": errors, "total_ms": total,
            "mean_ms": total / count if count else 0,
            "p95_ms": durations[math.ceil(.95 * count) - 1] if count else 0,
            "services": services, "invalid_lines": invalid, "filtered_lines": filtered}
'''

CLI_REFERENCE = '''import argparse
import json
import sys
from .summary import summarize

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    parser.add_argument("--service")
    args = parser.parse_args()
    if args.path == "-":
        report = summarize(sys.stdin, args.service)
    else:
        with open(args.path, encoding="utf-8") as stream:
            report = summarize(stream, args.service)
    print(json.dumps(report, sort_keys=True, allow_nan=False))
'''

PUBLIC_TESTS = '''import json
import unittest
from telemetry.parser import parse_line
from telemetry.summary import summarize

class Examples(unittest.TestCase):
    def test_zero_is_valid(self):
        self.assertEqual(parse_line('{"service":"api","status":200,"duration_ms":0}')["duration_ms"], 0)
    def test_bad_json(self):
        self.assertIsNone(parse_line("bad JSON"))
    def test_filter(self):
        lines = [json.dumps(dict(service=s, status=200, duration_ms=5)) for s in ("api", "jobs")]
        result = summarize(lines, "api")
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["filtered_lines"], 1)
'''

REFERENCE_TESTS = PUBLIC_TESTS + '''
    def test_p95_nearest_rank(self):
        lines = [json.dumps(dict(service="api", status=200, duration_ms=n)) for n in range(1, 21)]
        self.assertEqual(summarize(lines)["p95_ms"], 19)
    def test_boolean_duration_is_invalid(self):
        self.assertIsNone(parse_line('{"service":"api","status":200,"duration_ms":true}'))
    def test_empty(self):
        self.assertEqual(summarize([])["count"], 0)
'''

README = '''# Telemetry report exercise

A synthetic, offline Python repository for repeatable programming-workflow tests.
This is a test fixture, not a production codebase or an application benchmark.

`telemetry/` contains the JSONL parser, aggregate function, and command-line entry.
`catalog/` contains 128 generated service schema modules for repository navigation.
`docs/` contains generated operational notes; `data/events.jsonl` is fixed input.
There are no external dependencies. See TASK.md for the exact repair and feature.

Run examples: `python -m unittest discover -s tests -v`
Run report: `python -m telemetry data/events.jsonl --service service-007`

The original parser rejects zero durations and accepts some invalid records.
The existing summary has incomplete validation, filtering, counts, and quantiles.
'''


def _write(root, relative, text):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _row(n):
    if n % 41 == 0:
        return "broken json line\n"
    record = {"service": "service-%03d" % (n % 128),
              "status": 503 if n % 13 == 0 else 200,
              "duration_ms": (n * 17 % 10000) / 10,
              "request_id": "synthetic-%08d" % n}
    return json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"


def generate_fixture(root):
    """Generate fixed files in a new/empty normal directory; return a manifest."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise ValueError("Fixture target must be empty; no existing files are overwritten")
    for name, content in {
        "README.md": README, "TASK.md": PROMPT,
        "telemetry/__init__.py": '"""Small JSONL reporting package."""\n',
        "telemetry/__main__.py": "from .cli import main\nmain()\n",
        "telemetry/parser.py": PARSER_START,
        "telemetry/summary.py": SUMMARY_START,
        "telemetry/cli.py": CLI_START,
        "tests/test_telemetry.py": PUBLIC_TESTS,
        ".gitignore": "__pycache__/\n*.pyc\n.bench-logs/\n",
    }.items():
        _write(root, name, content)
    for n in range(128):
        fields = ["duration_ms", "service", "status", "request_id"]
        content = ('"""Synthetic service metadata for repository navigation."""\n'
                   + f'SERVICE = "service-{n:03d}"\n'
                   + f"FIELDS = {fields!r}\n"
                   + "EXAMPLE = " + repr({"service": f"service-{n:03d}", "status": 200, "duration_ms": n / 10}) + "\n"
                   + "NOTES = " + repr("Preserve zero duration values; emit UTF-8 JSONL. " * 10) + "\n")
        _write(root, f"catalog/service_{n:03d}.py", content)
    for n in range(24):
        _write(root, f"docs/operation-{n:02d}.md", f"# Synthetic operation {n}\n\n" +
               "The telemetry stream uses service, status, and duration_ms fields.\n" * 16)
    (root / "data").mkdir(exist_ok=True)
    with (root / "data/events.jsonl").open("w", encoding="utf-8") as f:
        for n in range(DATA_ROWS):
            f.write(_row(n))
    files = sorted(p for p in root.rglob("*") if p.is_file())
    manifest = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    return {"fixture_version": FIXTURE_VERSION, "prompt": PROMPT,
            "file_count": len(files), "data_rows": DATA_ROWS,
            "bytes": sum(p.stat().st_size for p in files),
            "manifest_sha256": hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest(),
            "manifest": manifest}


# This harness is supplied by the runner, never imported from agent-edited tests.
# It checks behavior; it is not a hostile-code containment system.
TRUSTED_HARNESS = r'''
import importlib, json, math, os, subprocess, sys
sys.path.insert(0, os.getcwd())
checks = []
def check(name, fn):
    try:
        fn()
        checks.append({"name": name, "passed": True})
    except Exception as exc:
        checks.append({"name": name, "passed": False, "detail": type(exc).__name__ + ": " + str(exc)[:400]})
def eq(actual, expected):
    if isinstance(expected, dict):
        if not isinstance(actual,dict) or set(actual)!=set(expected):
            raise AssertionError("Report fields differ")
        for key in expected: eq(actual[key],expected[key])
        return
    if isinstance(expected,(int,float)) and not isinstance(expected,bool):
        if not isinstance(actual,(int,float)) or isinstance(actual,bool) or not math.isclose(actual,expected,rel_tol=1e-9,abs_tol=1e-8):
            raise AssertionError(repr(actual) + " != " + repr(expected))
        return
    if actual != expected:
        raise AssertionError(repr(actual)[:200] + " != " + repr(expected)[:200])
def line(service="api", status=200, duration=0):
    return json.dumps(dict(service=service, status=status, duration_ms=duration))
try:
    parse_line = importlib.import_module("telemetry.parser").parse_line
    summarize = importlib.import_module("telemetry.summary").summarize
except Exception as exc:
    print(json.dumps({"passed":False,"checks":[{"name":"import","passed":False,"detail":str(exc)[:400]}]}))
    sys.exit(0)
check("bugfix.zero_duration", lambda: eq(parse_line(line()), {"service":"api","status":200,"duration_ms":0.0}))
check("bugfix.normalized_service", lambda: eq(parse_line(line(" api ", 201, 1.25)), {"service":"api","status":201,"duration_ms":1.25}))
invalids = ["", "bad", "[]", "null", "true", "{}", line(""), line("   "), line(7),
            line(status=True), line(status=99), line(status=600), line(status=200.5), line(status="200"),
            line(duration=True), line(duration=-1), line(duration="1"), line(duration=None),
            line(duration=float("nan")), line(duration=float("inf"))]
def invalid_check():
    for sample in invalids:
        eq(parse_line(sample), None)
check("bugfix.invalid_inputs", invalid_check)
zero = dict(count=0, errors=0, total_ms=0, mean_ms=0, p95_ms=0, services={}, invalid_lines=0, filtered_lines=0)
check("summary.empty", lambda: eq(summarize([]), zero))
samples = [line("api",200,0), line("api",503,10), line(" jobs ",404,20), "bad"]
all_expected = dict(count=3, errors=1, total_ms=30, mean_ms=10, p95_ms=20, services={"api":2,"jobs":1}, invalid_lines=1, filtered_lines=0)
check("summary.counts_and_invalid", lambda: eq(summarize(iter(samples)), all_expected))
api_expected = dict(count=2, errors=1, total_ms=10, mean_ms=5, p95_ms=10, services={"api":2}, invalid_lines=1, filtered_lines=1)
check("feature.service_filter", lambda: eq(summarize(iter(samples), "api"), api_expected))
none_expected = dict(zero, invalid_lines=1, filtered_lines=3)
check("feature.case_sensitive_filter", lambda: eq(summarize(iter(samples), "API"), none_expected))
check("feature.p95_nearest_rank", lambda: eq(summarize([line(duration=n) for n in range(20,0,-1)])["p95_ms"], 19))
check("feature.p95_one", lambda: eq(summarize([line(duration=4.5)])["p95_ms"],4.5))
def cli(stdin):
    args = [sys.executable, "-B", "-X", "pycache_prefix="+sys.pycache_prefix, "-m", "telemetry", "-", "--service", "api"]
    result = subprocess.run(args, input="\n".join(samples), text=True, capture_output=True, timeout=15)
    eq(result.returncode, 0)
    eq(json.loads(result.stdout), api_expected)
check("cli.stdin_filter", lambda: cli(True))
def cli_file():
    # Read the immutable fixture data; independently calculate expected output.
    source = "data/events.jsonl"
    values = []; errors=invalid=filtered=0
    with open(source,encoding="utf-8") as stream:
        for raw in stream:
            try:
                r=json.loads(raw)
            except ValueError:
                invalid+=1;continue
            if r["service"]!="service-007":
                filtered+=1;continue
            values.append(r["duration_ms"]);errors+=int(r["status"]>=500)
    values.sort();n=len(values);total=math.fsum(values)
    expected=dict(count=n, errors=errors,total_ms=total,mean_ms=total/n,p95_ms=values[math.ceil(.95*n)-1],
                  services={"service-007":n},invalid_lines=invalid,filtered_lines=filtered)
    result=subprocess.run([sys.executable,"-B","-X","pycache_prefix="+sys.pycache_prefix,"-m","telemetry",source,"--service","service-007"],text=True,capture_output=True,timeout=25)
    eq(result.returncode,0);eq(json.loads(result.stdout),expected)
check("cli.fixed_dataset",cli_file)
print(json.dumps({"passed":all(c["passed"] for c in checks),"checks":checks},sort_keys=True))
'''


def _run(work, argv, timeout=90, checkpoint=None, name="command"):
    checkpoint = checkpoint or (lambda: None)
    logs = work / ".bench-logs"
    if logs.is_symlink():
        raise ValueError("Benchmark log directory is a symlink")
    logs.mkdir(exist_ok=True)
    for path in (logs / (name + ".out"), logs / (name + ".err")):
        if path.is_symlink():
            raise ValueError("Benchmark log file is a symlink")
    started = time.perf_counter()
    with (logs / (name + ".out")).open("w+") as out, (logs / (name + ".err")).open("w+") as err:
        proc = subprocess.Popen(argv, cwd=work, stdout=out, stderr=err, start_new_session=True)
        try:
            while proc.poll() is None:
                checkpoint()
                if time.perf_counter() - started > timeout:
                    raise TimeoutError(name + " exceeded " + str(timeout) + "s")
                time.sleep(.02)
        finally:
            if proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                    proc.wait(timeout=2)
                except (ProcessLookupError, subprocess.TimeoutExpired):
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    proc.wait()
        out.seek(0); err.seek(0)
        return {"seconds": time.perf_counter() - started, "returncode": proc.returncode,
                "stdout": out.read(), "stderr": err.read()}


def evaluate_agent_workspace(work, checkpoint=None):
    """Run original acceptance checks; caller must contain untrusted agent code."""
    work = Path(work)
    callback_error = []
    def checked():
        if checkpoint is not None:
            try:
                checkpoint()
            except BaseException as exc:
                callback_error.append(exc)
                raise
    try:
        # Do not follow replacements of the runner log directory outside fixture.
        if (work / ".bench-logs").is_symlink():
            raise ValueError("Benchmark log directory is a symlink")
        for relative in ("telemetry", "data", "data/events.jsonl"):
            if (work / relative).is_symlink():
                raise ValueError("Fixture boundary replaced by symlink: " + relative)
        source = work / "data/events.jsonl"
        expected_hash = hashlib.sha256("".join(_row(n) for n in range(DATA_ROWS)).encode()).hexdigest()
        data_intact = source.is_file() and hashlib.sha256(source.read_bytes()).hexdigest() == expected_hash
        # Isolate bytecode so stale agent-generated .pyc files cannot mask edits.
        with tempfile.TemporaryDirectory(prefix="bench-acceptance-cache-") as cache:
            result = _run(work, [sys.executable, "-I", "-B", "-X", "pycache_prefix=" + cache,
                                "-c", TRUSTED_HARNESS], name="acceptance", checkpoint=checked)
        if result["returncode"]:
            return {"passed": False, "checks": [], "error": "Acceptance subprocess failed",
                    "returncode": result["returncode"], "stderr": result["stderr"][-2000:]}
        # Any extra stdout from an edited module is a failure, not parsed around.
        report = json.loads(result["stdout"])
        report["checks"].append({"name": "fixture.data_unchanged", "passed": data_intact})
        report["passed"] = report["passed"] and data_intact
        report["seconds"] = result["seconds"]
        changes = []
        for path in (work / "tests").rglob("*.py"):
            if not path.is_symlink() and (path.name != "test_telemetry.py" or path.read_text() != PUBLIC_TESTS):
                changes.append(str(path.relative_to(work)))
        report["test_files_added_or_changed"] = sorted(changes)
        report["checks"].append({"name": "task.tests_added_or_extended", "passed": bool(changes)})
        report["passed"] = report["passed"] and bool(changes)
        report["scope"] = "Original behavioral checks plus test-change evidence; not a security or complete correctness proof"
        return report
    except Exception as exc:
        if callback_error:
            raise
        return {"passed": False, "checks": [], "error": type(exc).__name__ + ": " + str(exc)[:500]}


def run_local_replay(work, checkpoint=lambda: None):
    """Run fixed read/search/edit/compile/test/CLI operations without any model."""
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    if not any(work.iterdir()):
        generate_fixture(work)
    if not (work / "TASK.md").is_file():
        raise ValueError("Replay requires a new empty directory or this generated fixture")
    replay_started = time.perf_counter()
    timings = {}
    started = time.perf_counter()
    checkpoint()
    paths = sorted(p for p in work.rglob("*") if p.is_file() and ".bench-logs" not in p.parts)
    total = matches = 0
    for path in paths:
        checkpoint()
        data = path.read_bytes()
        total += len(data)
        if path.suffix in (".py", ".md"):
            matches += data.count(b"duration_ms")
    timings["repo_read_search_s"] = time.perf_counter() - started
    started = time.perf_counter()
    for name, content in {"telemetry/parser.py": PARSER_REFERENCE,
                          "telemetry/summary.py": SUMMARY_REFERENCE,
                          "telemetry/cli.py": CLI_REFERENCE,
                          "tests/test_telemetry.py": REFERENCE_TESTS}.items():
        checkpoint()
        _write(work, name, content)
    timings["apply_fixed_patch_s"] = time.perf_counter() - started
    commands = [
        ("compile", [sys.executable, "-m", "compileall", "-q", "-f", "telemetry", "catalog", "tests"]),
        ("public_tests", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]),
        ("cli_dataset", [sys.executable, "-m", "telemetry", "data/events.jsonl"]),
    ]
    outputs = {}
    for name, command in commands:
        result = _run(work, command, checkpoint=checkpoint, name=name)
        timings[name + "_s"] = result["seconds"]
        outputs[name] = {"returncode": result["returncode"], "stdout": result["stdout"], "stderr": result["stderr"]}
        if result["returncode"]:
            return {"passed": False, "kind": "LOCAL_REPLAY_NO_MODEL", "timings": timings, "outputs": outputs,
                    "acceptance": {"passed": False, "error": name + " failed"},
                    "total_s": time.perf_counter() - replay_started}
    checkpoint()
    acceptance = evaluate_agent_workspace(work, checkpoint=checkpoint)
    timings["trusted_acceptance_s"] = acceptance.get("seconds")
    return {"passed": acceptance["passed"], "kind": "LOCAL_REPLAY_NO_MODEL",
            "fixture_version": FIXTURE_VERSION, "timings": timings,
            "total_s": time.perf_counter() - replay_started,
            "repo_bytes_read": total, "search_matches": matches,
            "acceptance": acceptance, "outputs": outputs,
            "limits": ["No AI inference: this measures a fixed local programming tool sequence.",
                       "Fresh files are normally in OS cache; this is not a cold-cache disk benchmark.",
                       "Compilation is Python bytecode compilation, not a C/Rust/Node production build."]}


def self_check():
    with tempfile.TemporaryDirectory(prefix="bench-agent-selfcheck-") as tmp:
        root = Path(tmp) / "repo"
        meta = generate_fixture(root)
        before = evaluate_agent_workspace(root)
        if before["passed"]:
            raise AssertionError("Broken starting fixture unexpectedly passed")
        result = run_local_replay(root)
        if not result["passed"]:
            raise AssertionError(json.dumps(result, indent=2))
        (root / "telemetry/parser.py").write_text("def parse_line(line): return None\n")
        # Invalidate bytecode explicitly to test edited source, independent of mtime granularity.
        shutil.rmtree(root / "telemetry/__pycache__", ignore_errors=True)
        after = evaluate_agent_workspace(root)
        if after["passed"]:
            raise AssertionError("Broken parser mutation unexpectedly passed")
        print(json.dumps({"self_check": "PASS", "fixture": {k:v for k,v in meta.items() if k not in ("prompt","manifest")},
                          "reference_check_count": len(result["acceptance"]["checks"]),
                          "timings": result["timings"], "network_or_model_calls": 0}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--generate", type=Path)
    args = parser.parse_args()
    if args.self_check:
        self_check()
    elif args.generate:
        print(json.dumps(generate_fixture(args.generate), indent=2))
    else:
        parser.print_help()
