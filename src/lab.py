"""Omarchy Lab: typical, agent, daily. Run as your normal Linux user.

python3 omarchy-lab.pyz typical
python3 omarchy-lab.pyz agent                         # local replay; no LLM
python3 omarchy-lab.pyz agent --live                  # ONE real Pi task
python3 omarchy-lab.pyz agent --live --model MODEL --rounds 3
python3 omarchy-lab.pyz daily                         # local browser + programming
python3 omarchy-lab.pyz daily --observe-update        # observe a user-run update

The temporary working directory is NOT a security sandbox for an external agent.
Live mode uses your existing agent login/settings and can incur provider charges.
No model call happens without --live. No mode launches a real system update.
"""
import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import resource
import selectors
import shlex
import shutil
import signal
import statistics
import subprocess
import sys
import tempfile
import threading
import time

import bench_base as base
import bench_agent as agent
import bench_daily as daily
import i18n
from i18n import t

VERSION = "2.1"


def median(values):
    return statistics.median(values) if values else None


def num(value, digits=3, unit=""):
    """Format a measurement, or show "not available" instead of None."""
    return t("common.na") if value is None else f"{value:.{digits}f}{unit}"


def spread(values):
    m = median(values)
    return 100 * (max(values) - min(values)) / m if m else None


def write_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2))


def kill_group(p):
    try:
        os.killpg(p.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        if p.poll() is None:
            p.wait(timeout=3)
    except subprocess.TimeoutExpired:
        pass
    # Also stop descendants when the leader has exited or ignored SIGTERM.
    try:
        os.killpg(p.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        p.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass


def interval_union(intervals):
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(end, merged[-1][1])
        else:
            merged.append([start, end])
    return sum(b - a for a, b in merged)


class PiEvents:
    """Consume only final assistant usage, never sum cumulative streaming usage."""
    def __init__(self):
        self.first_output_s = self.first_text_s = self.first_model_delta_s = None
        self.event_count, self.invalid_lines = 0, 0
        self.protocol_events = 0
        self.tool_open, self.tools, self.intervals = {}, [], []
        self.usage, self.models, self.retries = [], set(), 0

    def feed(self, raw, elapsed):
        try:
            e = json.loads(raw)
        except (ValueError, UnicodeError):
            self.invalid_lines += 1
            return
        if not isinstance(e, dict):
            self.invalid_lines += 1
            return
        self.event_count += 1
        kind = e.get("type")
        if kind in {"session", "agent_start", "agent_end", "turn_start", "turn_end", "message_start", "message_update", "message_end", "tool_execution_start", "tool_execution_end"}:
            self.protocol_events += 1
        if kind == "message_update":
            nested = e.get("assistantMessageEvent", {})
            if not isinstance(nested, dict):
                return
            if nested.get("type") in {"text_delta", "thinking_delta", "toolcall_delta"}:
                if self.first_model_delta_s is None:
                    self.first_model_delta_s = elapsed
            if nested.get("type") == "text_delta" and nested.get("delta") and self.first_text_s is None:
                self.first_text_s = elapsed
        elif kind == "tool_execution_start":
            self.tool_open[e.get("toolCallId", str(self.event_count))] = (elapsed, e.get("toolName", "unknown"))
        elif kind == "tool_execution_end":
            ident = e.get("toolCallId")
            start = self.tool_open.pop(ident, None)
            if start:
                self.intervals.append((start[0], elapsed))
                self.tools.append({"name": start[1], "observed_s": elapsed - start[0], "is_error": bool(e.get("isError"))})
        elif kind == "message_end":
            msg = e.get("message", {})
            if not isinstance(msg, dict):
                return
            if msg.get("role") == "assistant":
                model = msg.get("model")
                if model:
                    self.models.add(str(msg.get("provider", "?")) + "/" + str(model))
                if isinstance(msg.get("usage"), dict):
                    self.usage.append(msg["usage"])
        elif kind in {"auto_retry_start", "summarization_retry_scheduled"}:
            self.retries += 1

    def summary(self, wall):
        tool_s = interval_union(self.intervals)
        tokens = {}
        for key in ("input", "output", "cacheRead", "cacheWrite", "totalTokens"):
            vs = [u[key] for u in self.usage if isinstance(u.get(key), (int, float))]
            tokens[key] = sum(vs) if vs else None
        costs = [u.get("cost", {}).get("total") for u in self.usage if isinstance(u.get("cost"), dict)]
        costs = [c for c in costs if isinstance(c, (int, float))]
        return dict(first_stdout_s=self.first_output_s, first_model_delta_s=self.first_model_delta_s,
                    first_text_delta_s=self.first_text_s, event_count=self.event_count,
                    unparsed_lines=self.invalid_lines, protocol_event_count=self.protocol_events,
                    tool_event_intervals_union_s=tool_s if self.protocol_events else None,
                    remaining_unattributed_s=max(0, wall - tool_s) if self.protocol_events else None, tool_calls=self.tools,
                    unclosed_tool_events=len(self.tool_open), retries=self.retries,
                    observed_models=sorted(self.models), final_assistant_usage=tokens,
                    provider_reported_cost_sum=sum(costs) if costs else None,
                    accounting_note="Only final assistant-message usage; may omit retries/compaction. Cost is reported metadata, not a billing guarantee. Remaining time is not measured cloud time.")


def live_run(command, prompt, work, out, checkpoint, timeout):
    """No shell, drain both streams continuously, preserve receipt timestamps."""
    parsed, buffers = PiEvents(), {"stdout": b"", "stderr": b""}
    started, usage_before = time.monotonic(), resource.getrusage(resource.RUSAGE_CHILDREN)
    record = {"executable": command[0], "command_sha256": hashlib.sha256(json.dumps(command).encode()).hexdigest(),
              "arguments_note": "Arguments omitted to avoid persisting inline credentials; requested model is recorded separately.", "status": "RUNNING"}
    write_json(out / "invocation.json", record)
    (out / "prompt.txt").write_text(prompt)
    p = subprocess.Popen(command + [prompt], cwd=work, env=base.ENV, stdin=subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    selector = selectors.DefaultSelector()
    for name, stream in (("stdout", p.stdout), ("stderr", p.stderr)):
        os.set_blocking(stream.fileno(), False)
        selector.register(stream, selectors.EVENT_READ, name)
    byte_count, next_progress = 0, 20
    try:
        with (out / "agent-stdout.jsonl").open("wb") as stdout, (out / "agent-stderr.txt").open("wb") as stderr, (out / "event-receipts.jsonl").open("w") as receipts:
            sinks = {"stdout": stdout, "stderr": stderr}
            while selector.get_map() or p.poll() is None:
                checkpoint()
                elapsed = time.monotonic() - started
                if elapsed > timeout:
                    record["status"] = "TIMEOUT"
                    break
                if elapsed >= next_progress:
                    print("    " + t("agent.progress", elapsed=elapsed, tools=len(parsed.tools)), flush=True)
                    next_progress += 20
                for key, _ in selector.select(timeout=0.1):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    elapsed = time.monotonic() - started
                    name = key.data
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    byte_count += len(chunk)
                    if byte_count > 32 * 1024**2:
                        raise base.Stopped(t("agent.output_too_large"))
                    sinks[name].write(chunk)
                    sinks[name].flush()
                    if name == "stdout":
                        if parsed.first_output_s is None:
                            parsed.first_output_s = elapsed
                        buffers[name] += chunk
                        while b"\n" in buffers[name]:
                            line, buffers[name] = buffers[name].split(b"\n", 1)
                            parsed.feed(line.rstrip(b"\r"), elapsed)
                            receipts.write(json.dumps({"elapsed_s": elapsed, "event_line": line.decode("utf-8", "replace")}, ensure_ascii=False) + "\n")
                if p.poll() is not None and elapsed > timeout:
                    break
        if buffers["stdout"].strip():
            parsed.feed(buffers["stdout"], time.monotonic() - started)
        if record["status"] != "TIMEOUT":
            record["status"] = "EXITED" if p.returncode == 0 else "AGENT_ERROR"
    except BaseException as e:
        record["status"] = "INTERRUPTED" if isinstance(e, KeyboardInterrupt) else "ERROR"
        record["error"] = str(e)
        raise
    finally:
        kill_group(p)
        selector.close()
        p.stdout.close()
        p.stderr.close()
        elapsed = time.monotonic() - started
        ru = resource.getrusage(resource.RUSAGE_CHILDREN)
        record.update(wall_s=elapsed, returncode=p.returncode,
                      reaped_child_cpu_s=ru.ru_utime + ru.ru_stime - usage_before.ru_utime - usage_before.ru_stime,
                      events=parsed.summary(elapsed))
        write_json(out / "invocation.json", record)
    return record


def local_round(path, checkpoint):
    return agent.run_local_replay(path, checkpoint)


def keep_code(work, destination, maximum=16 * 1024**2):
    """Retain bounded ordinary source files, never follow agent-created symlinks."""
    destination.mkdir()
    used = 0
    for root, dirs, files in os.walk(work, followlinks=False):
        dirs[:] = [d for d in dirs if d not in {"__pycache__", ".git", "node_modules", ".venv"} and not (Path(root) / d).is_symlink()]
        for name in files:
            p = Path(root) / name
            if p.is_symlink() or not p.is_file() or p.suffix not in {".py", ".md", ".toml", ".txt", ".json"}:
                continue
            size = p.stat().st_size
            if used + size > maximum:
                continue
            dest = destination / p.relative_to(work)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, dest)
            used += size
    return used


def agent_mode(args, root, out, monitor):
    records = {"local_replay": [], "live": [], "live_requested": args.live}
    # Local-only rounds always use an identical fixture, even for live comparisons.
    for n in range(1, (1 if args.quick else 3) + 1):
        print(t("agent.replay_round", n=n), flush=True)
        monitor.phase = f"local-replay-{n}"
        work = root / f"replay-{n}"
        record = local_round(work, monitor.check)
        records["local_replay"].append(record)
        write_json(out / "agent-results.json", records)
        shutil.rmtree(work)
    if not args.live:
        return records
    command = shlex.split(args.agent_command) if args.agent_command else ["pi", "--mode", "json"]
    if not command or not shutil.which(command[0]):
        raise base.Stopped(t("agent.command_missing"))
    if not args.agent_command:
        help_text = base.query([command[0], "--help"])["stdout"]
        if "--no-session" in help_text:
            command.append("--no-session")
        if args.model:
            command += ["--model", args.model]
        if args.provider:
            command += ["--provider", args.provider]
    records["agent_version"] = base.query([command[0], "--version"])
    records["requested_model"] = args.model
    records["config_hashes"] = {str(p.relative_to(Path.home())): hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in (Path.home() / ".pi/agent/settings.json", Path.home() / ".pi/agent/AGENTS.md", Path.home() / "AGENTS.md") if p.is_file()}
    print(t("agent.live_banner", rounds=args.rounds, timeout=args.timeout), flush=True)
    print(t("agent.sandbox_note"), flush=True)
    for n in range(1, args.rounds + 1):
        monitor.phase = f"live-agent-{n}"
        work, logs = root / f"live-{n}", out / f"live-{n}"
        logs.mkdir()
        fixture = agent.generate_fixture(work)
        write_json(logs / "fixture.json", {k: v for k, v in fixture.items() if k != "prompt"})
        record = {"invocation": {"status": "STARTING"}, "acceptance": {"passed": False, "status": "NOT_EVALUATED"}, "success": False}
        records["live"].append(record)
        write_json(out / "agent-results.json", records)
        try:
            record["invocation"] = live_run(command, fixture["prompt"], work, logs, monitor.check, args.timeout)
            monitor.phase = f"acceptance-{n}"
            record["acceptance"] = agent.evaluate_agent_workspace(work, checkpoint=monitor.check)
            record["success"] = record["invocation"]["status"] == "EXITED" and bool(record["acceptance"].get("passed"))
        finally:
            if (logs / "invocation.json").exists():
                record["invocation"] = json.loads((logs / "invocation.json").read_text())
            keep_code(work, logs / "submitted-code")
            write_json(out / "agent-results.json", records)
        shutil.rmtree(work)
    return records


def replay_phase(label, seconds, root, monitor):
    monitor.phase = label
    started, runs = time.monotonic(), []
    while not runs or time.monotonic() - started < seconds:
        monitor.check()
        work = root / f"{label}-{len(runs)}"
        r = local_round(work, monitor.check)
        runs.append(r)
        shutil.rmtree(work)
        # Deliberately fixed idle gap; this is intermittent development work, not max CPU torture.
        monitor.pause(0.5, label)
    successful = [r["total_s"] for r in runs if r.get("passed")]
    return {"phase": label, "elapsed_s": time.monotonic() - started, "runs": runs,
            "median_task_s": median(successful), "cycles": len(runs), "passed_cycles": len(successful),
            "failed_cycles": len(runs) - len(successful)}


def daily_mode(args, root, out, monitor):
    records = {"phases": [], "observe_real_update": args.observe_update,
               "browser_complete": False, "browser_errors": []}
    browser = daily.BrowserSession(root / "browser", out / "browser", tabs=2 if args.quick else args.tabs)
    update_proc = update_space = update_stdout = update_stderr = None
    update_results, expected_browser_phases = {}, []
    completed_workload = False
    try:
        if not args.observe_update:
            print(t("daily.phase1"), flush=True)
            records["phases"].append(replay_phase("programming-alone", args.seconds, root, monitor))
        print(t("daily.open_browser"), flush=True)
        records["browser_start"] = browser.start()
        browser.set_phase("browser-idle-settle")
        monitor.pause(1 if args.quick else 2, "browser-idle-settle")
        browser.set_phase("browser-idle")
        expected_browser_phases.append("browser-idle")
        monitor.pause(3 if args.quick else 15, "browser-idle")
        if args.observe_update:
            records["packages_before"] = base.query(["pacman", "-Q"])
            browser.set_phase("real-update-observation-settle")
            monitor.pause(2, "real-update-observation-settle")
            browser.set_phase("real-update-observation")
            expected_browser_phases.append("real-update-observation")
            print(t("daily.observe_banner", seconds=args.seconds), flush=True)
            observation_started = time.monotonic()
            try:
                records["phases"].append(replay_phase("real-update-observation", args.seconds, root, monitor))
            except KeyboardInterrupt:
                records["observation_ended_by_user"] = True
            records["observation_elapsed_s"] = time.monotonic() - observation_started
            browser.set_phase("recovery")
            monitor.phase = "recovery"
            records["packages_after"] = base.query(["pacman", "-Q"])
            valid_packages = all(records[k].get("rc") == 0 for k in ("packages_before", "packages_after"))
            records["package_observation_valid"] = valid_packages
            if valid_packages:
                before = set(records["packages_before"]["stdout"].splitlines())
                after = set(records["packages_after"]["stdout"].splitlines())
                records["package_version_lines_added"] = sorted(after - before)
                records["package_version_lines_removed"] = sorted(before - after)
            else:
                records["package_version_lines_added"] = None
                records["package_version_lines_removed"] = None
                records["browser_errors"].append(t("daily.pacman_failed"))
            records["note"] = "Observation window with fixed local programming replay, not measured full update duration. An update may still be in progress. Package snapshots cannot prove update completion. Not a repeatable benchmark."
        else:
            print(t("daily.phase2"), flush=True)
            browser.set_phase("tabs-programming-settle")
            monitor.pause(2, "tabs-programming-settle")
            browser.set_phase("tabs-programming")
            expected_browser_phases.append("tabs-programming")
            records["phases"].append(replay_phase("tabs-programming", args.seconds, root, monitor))
            browser.set_phase("between-scenarios")
            print(t("daily.phase3"), flush=True)
            browser.set_phase("tabs-programming-update-sim-settle")
            monitor.pause(2, "tabs-programming-update-sim-settle")
            # Keep this worker's private files outside the main TemporaryDirectory
            # but on the same tested filesystem. If a process cannot be reaped,
            # the main cleanup will never race its remaining disk operations.
            update_space = Path(tempfile.mkdtemp(prefix=".omarchy-update-load-", dir=root.parent))
            module_root = getattr(daily.__loader__, "archive", None) or str(Path(daily.__file__).parent)
            worker_code = r"""
import json, signal, sys, threading
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import bench_daily, i18n
i18n.set_language(sys.argv[3])
stop = threading.Event()
signal.signal(signal.SIGTERM, lambda *_: stop.set())
signal.signal(signal.SIGINT, lambda *_: stop.set())
try:
    result = bench_daily.simulated_update(Path(sys.argv[2]), stop, lambda: None)
    print(json.dumps({"result": result}), flush=True)
except BaseException as exc:
    print(json.dumps({"error": str(exc)}), flush=True)
    raise
"""
            update_stdout = (out / "update-simulator-result.json").open("w")
            update_stderr = (out / "update-simulator.stderr.txt").open("w")
            browser.set_phase("tabs-programming-update-sim")
            expected_browser_phases.append("tabs-programming-update-sim")
            update_proc = subprocess.Popen([sys.executable, "-c", worker_code, str(module_root), str(update_space), i18n.current()],
                         stdin=subprocess.DEVNULL, stdout=update_stdout, stderr=update_stderr,
                         env=base.ENV, start_new_session=True)
            records["phases"].append(replay_phase("tabs-programming-update-sim", args.seconds, root, monitor))
            browser.set_phase("recovery")
            monitor.phase = "recovery"
        completed_workload = True
    finally:
        browser.set_phase("recovery")
        monitor.phase = "recovery"
        if update_proc:
            if update_proc.poll() is None:
                try:
                    os.killpg(update_proc.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    update_proc.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    update_results["error"] = t("daily.sim_not_stopped")
                    try:
                        os.killpg(update_proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    try:
                        update_proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        update_results["error"] += " " + t("daily.sim_not_reaped")
            if update_stdout:
                update_stdout.close()
            if update_stderr:
                update_stderr.close()
            result_path = out / "update-simulator-result.json"
            try:
                if result_path.stat().st_size > 65536:
                    raise ValueError("worker result too large")
                worker_result = json.loads(result_path.read_text())
                if isinstance(worker_result, dict):
                    for k, value in worker_result.items():
                        if k != "error" or "error" not in update_results:
                            update_results[k] = value
                else:
                    raise ValueError("worker result is not an object")
            except (OSError, ValueError) as exc:
                update_results.setdefault("error", t("daily.sim_no_result", error=exc))
            update_results["returncode"] = update_proc.poll()
            if update_proc.poll() not in (None, 0):
                update_results.setdefault("error", t("daily.sim_exit", code=update_proc.returncode))
        elif update_stdout or update_stderr:
            for f in (update_stdout, update_stderr):
                if f:
                    f.close()
        if update_space:
            if update_proc is None or update_proc.poll() is not None:
                try:
                    shutil.rmtree(update_space)
                except OSError as exc:
                    update_results["cleanup_error"] = str(exc)
                    update_results["retained_workspace"] = str(update_space)
            else:
                update_results["retained_workspace"] = str(update_space)
        records["update_simulator"] = update_results
        records["browser_metrics"] = browser.metrics()
        durations = {p["phase"]: p["elapsed_s"] for p in records["phases"]}
        durations["browser-idle"] = 3 if args.quick else 15
        durations.setdefault("real-update-observation", records.get("observation_elapsed_s", args.seconds))
        records["browser_coverage"] = {}
        minimum_coverage = .25 if args.quick else .60
        for phase in expected_browser_phases:
            metrics = records["browser_metrics"].get("phases", {}).get(phase, {})
            if metrics.get("measurement_status") != "OBSERVED":
                records["browser_errors"].append(t("daily.browser_insufficient", phase=phase))
            expected_s = durations.get(phase, args.seconds)
            observed_s = metrics.get("visible_ms", 0) / 1000
            ratio = observed_s / expected_s if expected_s else 0
            records["browser_coverage"][phase] = {"expected_wall_s": expected_s,
                "observed_foreground_s": observed_s, "coverage_ratio": ratio,
                "minimum_required_ratio": minimum_coverage}
            if ratio < minimum_coverage:
                records["browser_errors"].append(t("daily.browser_coverage_low", phase=phase, ratio=ratio, minimum=minimum_coverage))
        for key in ("missing_pages", "stale_pages"):
            if records["browser_metrics"].get(key):
                records["browser_errors"].append(t("daily.browser_key", key=key, value=records["browser_metrics"][key]))
        if browser.proc is not None and browser.proc.poll() is not None:
            records["browser_errors"].append(t("daily.browser_exited"))
        if update_results.get("error"):
            records["browser_errors"].append(update_results["error"])
        elif update_proc and update_results.get("result", {}).get("files_written", 0) < 1:
            records["browser_errors"].append(t("daily.sim_no_files"))
        # Preserve the complete record even if closing a browser/profile fails.
        try:
            browser.close()
        except Exception as exc:
            records["browser_errors"].append(t("daily.browser_cleanup_failed", error=exc))
        finally:
            records["browser_complete"] = completed_workload and bool(expected_browser_phases) and not records["browser_errors"]
            records["measurement_note"] = t("daily.measurement_note")
            write_json(out / "daily-results.json", records)
    return records


def report(out, data, rows):
    meta, result = data["metadata"], data.get("result", {})
    lines = [f"Omarchy Lab {VERSION} | {data['mode']} | {data['status']}",
             t("report.config", machine=meta["machine_model"], cpu=meta["cpu_model"], kernel=meta["kernel"]),
             t("report.dir", work_dir=meta["work_dir"], mount=meta["mount"]), ""]
    if data["mode"] == "agent":
        replay = result.get("local_replay", [])
        ts = [r["total_s"] for r in replay if r.get("passed")]
        if ts:
            lines.append(t("agent.replay_median", median=median(ts), n=len(ts), values=", ".join(f"{v:.3f}" for v in ts)))
        lines.append(t("agent.replay_passed", passed=sum(bool(r.get("passed")) for r in replay), total=len(replay)))
        live = result.get("live", [])
        if live:
            lines.append(t("agent.live_passed", passed=sum(r["success"] for r in live), total=len(live)))
            for i, r in enumerate(live, 1):
                inv = r["invocation"]
                ev = inv.get("events")
                if ev is None:
                    lines.append("  " + t("agent.round_incomplete", i=i, status=inv.get("status")))
                    continue
                counts = (f"{len(ev['tool_calls'])} / {sum(c['is_error'] for c in ev['tool_calls'])} / {ev['retries']}"
                          if ev.get("protocol_event_count") else t("common.not_observed"))
                lines += ["  " + t("agent.round_line", i=i, status=inv["status"], wall=inv.get("wall_s", 0),
                                   passed=t("common.pass") if r["acceptance"].get("passed") else t("common.fail")),
                          "    " + t("agent.model", models=", ".join(ev["observed_models"]) or t("agent.model_unknown")),
                          "    " + t("agent.first_delta", delta=num(ev["first_model_delta_s"], 3, "s"), text=num(ev["first_text_delta_s"], 3, "s")),
                          "    " + t("agent.tool_union", union=num(ev["tool_event_intervals_union_s"], 3, "s"),
                                       remaining=num(ev["remaining_unattributed_s"], 3, "s")),
                          "    " + t("agent.tool_counts", counts=counts)]
        elif result.get("live_requested"):
            lines.append(t("agent.live_no_result"))
        else:
            lines.append(t("agent.no_model"))
        lines += [t("agent.note_e2e"), t("agent.note_first_output"), t("agent.note_rounds")]
    else:
        phases = result.get("phases", [])
        first = phases[0].get("median_task_s") if phases else None
        for p in phases:
            ratio = p["median_task_s"] / first if first and p["median_task_s"] is not None else None
            lines.append(t("daily.phase_line", phase=p["phase"], median=num(p["median_task_s"], 3, "s"),
                           passed=p["passed_cycles"], cycles=p["cycles"], ratio=num(ratio, 2, "x")))
        lines.append(t("daily.browser_header"))
        for label, v in result.get("browser_metrics", {}).get("phases", {}).items():
            lines.append("  " + t("daily.browser_line", label=label, status=v.get("measurement_status"),
                                  raf=num(v.get("raf_interval_ms", {}).get("p95_ms"), 1, "ms"),
                                  timer=num(v.get("timer_lateness_ms", {}).get("p95_ms"), 1, "ms")))
        lines += [t("daily.note_raf"), t("daily.note_fixture")]
        if result.get("observe_real_update"):
            lines += [t("daily.real_update_note"),
                      t("daily.packages_changed", added=len(result.get("package_version_lines_added") or []),
                        removed=len(result.get("package_version_lines_removed") or []))
                      if result.get("package_observation_valid") else t("daily.packages_unknown")]
        else:
            lines.append(t("daily.sim_phase_note"))
    valid = [r for r in rows if r.get("cpu_max_c") is not None]
    lines += ["", t("report.cpu_peak", peak=max(r["cpu_max_c"] for r in valid)) if valid else t("report.no_sensor")]
    if rows:
        lines.append(t("report.mem_swap", mem=min(r["mem_available_mib"] for r in rows), swap=max(r["swap_used_mib"] for r in rows)))
        lines.append(t("report.phase_samples"))
        labels = list(dict.fromkeys(r['phase'] for r in rows))
        for label in labels:
            if 'settle' in label or label in {'setup', 'recovery'}:
                continue
            group = [r for r in rows if r['phase'] == label]
            cpu = [r['cpu_busy_pct'] for r in group if r['cpu_busy_pct'] is not None]
            wait = [r['iowait_pct'] for r in group if r['iowait_pct'] is not None]
            lines.append("  " + t("report.phase_sample_line", label=label, n=len(group),
                                  cpu=num(statistics.mean(cpu) if cpu else None, 1, "%"),
                                  wait=num(statistics.mean(wait) if wait else None, 1, "%")))
    lines += ["", t("report.notes_header")] + ["- " + n for n in data.get("notes", [])]
    lines += ["- " + t("report.note_no_score"), "- " + t("report.note_storage"), "- " + t("report.note_quick"),
              "", t("report.path", path=out / "report.txt")]
    text = "\n".join(lines) + "\n"
    (out / "report.txt").write_text(text)
    print("\n" + text, flush=True)


def main():
    i18n.setup(sys.argv[1:], interactive=len(sys.argv) > 1 and sys.argv[1] in ("agent", "daily", "typical"))
    if len(sys.argv) > 1 and sys.argv[1] == "typical":
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        if not any(v == '--output-dir' or v.startswith('--output-dir=') for v in sys.argv):
            sys.argv += ['--output-dir', str(Path.home() / 'omarchy-lab')]
        return base.main()
    ap = argparse.ArgumentParser(description=t("help.lab_description", version=VERSION), formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["agent", "daily", "typical"])
    ap.add_argument("--live", action="store_true", help=t("help.live"))
    ap.add_argument("--agent-command", help=t("help.agent_command"))
    ap.add_argument("--model", help=t("help.model"))
    ap.add_argument("--provider", help=t("help.provider"))
    ap.add_argument("--rounds", type=int, default=1, choices=range(1, 6), metavar="1..5", help=t("help.rounds"))
    ap.add_argument("--timeout", type=int, default=600, help=t("help.timeout"))
    ap.add_argument("--seconds", type=int, default=None, help=t("help.seconds"))
    ap.add_argument("--tabs", type=int, default=8, choices=range(2, 17), metavar="2..16", help=t("help.tabs"))
    ap.add_argument("--observe-update", action="store_true", help=t("help.observe_update"))
    ap.add_argument("--quick", action="store_true", help=t("help.quick"))
    ap.add_argument("--work-dir", type=Path, default=Path.home(), help=t("help.work_dir"))
    ap.add_argument("--output-dir", type=Path, default=Path.home() / "omarchy-lab", help=t("help.output_dir", path="~/omarchy-lab"))
    ap.add_argument("--stop-temp", type=int, default=90, choices=range(60, 96), metavar="60..95", help=t("help.stop_temp"))
    i18n.add_argument(ap)
    args = ap.parse_args()
    if sys.platform != "linux" or os.geteuid() == 0:
        ap.error(t("err.linux_user"))
    if args.mode != "agent" and (args.live or args.agent_command or args.model or args.provider):
        ap.error(t("err.agent_only"))
    if args.mode != "daily" and args.observe_update:
        ap.error(t("err.observe_daily_only"))
    if args.live and args.quick:
        ap.error(t("err.quick_live"))
    if args.agent_command and (args.model or args.provider):
        ap.error(t("err.custom_model"))
    if (args.agent_command or args.model or args.provider) and not args.live:
        ap.error(t("err.needs_live"))
    if args.provider and not args.model:
        ap.error(t("err.provider_model"))
    if not 60 <= args.timeout <= 1800:
        ap.error(t("err.timeout_range"))
    args.seconds = args.seconds if args.seconds is not None else (4 if args.quick else 600 if args.observe_update else 60)
    if not 2 <= args.seconds <= 1800:
        ap.error(t("err.seconds_range"))
    target = args.work_dir.expanduser().resolve(strict=True)
    if not target.is_dir() or any(target == Path(p) or Path(p) in target.parents for p in ("/dev", "/proc", "/sys")):
        ap.error(t("err.plain_dir"))
    if shutil.disk_usage(target).free < 1024**3:
        ap.error(t("err.space_1g"))
    output = args.output_dir.expanduser().resolve()
    output.mkdir(parents=True, mode=0o700, exist_ok=True)
    lock = (output / ".run.lock").open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        ap.error(t("err.locked"))
    out = Path(tempfile.mkdtemp(prefix=dt.datetime.now().strftime("%Y%m%d-%H%M%S-"), dir=output))
    monitor = base.Monitor(out, args.stop_temp)
    cpu = re.search(r"^model name\s*:\s*(.+)", base.read("/proc/cpuinfo"), re.M)
    meta = {"started": dt.datetime.now().astimezone().isoformat(), "kernel": platform.release(),
            "machine_model": base.read("/sys/class/dmi/id/product_name"), "cpu_model": cpu[1] if cpu else platform.machine(),
            "work_dir": str(target), "mount": base.mount_at(target), "python": sys.version,
            "display": base.query(["hyprctl", "monitors", "-j"]), "quick": args.quick, "language": i18n.current(),
            "governors": {str(p): base.read(p) for p in Path('/sys/devices/system/cpu/cpufreq').glob('policy*/scaling_governor')},
            "argv": [v if i == 0 or sys.argv[i] != '--agent-command' else '<custom command omitted>' for i, v in enumerate(sys.argv[1:])],
            "source_sha256": {m.__name__: hashlib.sha256(m.__loader__.get_data(m.__file__)).hexdigest() for m in (sys.modules[__name__], base, agent, daily, i18n)},
            "fixture_versions": {"agent": agent.FIXTURE_VERSION, "daily": daily.FIXTURE_VERSION}}
    # --agent-command=... is also accepted by argparse; keep it out of reports.
    meta['argv'] = ['--agent-command=<omitted>' if v.startswith('--agent-command=') else v for v in meta['argv']]
    data = {"version": VERSION, "mode": args.mode, "metadata": meta, "notes": [], "status": "RUNNING"}
    monitor.thread.start()
    def interrupted(signum, frame):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM, interrupted)
    print(t("run.banner", version=VERSION, mode=args.mode, out=out), flush=True)
    with tempfile.TemporaryDirectory(prefix=".omarchy-lab-", dir=target) as tmp:
        try:
            monitor.pause(1 if args.quick else 10, "idle-baseline")
            data["result"] = agent_mode(args, Path(tmp), out, monitor) if args.mode == "agent" else daily_mode(args, Path(tmp), out, monitor)
            data["status"] = "COMPLETE"
            result = data["result"]
            if args.mode == "agent" and (any(not r.get("passed") for r in result.get("local_replay", [])) or any(not r["success"] for r in result.get("live", []))):
                data["status"] = "COMPLETED_WITH_TASK_FAILURES"
            if args.mode == "daily" and any(p.get("failed_cycles") for p in result.get("phases", [])):
                data["status"] = "COMPLETED_WITH_TASK_FAILURES"
            if args.mode == "daily" and not result.get("browser_complete", False):
                data["status"] = "INCOMPLETE"
                data["notes"].extend(result.get("browser_errors", [t("daily.browser_incomplete")]))
        except KeyboardInterrupt:
            data["status"] = "INTERRUPTED"
            data["notes"].append(t("run.interrupted"))
        except Exception as e:
            data["status"] = "INCOMPLETE"
            data["notes"].append(str(e))
        finally:
            monitor.done.set()
            monitor.thread.join(timeout=3)
            # Recover already-written partial results on interruption/failure.
            partial = out / ("agent-results.json" if args.mode == "agent" else "daily-results.json")
            if "result" not in data and partial.exists():
                data["result"] = json.loads(partial.read_text())
            write_json(out / "results.json", data)
            report(out, data, monitor.rows)
    lock.close()
    return 0 if data["status"] == "COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
