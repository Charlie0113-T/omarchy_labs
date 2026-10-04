"""Checks for the message catalog, language selection and localized reports.

Run from the repository root: python3 -m unittest discover -s tests
"""
import contextlib
import io
import json
import re
import string
import sys
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

import i18n  # noqa: E402

CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿＀-￯]")


def fields(text):
    """Placeholder names and format specs, e.g. {('ratio', '.0%'), ('phase', '')}."""
    return {(name, spec) for _, name, spec, _ in string.Formatter().parse(text) if name is not None}


class Anything(dict):
    def __missing__(self, key):
        return 1.5


def code_without_catalog(path):
    text = path.read_text()
    return text.split("\nMESSAGES = {", 1)[0] if path.name == "i18n.py" else text


class FakeTTY(io.StringIO):
    def isatty(self):
        return True


class CatalogTest(unittest.TestCase):
    def test_every_entry_has_all_languages(self):
        for key, entry in i18n.MESSAGES.items():
            self.assertEqual(len(entry), len(i18n.LANGUAGES), key)
            for text in entry:
                self.assertIsInstance(text, str, key)
                self.assertTrue(text.strip(), key)

    def test_placeholders_match_english(self):
        for key, entry in i18n.MESSAGES.items():
            for code, text in zip(i18n.LANGUAGES[1:], entry[1:]):
                self.assertEqual(fields(text), fields(entry[0]), f"{key} [{code}]")

    def test_every_message_formats(self):
        for key, entry in i18n.MESSAGES.items():
            for text in entry:
                if fields(text):
                    text.format_map(Anything())

    def test_translations_are_in_the_right_script(self):
        for key, (en, zh_cn, zh_tw, ja) in i18n.MESSAGES.items():
            self.assertIsNone(CJK.search(en), key)
            self.assertIsNone(re.search(r"[぀-ヿ]", zh_cn + zh_tw), key)

    def test_code_uses_only_known_keys(self):
        for path in SRC.glob("*.py"):
            for key in re.findall(r"""\bt\(\s*["']([\w.]+)["']""", code_without_catalog(path)):
                self.assertIn(key, i18n.MESSAGES, f"{path.name}: {key}")

    def test_no_unused_keys(self):
        code = "\n".join(code_without_catalog(p) for p in SRC.glob("*.py"))
        dynamic = {f"page.title.{i}" for i in range(8)} | {k for k in i18n.MESSAGES if k.startswith("phase.")}
        unused = [k for k in i18n.MESSAGES if k not in dynamic and f'"{k}"' not in code and f"'{k}'" not in code]
        self.assertEqual(unused, [])

    def test_no_hard_coded_cjk_outside_catalog(self):
        for path in SRC.glob("*.py"):
            for number, line in enumerate(code_without_catalog(path).splitlines(), 1):
                if path.name == "i18n.py" and ("NAMES" in line or "Language /" in line):
                    continue  # the language menu shows each language in its own script
                self.assertIsNone(CJK.search(line), f"{path.name}:{number}: {line.strip()}")


class SelectionTest(unittest.TestCase):
    def setUp(self):
        i18n._configured = False
        i18n.set_language("en")

    def tearDown(self):
        i18n._configured = False
        i18n.set_language("en")

    def test_normalize(self):
        cases = {"en_US.UTF-8": "en", "ja_JP.UTF-8": "ja", "zh_CN.UTF-8": "zh-CN", "zh_TW.UTF-8": "zh-TW",
                 "zh-Hant": "zh-TW", "zh_HK.UTF-8": "zh-TW", "zh": "zh-CN", "ZH-tw": "zh-TW", "jp": "ja",
                 "C.UTF-8": None, "POSIX": None, "fr_FR.UTF-8": None, "": None}
        for value, expected in cases.items():
            self.assertEqual(i18n.normalize(value), expected, value)

    def test_flag_wins_over_everything(self):
        env = {"OMARCHY_LAB_LANG": "ja", "LANG": "zh_CN.UTF-8"}
        self.assertEqual(i18n.setup(["agent", "--lang", "zh-TW"], environ=env), "zh-TW")

    def test_flag_with_equals(self):
        self.assertEqual(i18n.setup(["daily", "--lang=ja"], environ={}), "ja")

    def test_flag_auto_follows_locale_without_asking(self):
        stdin = FakeTTY("4\n")
        self.assertEqual(i18n.setup(["agent", "--lang", "auto"], environ={"LANG": "ja_JP.UTF-8"},
                                    stdin=stdin, stdout=FakeTTY()), "ja")

    def test_environment_variable(self):
        self.assertEqual(i18n.setup(["agent"], environ={"OMARCHY_LAB_LANG": "zh-CN"}), "zh-CN")

    def test_non_terminal_follows_locale(self):
        env = {"LANGUAGE": "fr:ja", "LANG": "en_US.UTF-8"}
        self.assertEqual(i18n.setup(["agent"], environ=env, stdin=io.StringIO(), stdout=io.StringIO()), "ja")

    def test_unknown_locale_falls_back_to_english(self):
        self.assertEqual(i18n.setup(["agent"], environ={"LANG": "C.UTF-8"}, stdin=io.StringIO(), stdout=io.StringIO()), "en")

    def test_terminal_question_uses_answer(self):
        self.assertEqual(self._ask_with("3\n", {}), "zh-TW")

    def test_terminal_question_enter_keeps_locale(self):
        self.assertEqual(self._ask_with("\n", {"LANG": "ja_JP.UTF-8"}), "ja")

    def test_terminal_question_accepts_code_and_retries(self):
        self.assertEqual(self._ask_with("9\nzh-CN\n", {}), "zh-CN")

    def test_terminal_question_end_of_input_keeps_default(self):
        self.assertEqual(self._ask_with("", {"LANG": "zh_TW.UTF-8"}), "zh-TW")

    def test_help_never_asks(self):
        stdin = FakeTTY("4\n")
        self.assertEqual(i18n.setup(["agent", "--help"], environ={}, stdin=stdin, stdout=FakeTTY()), "en")

    def test_setup_runs_once(self):
        i18n.setup(["agent", "--lang", "ja"], environ={})
        self.assertEqual(i18n.setup(["agent", "--lang", "en"], environ={}), "ja")

    def test_parse_option(self):
        self.assertEqual(i18n.parse_option("auto"), "auto")
        self.assertEqual(i18n.parse_option("zh_tw"), "zh-TW")
        with self.assertRaises(Exception):
            i18n.parse_option("klingon")

    def _ask_with(self, typed, environ):
        answers = iter(typed.splitlines())

        def fake_input(prompt):
            try:
                return next(answers)
            except StopIteration:
                raise EOFError

        original = i18n.ask
        i18n.ask = lambda default, out=None: original(default, input_fn=fake_input, out=out)
        try:
            return i18n.setup(["agent"], environ=environ, stdin=FakeTTY(), stdout=FakeTTY())
        finally:
            i18n.ask = original


class ReportTest(unittest.TestCase):
    """Render real report() output in every language from results with missing values."""

    def tearDown(self):
        i18n.set_language("en")

    def render(self, data, rows):
        import lab
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            with contextlib.redirect_stdout(io.StringIO()):
                lab.report(out, data, rows)
            return (out / "report.txt").read_text()

    def meta(self):
        return {"machine_model": "Macmini7,1", "cpu_model": "Intel i7", "kernel": "7.2", "work_dir": "/home/u", "mount": {}}

    def rows(self):
        return [{"phase": "browser-idle", "cpu_busy_pct": None, "iowait_pct": None, "cpu_max_c": None,
                 "mem_available_mib": 1000.0, "swap_used_mib": 0.0}]

    def test_agent_report(self):
        events = {"observed_models": [], "first_model_delta_s": None, "first_text_delta_s": 3.3456,
                  "tool_event_intervals_union_s": None, "remaining_unattributed_s": None,
                  "tool_calls": [], "retries": 0, "protocol_event_count": 0}
        data = {"mode": "agent", "status": "COMPLETE", "metadata": self.meta(), "notes": [],
                "result": {"local_replay": [{"passed": True, "total_s": 1.2591}, {"passed": True, "total_s": 1.3}],
                           "live_requested": True,
                           "live": [{"success": False, "acceptance": {"passed": False},
                                     "invocation": {"status": "TIMEOUT", "wall_s": 600.0, "events": events}},
                                    {"success": False, "acceptance": {}, "invocation": {"status": "ERROR"}}]}}
        for code in i18n.LANGUAGES:
            i18n.set_language(code)
            text = self.render(data, self.rows())
            self.assertNotIn("None", text, code)
            self.assertIn(i18n.t("common.na"), text, code)
            self.assertIn("1.259", text, code)

    def test_daily_report_without_samples(self):
        phases = {"browser-idle": {"measurement_status": "INSUFFICIENT_SAMPLES",
                                   "raf_interval_ms": {"p95_ms": None}, "timer_lateness_ms": {"p95_ms": None}}}
        result = {"phases": [{"phase": "programming-alone", "median_task_s": 1.26, "passed_cycles": 30, "cycles": 30},
                             {"phase": "tabs-programming", "median_task_s": None, "passed_cycles": 0, "cycles": 2}],
                  "browser_metrics": {"phases": phases}, "observe_real_update": False}
        data = {"mode": "daily", "status": "INCOMPLETE", "metadata": self.meta(), "notes": ["x"], "result": result}
        for code in i18n.LANGUAGES:
            i18n.set_language(code)
            text = self.render(data, self.rows())
            self.assertNotIn("None", text, code)
            self.assertNotIn("Nonems", text, code)
            self.assertIn("1.00x", text, code)


class BrowserPageTest(unittest.TestCase):
    def tearDown(self):
        i18n.set_language("en")

    def test_page_header_is_localized_and_body_is_not(self):
        import bench_daily
        bodies = set()
        for code in i18n.LANGUAGES:
            i18n.set_language(code)
            session = bench_daily.BrowserSession(Path(tempfile.gettempdir()), Path(tempfile.gettempdir()), tabs=2)
            page = session._html(0).replace(session.token, "TOKEN")
            self.assertIn(f'<html lang="{code}">', page)
            self.assertIn(i18n.t("page.keep_visible"), page)
            self.assertIn(json.dumps(i18n.t("page.sampling")), page)
            bodies.add(page.split("<main>", 1)[1].split("</main>", 1)[0])
        self.assertEqual(len(bodies), 1)


if __name__ == "__main__":
    unittest.main()
