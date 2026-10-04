"""A stopped test must finish its cleanup even when more stop signals arrive.

A closing terminal can deliver SIGHUP more than once, Stop can be clicked twice,
and people press Ctrl+C repeatedly. On Python 3.14 a second SIGHUP during cleanup
used to lose the saved report. Run from the repository root:
python3 -m unittest discover -s tests
"""
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"

CHILD = r"""
import sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import bench_base
marker = Path(sys.argv[2])
bench_base.handle_stop_signals()
print("ready", flush=True)
status = "running"
try:
    time.sleep(30)
except KeyboardInterrupt:
    status = "interrupted"
finally:
    marker.write_text(status + ":cleanup-started")
    time.sleep(1.5)  # slow cleanup, like closing the test browser
    print("still printing after the terminal is gone", flush=True)
    marker.write_text(status + ":cleanup-finished")
"""


class StopSignalTest(unittest.TestCase):
    def run_child(self, signals):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "marker"
            with subprocess.Popen([sys.executable, "-c", CHILD, str(SRC), str(marker)],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as child:
                self.assertEqual(child.stdout.readline().strip(), "ready")
                for delay, signum in signals:
                    time.sleep(delay)
                    child.send_signal(signum)
                _, errors = child.communicate(timeout=10)
            return marker.read_text(), errors

    def test_second_hangup_during_cleanup_is_ignored(self):
        result, errors = self.run_child([(0.2, signal.SIGHUP), (0.5, signal.SIGHUP)])
        self.assertEqual(result, "interrupted:cleanup-finished")
        self.assertNotIn("Traceback", errors)

    def test_every_stop_signal_during_cleanup_is_ignored(self):
        result, _ = self.run_child([(0.2, signal.SIGTERM), (0.3, signal.SIGHUP),
                                    (0.2, signal.SIGTERM), (0.2, signal.SIGINT)])
        self.assertEqual(result, "interrupted:cleanup-finished")

    def test_single_ctrl_c_still_stops(self):
        result, _ = self.run_child([(0.2, signal.SIGINT)])
        self.assertEqual(result, "interrupted:cleanup-finished")


if __name__ == "__main__":
    unittest.main()
