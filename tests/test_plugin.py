"""Checks for the Omarchy Quattro plugin: manifest, panel text and plugin/action.sh.

Run from the repository root: python3 -m unittest discover -s tests
The status/stop tests need Linux (/proc) and are skipped elsewhere.
"""
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ACTION = ROOT / "plugin" / "action.sh"
LANGUAGES = ("en", "zh-CN", "zh-TW", "ja")


class ManifestTest(unittest.TestCase):
    """The same rules as `omarchy plugin validate` and the marketplace catalog build."""

    def setUp(self):
        self.manifest = json.loads((ROOT / "manifest.json").read_text())

    def test_required_fields_and_limits(self):
        m = self.manifest
        self.assertIs(m["schemaVersion"], 1)
        for field in ("id", "name", "version", "kinds", "entryPoints"):
            self.assertIn(field, m)
        limits = {"id": 128, "name": 120, "version": 64, "author": 120, "description": 500, "license": 120}
        for field, limit in limits.items():
            self.assertLessEqual(len(m[field]), limit, field)

    def test_id_is_namespaced_and_not_reserved(self):
        plugin_id = self.manifest["id"]
        self.assertRegex(plugin_id, r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
        self.assertNotIn("..", plugin_id)
        self.assertFalse(plugin_id.startswith("omarchy."))
        self.assertEqual(plugin_id, plugin_id.lower())

    def test_widget_module_name_matches_id(self):
        qml = (ROOT / "plugin" / "BarWidget.qml").read_text()
        self.assertIn(f'moduleName: "{self.manifest["id"]}"', qml)

    def test_entry_points_exist_for_every_kind(self):
        needed = {"bar": "bar", "bar-widget": "barWidget", "menu": "menu", "overlay": "overlay",
                  "panel": "panel", "service": "service"}
        for kind in self.manifest["kinds"]:
            self.assertIn(needed[kind], self.manifest["entryPoints"], kind)
        for path in self.manifest["entryPoints"].values():
            self.assertFalse(path.startswith("/") or ".." in path, path)
            self.assertTrue((ROOT / path).is_file(), path)
        self.assertIn(self.manifest["barWidget"].get("defaultSection", "center"), ("left", "center", "right"))

    def test_no_symlinks(self):
        links = [p for p in ROOT.rglob("*") if p.is_symlink() and ".git" not in p.parts]
        self.assertEqual(links, [])

    def test_versions_agree(self):
        sys.path.insert(0, str(ROOT / "src"))
        from version import LAB_VERSION
        self.assertTrue(self.manifest["version"].startswith(LAB_VERSION + "."), (self.manifest["version"], LAB_VERSION))


class PanelTextTest(unittest.TestCase):
    def test_every_entry_has_four_languages(self):
        text = (ROOT / "plugin" / "Strings.js").read_text()
        entries = re.findall(r'^\s*"([A-Za-z]+)":\s*\[(.*)\],?\s*$', text, re.M)
        self.assertGreater(len(entries), 10)
        for key, values in entries:
            items = json.loads("[" + values + "]")
            self.assertEqual(len(items), len(LANGUAGES), key)
            self.assertTrue(all(isinstance(v, str) and v.strip() for v in items), key)

    def test_every_key_used_in_qml_exists(self):
        strings = (ROOT / "plugin" / "Strings.js").read_text()
        qml = (ROOT / "plugin" / "BarWidget.qml").read_text()
        for key in re.findall(r'tr\("([A-Za-z]+)"\)', qml):
            self.assertIn(f'"{key}":', strings, key)


class ActionTest(unittest.TestCase):
    """Runs plugin/action.sh with stand-ins for the desktop commands it calls."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.bin = Path(self.tmp.name) / "bin"
        self.log = Path(self.tmp.name) / "calls.log"
        self.home.mkdir()
        self.bin.mkdir()
        for name in ("omarchy-launch-floating-terminal-with-presentation", "omarchy-launch-editor",
                     "notify-send", "xdg-open"):
            self.stub(name, f'printf "%s\\0" {name} "$@" >> "{self.log}"; printf "\\n" >> "{self.log}"')
        self.clipboard = Path(self.tmp.name) / "clipboard"
        self.stub("wl-copy", f'cat > "{self.clipboard}"; printf "wl-copy\\0\\n" >> "{self.log}"')

    def tearDown(self):
        self.tmp.cleanup()

    def stub(self, name, body):
        path = self.bin / name
        path.write_text("#!/bin/bash\n" + body + "\n")
        path.chmod(0o755)

    def action(self, *args):
        env = dict(os.environ, HOME=str(self.home), PATH=f"{self.bin}:{os.environ['PATH']}")
        return subprocess.run(["bash", str(ACTION), *args], env=env, capture_output=True, text=True, timeout=20)

    def calls(self):
        if not self.log.exists():
            return []
        return [line.split("\0")[:-1] if line.endswith("\0") else line.split("\0")
                for line in self.log.read_text().splitlines() if line]

    def test_tests_open_in_a_terminal_from_source(self):
        for mode in ("typical", "daily", "agent"):
            self.log.unlink(missing_ok=True)
            self.assertEqual(self.action(mode).returncode, 0)
            (call,) = self.calls()
            self.assertEqual(call[0], "omarchy-launch-floating-terminal-with-presentation")
            command = shlex.split(call[1])
            self.assertEqual(command, ["PYTHONDONTWRITEBYTECODE=1", "python3", "-B", str(ROOT / "src"), mode])

    def test_live_agent_asks_first_in_the_panel_language(self):
        self.assertEqual(self.action("agent-live", "ja").returncode, 0)
        (call,) = self.calls()
        self.assertIn("利用枠を消費します", call[1])
        self.assertIn("read -r _ && PYTHONDONTWRITEBYTECODE=1 python3 -B", call[1])
        self.assertTrue(call[1].endswith("agent --live"))

    def test_results_actions_without_results_only_notify(self):
        for action in ("open-report", "open-folder", "share"):
            self.log.unlink(missing_ok=True)
            self.assertEqual(self.action(action, "zh-CN").returncode, 0, action)
            (call,) = self.calls()
            self.assertEqual(call[0], "notify-send", action)

    def make_run(self, name, issue=True):
        run = self.home / "omarchy-lab" / name
        run.mkdir(parents=True)
        (run / "report.txt").write_text("report " + name)
        if issue:
            (run / "issue.md").write_text("### Summary\n" + name)
            (run / "issue-url.txt").write_text("https://github.com/Charlie0113-T/omarchy_labs/issues/new?title=x\n")
        return run

    def test_latest_report_is_newest_by_timestamp(self):
        self.make_run("20261004-101500-aaaa")
        newest = self.make_run("20261005-090000-bbbb")
        (self.home / "omarchy-lab" / ".run.lock").write_text("")
        self.action("open-report")
        self.assertEqual(self.calls(), [["omarchy-launch-editor", str(newest / "report.txt")]])

    def test_share_copies_issue_and_opens_link(self):
        self.make_run("20261005-090000-bbbb")
        self.assertEqual(self.action("share", "en").returncode, 0)
        calls = self.calls()
        self.assertEqual(calls[0], ["wl-copy"])
        self.assertEqual(self.clipboard.read_text(), "### Summary\n20261005-090000-bbbb")
        self.assertEqual(calls[1][0], "notify-send")
        self.assertIn("review it", calls[1][-1])
        self.assertEqual(calls[2], ["xdg-open", "https://github.com/Charlie0113-T/omarchy_labs/issues/new?title=x"])

    def test_share_without_issue_file_does_nothing_else(self):
        self.make_run("20261005-090000-bbbb", issue=False)
        self.action("share")
        self.assertEqual([c[0] for c in self.calls()], ["notify-send"])

    def test_unknown_action_is_refused(self):
        result = self.action("rm-rf")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.calls(), [])

    @unittest.skipUnless(sys.platform.startswith("linux"), "needs /proc")
    def test_status_and_stop_match_only_the_test_process(self):
        source = ROOT / "src"
        decoy = subprocess.Popen(["sleep", "60"])  # an unrelated process must survive
        fake = subprocess.Popen([sys.executable, "-B", "-c", "import time; time.sleep(60)", str(source), "typical"])
        try:
            self.assertEqual(self.action("status").stdout.strip(), "running")
            self.assertEqual(self.action("stop").returncode, 0)
            fake.wait(timeout=5)
            self.assertEqual(self.action("status").stdout.strip(), "idle")
            self.assertIsNone(decoy.poll())
        finally:
            for p in (fake, decoy):
                if p.poll() is None:
                    p.kill()
                p.wait()


if __name__ == "__main__":
    unittest.main()
