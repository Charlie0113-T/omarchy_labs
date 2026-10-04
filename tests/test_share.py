"""Checks for the shared GitHub issue and for translatable notes.

Run from the repository root: python3 -m unittest discover -s tests
"""
import contextlib
import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

import bench_base  # noqa: E402
import i18n  # noqa: E402
from i18n import t  # noqa: E402
import share  # noqa: E402

CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿＀-￯]")
HOME = str(Path.home())


def rows():
    return [{"phase": "programming-alone", "cpu_busy_pct": 20.0, "iowait_pct": 1.1, "cpu_max_c": 70.0,
             "mem_available_mib": 12000.0, "swap_used_mib": 0.0},
            {"phase": "tabs-programming", "cpu_busy_pct": 40.0, "iowait_pct": None, "cpu_max_c": 86.0,
             "mem_available_mib": 11797.0, "swap_used_mib": 0.0}]


def lab_meta(language):
    return {"machine_model": "Macmini7,1", "cpu_model": "Intel(R) Core(TM) i7-4578U CPU @ 3.00GHz",
            "kernel": "7.2.5-3-omarchy", "work_dir": HOME, "started": "2026-10-04T10:00:00-04:00",
            "mount": {"source": "/dev/mapper/root[/@home]", "fstype": "btrfs", "options": "rw,relatime,compress=zstd:3"},
            "memory_total_bytes": 16632000000, "omarchy_version": {"rc": 0, "stdout": "3.1.0"},
            "test_disks": [{"name": "sda", "model": "APPLE HDD HTS541010A9E662", "rota": True}],
            "quick": False, "language": language}


def daily_data(language):
    phases = {"browser-idle": {"measurement_status": "OBSERVED", "raf_interval_ms": {"p95_ms": 33.4},
                               "timer_lateness_ms": {"p95_ms": 2.1}},
              "tabs-programming": {"measurement_status": "INSUFFICIENT_SAMPLES", "raf_interval_ms": {"p95_ms": None},
                                   "timer_lateness_ms": {"p95_ms": None}},
              "recovery": {"measurement_status": "INSUFFICIENT_SAMPLES"}}
    return {"version": "2.1", "mode": "daily", "status": "INCOMPLETE", "metadata": lab_meta(language),
            "notes": [t("daily.browser_insufficient", phase="tabs-programming"), t("daily.browser_exited")],
            "result": {"phases": [{"phase": "programming-alone", "median_task_s": 1.26, "passed_cycles": 30, "cycles": 30},
                                  {"phase": "tabs-programming", "median_task_s": 1.39, "passed_cycles": 28, "cycles": 28}],
                       "browser_metrics": {"phases": phases}, "observe_real_update": False}}


def agent_data(language):
    events = {"observed_models": ["openai-codex/gpt-6.1-sol"], "first_text_delta_s": 23.069,
              "tool_calls": [{"is_error": False}] * 14, "retries": 0, "protocol_event_count": 40}
    return {"version": "2.1", "mode": "agent", "status": "COMPLETE", "metadata": lab_meta(language), "notes": [],
            "result": {"local_replay": [{"passed": True, "total_s": 1.259}] * 3, "live_requested": True,
                       "live": [{"success": True, "acceptance": {"passed": True},
                                 "invocation": {"status": "EXITED", "wall_s": 110.04, "events": events}},
                                {"success": False, "acceptance": {}, "invocation": {"status": "ERROR"}}]}}


def typical_data(language):
    meta = {"machine_model": "Macmini7,1", "cpu_model": "Intel i7", "kernel": "7.2.5-3-omarchy",
            "test_directory": HOME, "started_local": "2026-10-04T10:00:00", "memory_total_bytes": 16632000000,
            "test_mount": {"source": "/dev/mapper/root[/@home]", "fstype": "btrfs", "options": "rw"},
            "test_disks": [], "omarchy_version": {"rc": 127, "stdout": ""}, "language": language,
            "sustained_last_vs_early_pct": 97.5, "swap_page_deltas": {"pswpin": 0, "pswpout": 0}}
    summary = [{"key": "cpu_single", "label": t("label.cpu_single"), "value": 362.86, "unit": "events/s",
                "lower_is_better": False, "samples": [360.1, 362.86, 365.0], "n": 3, "spread_pct": 1.4},
               {"key": "rand_p95", "label": t("label.rand_lat", suffix="p95"), "value": 15.27, "unit": "ms",
                "lower_is_better": True, "samples": [15.27], "n": 1, "spread_pct": 0.0}]
    return {"version": "1.0", "profile": "FULL-3-ROUNDS", "status": "INCOMPLETE", "metadata": meta, "summary": summary,
            "notes": [t("note.spread", label=t("label.cpu_single"), spread=21.3)],
            "failures": [i18n.message(bench_base.Stopped(t("mon.temp_stop", temp=90.0, limit=90)))]}


BUILDERS = {"daily": daily_data, "agent": agent_data, "typical": typical_data}


class IssueTest(unittest.TestCase):
    def tearDown(self):
        i18n.set_language("en")

    def compose(self, kind, code):
        i18n.set_language(code)  # notes are created in the run's language, as in a real run
        data = BUILDERS[kind](code)
        return share.compose(kind, data, rows())

    def test_english_first_then_collapsed_translation(self):
        for kind in BUILDERS:
            for code in i18n.LANGUAGES:
                text = self.compose(kind, code)
                english, _, rest = text.partition("<details>")
                self.assertTrue(english.startswith("### Summary"), (kind, code))
                self.assertIsNone(CJK.search(english), (kind, code, CJK.search(english)))
                self.assertIn("### Feedback / questions", english)
                if code == "en":
                    self.assertEqual(rest, "", kind)
                else:
                    self.assertIn(i18n.NAMES[code], rest)
                    self.assertIn("### " + i18n.MESSAGES["issue.summary"][i18n.LANGUAGES.index(code)], rest)
                    self.assertIsNotNone(CJK.search(rest), (kind, code))
                    self.assertTrue(rest.rstrip().endswith("</sub>"))

    def test_fixed_sections_in_order(self):
        for kind in BUILDERS:
            english = self.compose(kind, "ja").partition("<details>")[0]
            headings = re.findall(r"^### (.+)$", english, re.M)
            self.assertEqual(headings, ["Summary", "Device and storage", "Results", "Notes from the run",
                                        "Feedback / questions"], kind)

    def test_no_missing_values_or_home_path(self):
        for kind in BUILDERS:
            for code in i18n.LANGUAGES:
                text = self.compose(kind, code)
                self.assertNotIn("None", text, (kind, code))
                self.assertNotIn(HOME, text, (kind, code))
                self.assertIn("`~`", text, (kind, code))

    def test_tables_have_matching_columns(self):
        for kind in BUILDERS:
            for line_group in re.findall(r"((?:^\|.*\|$\n?)+)", self.compose(kind, "zh-TW"), re.M):
                widths = {len(re.split(r"(?<!\\)\|", line)) for line in line_group.strip().splitlines()}
                self.assertEqual(len(widths), 1, (kind, line_group))

    def test_notes_are_translated_in_english_copy(self):
        text = self.compose("daily", "zh-CN")
        english, _, translated = text.partition("<details>")
        self.assertIn("tabs-programming: not enough visible-page samples", english)
        self.assertIn("The browser exited before measurement finished.", english)
        self.assertIn("浏览器在测量完成前退出。", translated)

    def test_typical_failure_from_exception_is_translated(self):
        english = self.compose("typical", "ja").partition("<details>")[0]
        self.assertIn("CPU temperature reached 90.0°C", english)
        self.assertIn("CPU single-thread: range/median is 21.3%", english)
        self.assertIn("unknown (not detected automatically)", english)

    def test_agent_rounds_table(self):
        english = self.compose("agent", "en")
        self.assertIn("| 1 | EXITED | 110.04s | PASS | openai-codex/gpt-6.1-sol | 23.069s | 14 / 0 / 0 |", english)
        self.assertIn("| 2 | ERROR | N/A | FAIL | N/A | N/A | not observed |", english)

    def test_title(self):
        self.assertEqual(share.title("daily", daily_data("en")), "Test report: Omarchy Lab 2.1 daily on Macmini7,1 (HDD)")
        self.assertEqual(share.title("typical", typical_data("en")), "Test report: Omarchy Lab 2.1 typical on Macmini7,1")

    def test_offer_writes_issue_and_prints_guidance_in_run_language(self):
        i18n.set_language("ja")
        data = daily_data("ja")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "report.en.txt").write_text("x")
            printed = io.StringIO()
            with contextlib.redirect_stdout(printed):
                path = share.offer(out, "daily", data, rows())
            self.assertEqual(path, out / "issue.md")
            self.assertTrue(path.read_text().startswith("### Summary"))
        guidance = printed.getvalue()
        self.assertIn(i18n.MESSAGES["share.header"][3], guidance)
        self.assertIn("https://github.com/Charlie0113-T/omarchy_labs/issues/new?template=test-report.md&title=Test%20report", guidance)
        self.assertIn("report.en.txt", guidance)

    def test_offer_never_raises(self):
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            self.assertIsNone(share.offer(Path("/nonexistent/dir"), "daily", daily_data("en"), rows()))
        self.assertIn("Could not prepare the GitHub issue text", printed.getvalue())


class TextTest(unittest.TestCase):
    def tearDown(self):
        i18n.set_language("en")

    def test_message_renders_again_in_another_language(self):
        i18n.set_language("zh-TW")
        note = t("daily.browser_coverage_low", phase="tabs", ratio=0.42, minimum=0.6)
        self.assertIn("42%", note)
        self.assertIsNotNone(CJK.search(note))
        self.assertTrue(note.render("en").startswith("tabs: foreground sampling covered 42%"))

    def test_text_is_a_plain_string_for_json(self):
        self.assertEqual(json.loads(json.dumps({"n": t("issue.none")})), {"n": "No notes"})

    def test_nested_and_exception_values_follow_the_language(self):
        i18n.set_language("ja")
        exc = bench_base.Stopped(t("base.sysbench_cpu"))
        note = t("mon.failed", error=exc)
        self.assertIn("sysbench の CPU 出力", note)
        self.assertIn("Could not parse sysbench CPU output", i18n.localize(note, "en"))
        self.assertIs(i18n.message(exc), exc.args[0])
        self.assertEqual(i18n.message(ValueError("plain")), "plain")

    def test_using_restores_language(self):
        i18n.set_language("ja")
        with i18n.using("en"):
            self.assertEqual(t("issue.none"), "No notes")
        self.assertEqual(i18n.current(), "ja")


class DiskTest(unittest.TestCase):
    """The Issue #1 layout: Btrfs subvolume on LUKS on an HDD partition."""

    BLOCKS = {"blockdevices": [
        {"name": "sda", "path": "/dev/sda", "maj:min": "8:0", "type": "disk", "rota": True,
         "model": "APPLE HDD HTS541010A9E662", "tran": "sata", "size": 1000204886016,
         "children": [{"name": "sda1", "path": "/dev/sda1", "maj:min": "8:1", "type": "part"},
                      {"name": "sda2", "path": "/dev/sda2", "maj:min": "8:2", "type": "part",
                       "children": [{"name": "root", "path": "/dev/mapper/root", "maj:min": "253:0", "type": "crypt"}]}]},
        {"name": "sdb", "path": "/dev/sdb", "maj:min": "8:16", "type": "disk", "rota": False, "model": "APPLE SSD SM0128G"}]}

    def test_btrfs_on_luks_finds_the_hdd(self):
        mount = {"source": "/dev/mapper/root[/@home]", "fstype": "btrfs", "maj:min": "0:28"}
        disks = bench_base.disks_for_mount(self.BLOCKS, mount)
        self.assertEqual([d["name"] for d in disks], ["sda"])
        self.assertTrue(share.rotational(disks[0]))

    def test_device_number_match_still_works(self):
        disks = bench_base.disks_for_mount(self.BLOCKS, {"source": "/dev/sdb", "maj:min": "8:16"})
        self.assertEqual([d["name"] for d in disks], ["sdb"])

    def test_virtual_filesystems_match_nothing(self):
        self.assertEqual(bench_base.disks_for_mount(self.BLOCKS, {"source": "overlay", "maj:min": "0:74"}), [])


if __name__ == "__main__":
    unittest.main()
