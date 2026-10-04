#!/usr/bin/env python3
"""Omarchy Bench 1.0 — repeatable Linux tests, ordinary temporary files only.

Run as your NORMAL USER: python3 ~/Downloads/omarchy-bench.py
Dependencies: Python >=3.9, sysbench, fio (Jens Axboe's), findmnt, lsblk.
First-time package install on an up-to-date Omarchy: sudo pacman -S --needed fio sysbench
If package installation fails, use Omarchy's own update workflow; do not use pacman -Sy.
No sudo inside this script, no network, no raw device writes or settings changes.

Methods: https://github.com/akopytov/sysbench
         https://fio.readthedocs.io/en/latest/fio_doc.html
--quick is a reduced smoke test; its results MUST NOT be compared with full runs.
Reports: ~/omarchy-bench/<timestamp>/report.txt, results.json, samples.csv, raw/

Comparison protocol:
  Reboot, wait 3 minutes, close downloads/updates/agents and keep the room,
  display resolution, power profile and software versions the same. Leave the
  desktop running and do not operate the machine while this test runs. Change
  one variable at a time (e.g. HDD vs SSD); retain every run, including failures.
  Separately repeat 3 times: terminal launch, opening the same project, browser
  interaction, and one fixed build. Record first-use vs already-cached launches.
  Check sleep/wake, Bluetooth, sound and external storage manually.
"""
import argparse
import csv
import datetime as dt
import fcntl
import glob
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import re
import shutil
import signal
import statistics
import subprocess
import sys
import tempfile
import threading
import time

import i18n
from i18n import t
import share

VERSION = "1.0"
GIB = 1024 ** 3
ENV = dict(os.environ, LC_ALL="C", LANG="C")
LSBLK = ["lsblk", "--json", "--bytes", "-o", "NAME,PATH,MAJ:MIN,TYPE,SIZE,ROTA,MODEL,TRAN,FSTYPE,MOUNTPOINTS"]


def read(path, default=""):
    try:
        return Path(path).read_text(errors="replace").strip()
    except OSError:
        return default


def query(argv, timeout=8):
    try:
        r = subprocess.run(argv, capture_output=True, text=True, env=ENV, timeout=timeout)
        return {"rc": r.returncode, "stdout": r.stdout.strip(), "stderr": r.stderr.strip()}
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"rc": -1, "stdout": "", "stderr": str(e)}


def json_query(argv):
    r = query(argv)
    try:
        return json.loads(r["stdout"])
    except ValueError:
        return {"unavailable": r}


def meminfo():
    return {k: int(v) * 1024 for k, v in re.findall(r"^(\w+):\s+(\d+) kB", read("/proc/meminfo"), re.M)}


def vmstat():
    return {k: int(v) for k, v in re.findall(r"^(pswpin|pswpout) (\d+)$", read("/proc/vmstat"), re.M)}


def throttles():
    return {p: int(read(p)) for p in glob.glob("/sys/devices/system/cpu/cpu*/thermal_throttle/*_throttle_count") if read(p).isdigit()}


def cpu_sensors():
    found = {}
    for h in glob.glob("/sys/class/hwmon/hwmon*"):
        name = read(Path(h) / "name")
        if name in {"coretemp", "k10temp", "zenpower", "cpu_thermal"}:
            for p in glob.glob(h + "/temp*_input"):
                found[p] = name + ":" + read(p.replace("_input", "_label"), Path(p).stem)
    if not found:
        for h in glob.glob("/sys/class/thermal/thermal_zone*"):
            if read(Path(h) / "type") in {"x86_pkg_temp", "cpu-thermal", "cpu_thermal"}:
                found[str(Path(h) / "temp")] = read(Path(h) / "type")
    return found


def temperatures(sensors):
    result = {}
    for p, label in sensors.items():
        try:
            value = float(read(p)) / 1000
            if 0 < value < 150:
                result[label + "@" + p] = value
        except ValueError:
            pass
    return result


def disks_for_mount(blocks, mount):
    target = mount.get("maj:min")
    # Btrfs reports its own device number, so also match the source path,
    # e.g. "/dev/mapper/root[/@home]" -> /dev/mapper/root (LUKS -> partition -> disk).
    source = re.sub(r"\[.*\]$", "", mount.get("source") or "")
    result = {}
    def walk(node, parents):
        lineage = parents + [node]
        if (target and node.get("maj:min") == target) or (source.startswith("/dev/") and node.get("path") == source):
            for d in lineage:
                if d.get("type") == "disk":
                    result[d.get("name")] = {k: d.get(k) for k in ("name", "model", "size", "rota", "tran")}
        for child in node.get("children", []):
            walk(child, lineage)
    for block in blocks.get("blockdevices", []):
        walk(block, [])
    return list(result.values())


def mount_at(path):
    obj = json_query(["findmnt", "--json", "--target", str(path), "-o", "SOURCE,TARGET,FSTYPE,OPTIONS,MAJ:MIN"])
    return obj.get("filesystems", [{}])[0]


class Stopped(Exception):
    pass


class Monitor:
    def __init__(self, out, limit):
        self.out, self.limit = out, limit
        self.sensors = cpu_sensors()
        self.rows, self.phase, self.reason = [], "setup", None
        self.done = threading.Event()
        self.start = time.monotonic()
        self.thread = threading.Thread(target=self.loop, daemon=True)

    def loop(self):
        previous = None
        try:
            with (self.out / "samples.csv").open("w", newline="") as f:
                keys = ["elapsed_s", "phase", "cpu_busy_pct", "iowait_pct", "cpu_max_c", "mem_available_mib", "swap_used_mib"]
                writer = csv.DictWriter(f, fieldnames=keys)
                writer.writeheader()
                while not self.done.is_set():
                    nums = [int(x) for x in read("/proc/stat").splitlines()[0].split()[1:9]]
                    total, idle, wait = sum(nums), nums[3], nums[4]
                    busy_pct = wait_pct = None
                    if previous and total > previous[0]:
                        delta = total - previous[0]
                        busy_pct = 100 * (delta - idle + previous[1] - wait + previous[2]) / delta
                        wait_pct = 100 * (wait - previous[2]) / delta
                    previous = (total, idle, wait)
                    temps, mem = temperatures(self.sensors), meminfo()
                    maximum = max(temps.values()) if temps else None
                    row = dict(elapsed_s=round(time.monotonic() - self.start, 2), phase=self.phase,
                               cpu_busy_pct=busy_pct, iowait_pct=wait_pct, cpu_max_c=maximum,
                               mem_available_mib=mem.get("MemAvailable", 0) / 1024**2,
                               swap_used_mib=(mem.get("SwapTotal", 0) - mem.get("SwapFree", 0)) / 1024**2)
                    self.rows.append(row)
                    writer.writerow(row)
                    f.flush()
                    if maximum is not None and maximum >= self.limit:
                        self.reason = t("mon.temp_stop", temp=maximum, limit=self.limit)
                    self.done.wait(1)
        except Exception as e:
            self.reason = t("mon.failed", error=e)

    def check(self):
        if self.reason:
            raise Stopped(self.reason)

    def pause(self, seconds, phase):
        self.phase = phase
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            self.check()
            time.sleep(min(0.25, max(0, until - time.monotonic())))


class Suite:
    def __init__(self, args, out, work, meta):
        self.args, self.out, self.work, self.meta = args, out, work, meta
        self.monitor = Monitor(out, args.stop_temp)
        self.records, self.notes, self.failures = [], [], []
        self.status, self.serial = "RUNNING", 0
        self.before_throttle, self.before_swap = throttles(), vmstat()
        self.rounds = 1 if args.quick else 3
        self.size = 32 * 1024**2 if args.quick else 2 * GIB

    @staticmethod
    def stop_process(p):
        if p.poll() is not None:
            return
        try:
            os.killpg(p.pid, signal.SIGTERM)
            p.wait(timeout=2)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    def run(self, phase, argv, timeout):
        self.monitor.check()
        self.monitor.phase = phase
        self.serial += 1
        stem = f"{self.serial:02d}-{phase}"
        (self.out / "raw" / (stem + ".command.json")).write_text(json.dumps(argv, ensure_ascii=False))
        print(f"  → {phase}", flush=True)
        start = time.monotonic()
        with (self.out / "raw" / (stem + ".txt")).open("w+") as stdout, (self.out / "raw" / (stem + ".stderr.txt")).open("w+") as stderr:
            p = subprocess.Popen(argv, cwd=self.work, env=ENV, stdout=stdout, stderr=stderr, start_new_session=True)
            last_progress = start
            try:
                while p.poll() is None:
                    self.monitor.check()
                    now = time.monotonic()
                    if now - start > timeout:
                        raise Stopped(t("base.timeout", phase=phase, timeout=timeout))
                    if now - last_progress >= 20:
                        print("    " + t("base.in_progress", elapsed=now - start), flush=True)
                        last_progress = now
                    time.sleep(0.02)
                self.monitor.check()
            finally:
                self.stop_process(p)
            elapsed = time.monotonic() - start
            stdout.seek(0)
            output = stdout.read()
            stderr.seek(0)
            error = stderr.read()
            if p.returncode:
                raise Stopped(t("base.failed", phase=phase, code=p.returncode, output=(error or output)[-500:]))
        return output, elapsed

    def record(self, key, label, value, unit, lower=False):
        self.records.append(dict(key=key, label=label, value=float(value), unit=unit, lower_is_better=lower))

    def cpu(self, threads, seconds, name, measure=True, interval=0):
        args = ["sysbench", "cpu", f"--threads={threads}", f"--time={seconds}", "--events=0", "--cpu-max-prime=20000"]
        if interval:
            args.append(f"--report-interval={interval}")
        text, _ = self.run(name, args + ["run"], seconds + 45)
        match = re.search(r"events per second:\s*([\d.]+)", text)
        if not match:
            raise Stopped(t("base.sysbench_cpu"))
        if measure:
            key = "cpu_single" if threads == 1 else "cpu_multi"
            self.record(key, t("label.cpu_single") if threads == 1 else t("label.cpu_threads", threads=threads), match[1], "events/s")
        return text

    def fio(self, phase, options, timeout=600):
        # Fixed relative filename inside our private directory. No user-supplied device path.
        base = ["fio", "--output-format=json", f"--name={phase}", "--filename=data.bin",
                "--ioengine=psync", "--iodepth=1", "--numjobs=1", "--direct=1",
                f"--size={self.size}", "--fallocate=none", "--group_reporting=1",
                "--randrepeat=1", "--randseed=20261003", "--eta=never", "--disk_util=0"]
        text, elapsed = self.run(phase, base + options, timeout)
        try:
            doc = json.loads(text[text.index("{"):])
            job = doc["jobs"][0]
            if any(j.get("error", 0) for j in doc["jobs"]):
                raise ValueError("fio job error")
        except (ValueError, KeyError, IndexError) as e:
            raise Stopped(t("base.fio_json", error=e))
        return job, elapsed

    def smallfiles(self, n, count):
        phase = f"smallfiles-{n}"
        self.monitor.phase = phase
        print("  → " + t("base.smallfiles_start", phase=phase, count=count), flush=True)
        folder = self.work / f"small-{n}"
        folder.mkdir()
        payload = random.Random(20261003).randbytes(4096)
        started = time.monotonic()
        try:
            for i in range(count):
                self.monitor.check()
                with (folder / f"f{i:04d}").open("xb") as f:
                    f.write(payload)
                    f.flush()
                    os.fsync(f.fileno())
                if time.monotonic() - started > 180:
                    raise Stopped(t("base.smallfiles_timeout"))
            fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
            self.record("smallfiles", t("label.smallfiles", count=count), time.monotonic() - started, "s", True)
        finally:
            shutil.rmtree(folder)

    def execute(self):
        q = self.args.quick
        cpus = self.meta["logical_cpus_available"]
        self.monitor.thread.start()
        print("\n" + t("bench.step1"), flush=True)
        self.monitor.pause(2 if q else 20, "idle-baseline")
        idle = [r["cpu_busy_pct"] for r in self.monitor.rows if r["phase"] == "idle-baseline" and r["cpu_busy_pct"] is not None]
        if idle and statistics.median(idle) > 10:
            self.notes.append(t("note.baseline_busy"))
        if not self.monitor.sensors:
            self.notes.append(t("note.no_temp"))
        print(t("bench.step2"), flush=True)
        self.cpu(cpus, 1 if q else 5, "cpu-warmup", False)
        for n in range(1, self.rounds + 1):
            self.cpu(1, 2 if q else 15, f"cpu-single-{n}")
            if cpus > 1:
                self.cpu(cpus, 2 if q else 15, f"cpu-multi-{n}")
        print(t("bench.step3"), flush=True)
        for n in range(1, self.rounds + 1):
            text, _ = self.run(f"memory-{n}", ["sysbench", "memory", "--threads=1", "--memory-block-size=128M",
                                  "--memory-total-size=1024G", "--memory-oper=read", "--memory-access-mode=seq",
                                  "--memory-scope=global", f"--time={2 if q else 10}", "--events=0", "run"], 60)
            match = re.search(r"\(([\d.]+) MiB/sec\)", text)
            if not match:
                raise Stopped(t("base.mem_parse"))
            self.record("memory", t("label.memory"), match[1], "MiB/s")
        print(t("bench.step4"), flush=True)
        for n in range(1, self.rounds + 1):
            # Wall time includes fio setup and end_fsync; more conservative than cached writes.
            (self.work / "data.bin").unlink(missing_ok=True)
            j, elapsed = self.fio(f"seq-write-{n}", ["--rw=write", "--bs=1M", "--refill_buffers=1", "--end_fsync=1"])
            io_bytes = j["write"].get("io_bytes", j["write"].get("io_kbytes", 0) * 1024)
            if io_bytes != self.size:
                raise Stopped(t("base.seq_write_len"))
            self.record("seq_write", t("label.seq_write"), io_bytes / elapsed / 1024**2, "MiB/s")
            j, _ = self.fio(f"seq-read-{n}", ["--rw=read", "--bs=1M", "--readonly", "--allow_file_create=0"])
            b = j["read"].get("bw_bytes", j["read"].get("bw", 0) * 1024)
            self.record("seq_read", t("label.seq_read"), b / 1024**2, "MiB/s")
            j, _ = self.fio(f"random-read-{n}", ["--rw=randread", "--bs=4k", "--readonly", "--allow_file_create=0",
                         "--time_based=1", f"--runtime={2 if q else 20}", f"--ramp_time={0 if q else 3}", "--percentile_list=95:99"], 90)
            self.record("rand_iops", t("label.rand_iops"), j["read"]["iops"], "IOPS")
            lat = j["read"].get("clat_ns", {})
            for percentile, suffix in [(95, "p95"), (99, "p99")]:
                value = next((v for k, v in lat.get("percentile", {}).items() if float(k) == percentile), None)
                if value is None:
                    raise Stopped(t("base.fio_percentile"))
                self.record("rand_" + suffix, t("label.rand_lat", suffix=suffix), value / 1e6, "ms", True)
        # Separate bounded integrity check; excluded from speed results.
        self.fio("crc32c-check", ["--rw=write", "--bs=64k", f"--size={16 * 1024**2 if q else 64 * 1024**2}",
                                 "--verify=crc32c", "--do_verify=1", "--verify_fatal=1", "--end_fsync=1"], 180)
        self.meta["temporary_file_crc32c"] = "PASS (limited sample, not full-drive health)"
        print(t("bench.step5"), flush=True)
        for n in range(1, self.rounds + 1):
            self.smallfiles(n, 8 if q else 300)
        print(t("bench.step6"), flush=True)
        self.monitor.pause(2 if q else 20, "pre-sustained-rest")
        output = self.cpu(cpus, 4 if q else 120, "cpu-sustained", False, 1 if q else 10)
        rates = [float(x) for x in re.findall(r"\beps:\s*([\d.]+)", output)]
        self.meta["sustained_eps_intervals"] = rates
        if len(rates) >= 6:
            # Exclude the first 10-second interval (initial warmup).
            first, last = statistics.mean(rates[1:4]), statistics.mean(rates[-3:])
            ratio = 100 * last / first if first else None
            self.meta["sustained_last_vs_early_pct"] = ratio
            if ratio is not None and ratio < 90:
                self.notes.append(t("note.sustained_drop"))
        self.monitor.pause(2 if q else 20, "recovery")
        self.status = "COMPLETE"

    def finalize(self):
        self.monitor.done.set()
        if self.monitor.thread.is_alive():
            self.monitor.thread.join(timeout=3)
        after = throttles()
        self.meta["thermal_throttle_counter_deltas"] = {p: after[p] - old for p, old in self.before_throttle.items() if p in after}
        sw = vmstat()
        self.meta["swap_page_deltas"] = {k: sw[k] - v for k, v in self.before_swap.items() if k in sw}
        if any(v > 0 for v in self.meta["thermal_throttle_counter_deltas"].values()):
            self.notes.append(t("note.throttle"))
        if any(v > 0 for v in self.meta["swap_page_deltas"].values()):
            self.notes.append(t("note.swap"))
        journal = query(["journalctl", "-k", "--since", "@" + str(int(self.meta["start_epoch"])), "--no-pager", "-p", "warning"], 10)
        (self.out / "raw" / "kernel-warnings.txt").write_text(journal["stdout"] + "\n" + journal["stderr"])
        self.meta["kernel_log_access_rc"] = journal["rc"]
        # A normal user may have no access even when journalctl exits zero. Never infer 'no errors'.
        if journal["rc"] or "permission" in journal["stderr"].lower() or "not seeing messages" in journal["stderr"].lower():
            self.notes.append(t("note.kernel_log"))
        summary = []
        for key in dict.fromkeys(r["key"] for r in self.records):
            rows = [r for r in self.records if r["key"] == key]
            values = [r["value"] for r in rows]
            med = statistics.median(values)
            spread = 100 * (max(values) - min(values)) / med if med else 0
            summary.append(dict(rows[0], value=med, samples=values, n=len(values), spread_pct=spread))
            if len(values) >= 3 and spread > 15:
                self.notes.append(t("note.spread", label=rows[0]["label"], spread=spread))
        temps = [r["cpu_max_c"] for r in self.monitor.rows if r["cpu_max_c"] is not None]
        self.meta["cpu_observed_peak_c"] = max(temps) if temps else None
        phase_temps = {}
        for phase in dict.fromkeys(r["phase"] for r in self.monitor.rows):
            vs = [r["cpu_max_c"] for r in self.monitor.rows if r["phase"] == phase and r["cpu_max_c"] is not None]
            if vs:
                phase_temps[phase] = {"median_c": statistics.median(vs), "max_c": max(vs)}
        self.meta["temperature_by_phase"] = phase_temps
        self.meta["sensor_paths"] = self.monitor.sensors
        self.meta["duration_s"] = round(time.time() - self.meta["start_epoch"], 1)
        results = dict(version=VERSION, profile="QUICK-NOT-COMPARABLE" if self.args.quick else "FULL-3-ROUNDS",
                       status=self.status, metadata=self.meta, summary=summary, records=self.records, notes=self.notes,
                       failures=self.failures)
        (self.out / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
        report = self.report_text(summary, phase_temps)
        (self.out / "report.txt").write_text(report)
        if i18n.current() != "en":
            with i18n.using("en"):
                (self.out / "report.en.txt").write_text(self.report_text(summary, phase_temps))
        print("\n" + report, flush=True)
        share.offer(self.out, "typical", results, self.monitor.rows)

    def report_text(self, summary, phase_temps):
        lines = [f"Omarchy Bench {VERSION} | " + t("bench.profile_quick" if self.args.quick else "bench.profile_full"),
                 t("bench.status", status=self.status, minutes=self.meta["duration_s"] / 60),
                 t("bench.cpu", cpu=self.meta["cpu_model"], threads=self.meta["logical_cpus_available"]),
                 t("bench.memory", gib=self.meta["memory_total_bytes"] / GIB),
                 t("bench.mount", source=self.meta["test_mount"].get("source", "?"), fstype=self.meta["test_mount"].get("fstype", "?"))]
        for disk in self.meta["test_disks"]:
            medium = t("bench.medium_rotational" if disk["rota"] in (True, 1, "1") else "bench.medium_solid")
            lines.append(t("bench.disk", name=disk["name"], model=disk["model"], medium=medium))
        if not self.meta["test_disks"]:
            lines.append(t("bench.disk_unknown"))
        lines += [t("bench.method", mib=self.size / 1024**2), "", t("bench.table_header")]
        for r in summary:
            arrow = "↓" if r["lower_is_better"] else "↑"
            lines.append(f"{i18n.localize(r['label'])} {arrow} | {r['value']:.2f} {r['unit']} | " + ", ".join(f"{v:.2f}" for v in r["samples"]) + f" | {r['spread_pct']:.1f}% (n={r['n']})")
        peak = self.meta["cpu_observed_peak_c"]
        lines += ["", t("report.cpu_peak", peak=peak) if peak is not None else t("bench.no_temp")]
        for phase in ("idle-baseline", "cpu-sustained", "recovery"):
            p = phase_temps.get(phase)
            if p:
                lines.append("  " + t("bench.phase_temp", phase=phase, median=p["median_c"], max=p["max_c"]))
        ratio = self.meta.get("sustained_last_vs_early_pct")
        if ratio is not None:
            lines.append(t("bench.sustained", ratio=ratio))
        crc = t("bench.crc_pass") if "temporary_file_crc32c" in self.meta else t("bench.not_done")
        lines.append(t("bench.crc", value=crc))
        lines.append(t("bench.swap", deltas=self.meta["swap_page_deltas"]))
        lines += ["", t("bench.tips_header")] + ["- " + i18n.localize(x) for x in self.notes + self.failures]
        lines += ["- " + t(key) for key in ("bench.tip_percentile", "bench.tip_direct_io", "bench.tip_window",
                                           "bench.tip_memory", "bench.tip_sustained", "bench.tip_no_score",
                                           "bench.tip_not_verified", "bench.tip_same_conditions", "bench.tip_fusion")]
        lines += ["", t("bench.boot_header"), self.meta["boot_timing"]["stdout"] or t("bench.not_obtained"), "",
                  t("bench.out", path=self.out)]
        return "\n".join(lines) + "\n"


def main():
    # Already chosen when launched through omarchy-lab.pyz; asks only when run on its own.
    i18n.setup(sys.argv[1:])
    ap = argparse.ArgumentParser(description=t("help.bench_description", version=VERSION), formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quick", action="store_true", help=t("help.bench_quick"))
    ap.add_argument("--work-dir", type=Path, default=Path.home(), help=t("help.work_dir"))
    ap.add_argument("--output-dir", type=Path, default=Path.home() / "omarchy-bench", help=t("help.output_dir", path="~/omarchy-bench"))
    ap.add_argument("--stop-temp", type=int, default=90, choices=range(60, 96), metavar="60..95", help=t("help.stop_temp"))
    i18n.add_argument(ap)
    args = ap.parse_args()
    if sys.platform != "linux":
        ap.error(t("err.linux_only"))
    if os.geteuid() == 0:
        ap.error(t("err.no_root"))
    if sys.version_info < (3, 9):
        ap.error(t("err.python"))
    missing = [x for x in ("sysbench", "fio", "findmnt", "lsblk") if not shutil.which(x)]
    if missing:
        ap.error(t("err.missing", tools=", ".join(missing)))
    fio_version, sb_version = query(["fio", "--version"]), query(["sysbench", "--version"])
    if not fio_version["stdout"].startswith("fio-") or sb_version["rc"]:
        ap.error(t("err.fio_wrong"))
    target = args.work_dir.expanduser().resolve(strict=True)
    if not target.is_dir() or any(target == Path(p) or Path(p) in target.parents for p in ("/dev", "/proc", "/sys")):
        ap.error(t("err.work_dir"))
    mount, rootmount = mount_at(target), mount_at("/")
    if not mount:
        ap.error(t("err.mount_unknown"))
    invalid_fs = mount.get("fstype", "") in {"tmpfs", "ramfs", "overlay", "squashfs", "nfs", "nfs4", "cifs", "fuse.sshfs"}
    if invalid_fs and not args.quick:
        ap.error(t("err.fs_invalid", mount=mount))
    size = 32 * 1024**2 if args.quick else 2 * GIB
    if shutil.disk_usage(target).free < (512 * 1024**2 if args.quick else 8 * GIB):
        ap.error(t("err.space_bench"))
    base = args.output_dir.expanduser().resolve()
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock = (base / ".run.lock").open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        ap.error(t("err.bench_locked"))
    out = Path(tempfile.mkdtemp(prefix=dt.datetime.now().strftime("%Y%m%d-%H%M%S-"), dir=base))
    (out / "raw").mkdir()
    blocks = json_query(LSBLK)
    text = read("/proc/cpuinfo")
    match = re.search(r"^model name\s*:\s*(.+)", text, re.M)
    meta = dict(start_epoch=time.time(), started_local=dt.datetime.now().astimezone().isoformat(),
                script_sha256=hashlib.sha256(__loader__.get_data(__file__) if hasattr(__loader__, 'get_data') else Path(__file__).read_bytes()).hexdigest(),
                cpu_model=match[1] if match else platform.machine(),
                logical_cpus_available=len(os.sched_getaffinity(0)), logical_cpus_system=os.cpu_count(),
                memory_total_bytes=meminfo().get("MemTotal", 0), kernel=platform.release(),
                machine_model=read("/sys/class/dmi/id/product_name"), os_release=read("/etc/os-release"),
                test_directory=str(target), test_mount=mount, root_mount=rootmount, lsblk=blocks,
                test_disks=disks_for_mount(blocks, mount), sysbench=sb_version["stdout"], fio=fio_version["stdout"],
                package_versions=query(["pacman", "-Q", "omarchy", "hyprland", "linux", "fio", "sysbench"]),
                omarchy_version=query(["omarchy-version"]),
                cpu_governors={p: read(p) for p in glob.glob("/sys/devices/system/cpu/cpufreq/policy*/scaling_governor")},
                power_profile=query(["powerprofilesctl", "get"]), boot_timing=query(["systemd-analyze", "time"]),
                display=query(["hyprctl", "monitors", "-j"]), stop_temperature_c=args.stop_temp,
                file_size_bytes=size, repeats=1 if args.quick else 3, language=i18n.current())
    print(f"Omarchy Bench {VERSION} | " + t("bench.start_quick" if args.quick else "bench.start_full"), flush=True)
    print(t("bench.start_info", target=target, source=mount.get("source"), fstype=mount.get("fstype"), out=out), flush=True)
    for d in meta["test_disks"]:
        print(t("bench.physical_disk", name=d["name"], model=d["model"], rota=d["rota"]), flush=True)
    print(t("bench.private_dir"), flush=True)
    with tempfile.TemporaryDirectory(prefix=".omarchy-bench-", dir=target) as tmp:
        suite = Suite(args, out, Path(tmp), meta)
        if invalid_fs:
            suite.notes.append(t("note.virtual_fs"))
        if mount.get("maj:min") != rootmount.get("maj:min"):
            suite.notes.append(t("note.other_mount"))
        def interrupted(signum, frame):
            raise KeyboardInterrupt()
        signal.signal(signal.SIGTERM, interrupted)
        try:
            suite.execute()
        except KeyboardInterrupt:
            suite.status = "INTERRUPTED"
            suite.failures.append(t("bench.interrupted"))
        except Exception as e:
            suite.status = "INCOMPLETE"
            suite.failures.append(i18n.message(e))
        finally:
            suite.finalize()
    lock.close()
    return 0 if suite.status == "COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
