"""Prepare a GitHub issue that shares a finished run, in one fixed format.

The body is English first, so every shared report reads the same and can be
searched and compared. When the run used another language, the same report
follows in that language in a collapsed section. Nothing is sent anywhere: the
tool saves issue.md and shows how to post it, and the person reviews it first.
"""
from pathlib import Path
import shlex
import shutil
import statistics
from urllib.parse import quote

import i18n
from i18n import num, t
from version import LAB_VERSION

REPO = "Charlie0113-T/omarchy_labs"
TEMPLATE = "test-report.md"
ENGLISH_NAMES = {"en": "English", "zh-CN": "Simplified Chinese", "zh-TW": "Traditional Chinese", "ja": "Japanese"}
# Settle, startup and recovery phases are bookkeeping; the issue shows the measured ones.
BROWSER_PHASES = ("browser-idle", "tabs-programming", "tabs-programming-update-sim", "real-update-observation")


def facts(kind, data):
    """One view of the run for both result shapes: typical (Omarchy Bench) and agent/daily."""
    meta = data.get("metadata", {})
    typical = kind == "typical"
    version = meta.get("omarchy_version") or {}
    return {
        "model": meta.get("machine_model") or "",
        "cpu": meta.get("cpu_model") or "",
        "memory": meta.get("memory_total_bytes"),
        "kernel": meta.get("kernel") or "",
        "omarchy": version.get("stdout") if version.get("rc") == 0 else None,
        "directory": meta.get("test_directory" if typical else "work_dir") or "",
        "mount": meta.get("test_mount" if typical else "mount") or {},
        "disks": meta.get("test_disks") or [],
        "started": (meta.get("started_local" if typical else "started") or "")[:19].replace("T", " "),
        "quick": str(data.get("profile", "")).startswith("QUICK") if typical else bool(meta.get("quick")),
        "language": meta.get("language") or "en",
    }


def title(kind, data):
    f = facts(kind, data)
    machine = f["model"] or f["cpu"] or "unknown machine"
    disk = next(iter(f["disks"]), None)
    medium = "" if disk is None else " (HDD)" if rotational(disk) else " (SSD)"
    return f"Test report: Omarchy Lab {LAB_VERSION} {kind} on {machine}{medium}"


def rotational(disk):
    return disk.get("rota") in (True, 1, "1")


def shorten(text, limit):
    return text if len(text) <= limit else text[:limit - 1] + "…"


def cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def table(header_key, rows):
    columns = [c.strip() for c in t(header_key).split("|")]
    lines = ["| " + " | ".join(columns) + " |", "|" + " --- |" * len(columns)]
    return lines + ["| " + " | ".join(cell(v) for v in row) + " |" for row in rows]


def phase_name(phase):
    key = "phase." + phase
    return t(key) if key in i18n.MESSAGES else phase


def mean(values):
    values = [v for v in values if v is not None]
    return statistics.mean(values) if values else None


def body(kind, data, rows, feedback):
    """The issue body in the current language."""
    f = facts(kind, data)
    run = "- " + t("issue.run", version=LAB_VERSION, mode=kind, status=data.get("status"))
    if f["quick"]:
        run += " · " + t("issue.quick")
    names = ENGLISH_NAMES if i18n.current() == "en" else i18n.NAMES
    lines = ["### " + t("issue.summary"), "", run,
             "- " + t("issue.language", name=f"{names.get(f['language'], f['language'])} (`{f['language']}`)",
                      started=f["started"] or "?"),
             "", "### " + t("issue.device"), ""]

    mount = f["mount"]
    disks = [f"{d.get('name')} · {d.get('model') or '?'} · {t('issue.rotational' if rotational(d) else 'issue.solid')}"
             for d in f["disks"]]
    device = [(t("issue.model"), f["model"] or "?"), (t("issue.cpu"), f["cpu"] or "?")]
    if f["memory"]:
        device.append((t("issue.memory"), f"{f['memory'] / 1024**3:.2f} GiB"))
    device.append((t("issue.kernel"), f["kernel"] or "?"))
    if f["omarchy"]:
        device.append((t("issue.omarchy"), f["omarchy"]))
    device += [(t("issue.test_dir"), f"`{f['directory']}`"),
               (t("issue.filesystem"), t("issue.fs_value", fstype=mount.get("fstype", "?"), source=mount.get("source", "?"))),
               (t("issue.mount_options"), f"`{shorten(str(mount.get('options', '?')), 160)}`"),
               (t("issue.disk"), "<br>".join(disks) or t("issue.disk_unknown"))]
    lines += table("issue.device_header", device)

    lines += ["", "### " + t("issue.results"), ""]
    lines += {"typical": typical_results, "agent": agent_results, "daily": daily_results}[kind](data, rows)
    peak = max((r["cpu_max_c"] for r in rows if r.get("cpu_max_c") is not None), default=None)
    lines.append("- " + (t("report.cpu_peak", peak=peak) if peak is not None else t("report.no_sensor")))
    if rows:
        lines.append("- " + t("report.mem_swap", mem=min(r["mem_available_mib"] for r in rows),
                              swap=max(r["swap_used_mib"] for r in rows)))

    notes = list(data.get("notes", [])) + list(data.get("failures", []))
    lines += ["", "### " + t("issue.notes"), ""]
    lines += ["- " + str(i18n.localize(n)) for n in notes] or ["- " + t("issue.none")]
    if feedback:
        lines += ["", "### " + t("issue.feedback"), "", t("issue.feedback_hint")]
    return "\n".join(lines)


def typical_results(data, rows):
    summary = [(f"{i18n.localize(r['label'])} {'↓' if r['lower_is_better'] else '↑'}", f"{r['value']:.2f} {r['unit']}",
                ", ".join(f"{v:.2f}" for v in r["samples"]), f"{r['spread_pct']:.1f}% (n={r['n']})")
               for r in data.get("summary", [])]
    lines = table("bench.table_header", summary) + [""] if summary else []
    meta = data.get("metadata", {})
    ratio = meta.get("sustained_last_vs_early_pct")
    if ratio is not None:
        lines.append("- " + t("bench.sustained", ratio=ratio))
    crc = t("bench.crc_pass") if "temporary_file_crc32c" in meta else t("bench.not_done")
    lines.append("- " + t("bench.crc", value=crc))
    if "swap_page_deltas" in meta:
        lines.append("- " + t("bench.swap", deltas=meta["swap_page_deltas"]))
    return lines


def agent_results(data, rows):
    result = data.get("result", {})
    replay = result.get("local_replay", [])
    times = [r["total_s"] for r in replay if r.get("passed")]
    lines = []
    if times:
        lines.append("- " + t("agent.replay_median", median=statistics.median(times), n=len(times),
                                values=", ".join(f"{v:.3f}" for v in times)))
    lines.append("- " + t("agent.replay_passed", passed=sum(bool(r.get("passed")) for r in replay), total=len(replay)))
    live = result.get("live", [])
    if live:
        lines.append("- " + t("agent.live_passed", passed=sum(bool(r.get("success")) for r in live), total=len(live)))
        rounds = []
        for i, r in enumerate(live, 1):
            inv, ev = r.get("invocation", {}), r.get("invocation", {}).get("events") or {}
            counts = (f"{len(ev['tool_calls'])} / {sum(c['is_error'] for c in ev['tool_calls'])} / {ev['retries']}"
                      if ev.get("protocol_event_count") else t("common.not_observed"))
            rounds.append((i, inv.get("status", "?"), num(inv.get("wall_s"), 2, "s"),
                           t("common.pass") if r.get("acceptance", {}).get("passed") else t("common.fail"),
                           ", ".join(ev.get("observed_models", [])) or t("common.na"),
                           num(ev.get("first_text_delta_s"), 3, "s"), counts))
        lines += [""] + table("issue.rounds_header", rounds) + [""]
    elif result.get("live_requested"):
        lines.append("- " + t("agent.live_no_result"))
    else:
        lines.append("- " + t("agent.no_model"))
    return lines


def daily_results(data, rows):
    result = data.get("result", {})
    phases = result.get("phases", [])
    first = phases[0].get("median_task_s") if phases else None
    scenarios = []
    for p in phases:
        ratio = p["median_task_s"] / first if first and p.get("median_task_s") is not None else None
        wait = mean(r.get("iowait_pct") for r in rows if r.get("phase") == p["phase"])
        scenarios.append((phase_name(p["phase"]), num(p.get("median_task_s"), 3, "s"),
                          f"{p.get('passed_cycles')}/{p.get('cycles')}", num(ratio, 2, "×"), num(wait, 1, "%")))
    lines = table("issue.daily_header", scenarios) + [""] if scenarios else []
    measured = result.get("browser_metrics", {}).get("phases", {})
    browser = [(phase_name(name), measured[name].get("measurement_status"),
                num(measured[name].get("raf_interval_ms", {}).get("p95_ms"), 1, " ms"),
                num(measured[name].get("timer_lateness_ms", {}).get("p95_ms"), 1, " ms"))
               for name in BROWSER_PHASES if name in measured]
    if browser:
        lines += table("issue.browser_header", browser) + [""]
    if result.get("observe_real_update"):
        lines.append("- " + (t("daily.packages_changed", added=len(result.get("package_version_lines_added") or []),
                                 removed=len(result.get("package_version_lines_removed") or []))
                             if result.get("package_observation_valid") else t("daily.packages_unknown")))
    else:
        lines.append("- " + t("daily.sim_phase_note"))
    return lines


def compose(kind, data, rows):
    """English body first; the run's own language follows, collapsed, when it differs."""
    code = facts(kind, data)["language"]
    with i18n.using("en"):
        parts = [body(kind, data, rows, feedback=True)]
    if code != "en":
        with i18n.using(code):
            translated = body(kind, data, rows, feedback=False)
        parts += ["", f"<details><summary>{i18n.NAMES[code]} · {ENGLISH_NAMES[code]}</summary>", "", translated, "", "</details>"]
    parts += ["", f"<sub>Generated by Omarchy Lab {LAB_VERSION}</sub>", ""]
    # Keep the account name out of a public post.
    return "\n".join(parts).replace(str(Path.home()), "~")


def offer(out, kind, data, rows):
    """Save issue.md and explain, in the chosen language, how to post it. Never fails the run."""
    try:
        path = Path(out) / "issue.md"
        heading = title(kind, data)
        url = f"https://github.com/{REPO}/issues/new?template={TEMPLATE}&title={quote(heading)}"
        path.write_text(compose(kind, data, rows))
        # The Omarchy bar widget's "Share latest result" opens this link.
        (Path(out) / "issue-url.txt").write_text(url + "\n")
    except Exception as exc:
        print(t("share.failed", error=exc), flush=True)
        return None
    lines = ["", "── " + t("share.header") + " ──", "1. " + t("share.saved", path=path)]
    if i18n.current() != "en":
        lines.append("   " + t("share.languages", name=i18n.NAMES[i18n.current()]))
    lines += ["2. " + t("share.review"), "3. " + t("share.open"), "   " + url]
    if shutil.which("wl-copy"):
        lines.append("   " + t("share.copy", command=f"wl-copy < {shlex.quote(str(path))}"))
    if shutil.which("gh"):
        command = f"gh issue create -R {REPO} --title {shlex.quote(heading)} --body-file {shlex.quote(str(path))}"
        lines.append("   " + t("share.gh", command=command))
    attachment = Path(out) / ("report.en.txt" if (Path(out) / "report.en.txt").exists() else "report.txt")
    lines.append("4. " + t("share.attach", file=attachment))
    print("\n".join(lines), flush=True)
    return path
