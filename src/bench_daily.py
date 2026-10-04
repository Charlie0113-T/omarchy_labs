"""Local, headed-browser observations and a bounded update-like I/O fixture.

Uses Python's standard library. Does not use an existing browser profile, CDP,
external pages, a package manager, headless mode, or disabled browser sandboxing.
Browser timing is a page scheduling proxy, not physical input-to-screen latency.
"""
from __future__ import annotations

import gzip
import hashlib
import hmac
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import math
import os
from pathlib import Path
import random
import secrets
import shutil
import signal
import subprocess
import tarfile
import tempfile
import threading
import time
from urllib.parse import urlsplit

import i18n
from i18n import t


FIXTURE_VERSION = "daily-local-v1"
MAX_SAMPLES_PER_PHASE = 200_000


def _summary(values):
    values = sorted(values)
    if not values:
        return {"n": 0, "p50_ms": None, "p95_ms": None, "p99_ms": None, "max_ms": None}
    def pct(p):
        return round(values[max(0, math.ceil(len(values) * p) - 1)], 3)
    return {"n": len(values), "p50_ms": pct(.5), "p95_ms": pct(.95),
            "p99_ms": pct(.99), "max_ms": round(values[-1], 3),
            "over_50ms": sum(x > 50 for x in values),
            "over_100ms": sum(x > 100 for x in values)}


class BrowserSession:
    """Start once, label parent workload phases, obtain telemetry, then close.

    start() raises RuntimeError when no visible display/browser is available.
    set_phase() can run from the workload thread. metrics() is a snapshot.
    close() is idempotent and terminates only this session's own process group.
    """
    def __init__(self, work: Path, out: Path, tabs=8):
        self.work, self.out = Path(work), Path(out)
        self.tabs = int(tabs)
        if not 1 <= self.tabs <= 20:
            raise ValueError("Browser fixture requires 1..20 tabs")
        self.token = secrets.token_urlsafe(24)
        self.lock = threading.RLock()
        self.phase, self.phase_id = "browser-startup", 0
        self.phases = {}
        self.pages = {}
        self._last_sequences = {}
        self.missing_report_batches = 0
        self._phase_ids = {0: self.phase}
        self._ensure_phase(self.phase)
        self.server = self.server_thread = self.proc = self.profile = self.log = None
        self.started = None
        self.closed = False
        # Only the page header follows the chosen language; the page body is identical in all languages.
        self.metadata = {"fixture": FIXTURE_VERSION, "tabs": self.tabs, "ui_language": i18n.current(),
                         "headless": False, "background_throttling": "browser default",
                         "timing_kind": "foreground page rAF intervals and 100ms timer lateness; not desktop FPS/INP"}

    def _ensure_phase(self, name):
        return self.phases.setdefault(name, {"raf": [], "timer": [], "batches": 0,
                "visible_ms": 0., "hidden_ms": 0., "visibility_changes": 0,
                "hidden_raf_callbacks": 0, "hidden_timer_callbacks": 0,
                "transition_discarded_samples": 0, "buffer_dropped_samples": 0,
                "server_dropped_samples": 0})

    def set_phase(self, name):
        if not isinstance(name, str) or not name or len(name) > 100:
            raise ValueError("Phase must be a nonempty string of at most 100 characters")
        with self.lock:
            self.phase, self.phase_id = name, self.phase_id + 1
            self._phase_ids[self.phase_id] = name
            self._ensure_phase(name)

    def _phase_reply(self):
        with self.lock:
            return {"phase": self.phase, "phase_id": self.phase_id}

    def _receive(self, doc):
        """Validate bounded telemetry; never accepts files, URLs or commands."""
        if not isinstance(doc, dict):
            raise ValueError("Expected object")
        page, seq, epoch = doc.get("page"), doc.get("seq"), doc.get("phase_id")
        if type(page) is not int or not 0 <= page < self.tabs or type(seq) is not int or seq < 0:
            raise ValueError("Invalid page or sequence")
        if type(epoch) is not int:
            raise ValueError("Invalid phase id")
        arrays = {}
        for key in ("raf", "timer"):
            value = doc.get(key, [])
            if not isinstance(value, list) or len(value) > 4096:
                raise ValueError("Invalid sample buffer")
            if any(type(x) not in (int, float) or not math.isfinite(x) or not 0 <= x <= 3_600_000 for x in value):
                raise ValueError("Invalid sample")
            arrays[key] = value
        scalar_keys = ("visible_ms", "hidden_ms", "visibility_changes", "hidden_raf_callbacks",
                       "hidden_timer_callbacks", "buffer_dropped_samples")
        scalars = {}
        for key in scalar_keys:
            value = doc.get(key, 0)
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 3_600_000:
                raise ValueError("Invalid telemetry counter")
            scalars[key] = value
        with self.lock:
            if seq <= self._last_sequences.get(page, -1):
                return self._phase_reply()
            self.missing_report_batches += max(0, seq - self._last_sequences.get(page, -1) - 1)
            self._last_sequences[page] = seq
            self.pages[page] = {"last_seen_monotonic": time.monotonic(),
                    "visibility": str(doc.get("visibility", "unknown"))[:20],
                    "viewport": doc.get("viewport") if isinstance(doc.get("viewport"), dict) else {},
                    "user_agent": str(doc.get("user_agent", ""))[:300], "last_phase_id": epoch}
            name = self._phase_ids.get(epoch)
            if name is None:
                return self._phase_reply()
            row = self._ensure_phase(name)
            # A batch straddling the parent's phase boundary cannot be assigned
            # precisely. Discard it rather than contaminating either scenario.
            if epoch != self.phase_id:
                row["transition_discarded_samples"] += sum(map(len, arrays.values()))
            else:
                row["batches"] += 1
                for key, values in arrays.items():
                    room = max(0, MAX_SAMPLES_PER_PHASE - len(row[key]))
                    row[key].extend(values[:room])
                    row["server_dropped_samples"] += max(0, len(values) - room)
                for key, value in scalars.items():
                    row[key] += value
            return self._phase_reply()

    def _handler_class(self):
        owner = self
        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            def log_message(self, *args):
                pass
            def _send(self, status, payload, content_type="application/json; charset=utf-8"):
                if not isinstance(payload, bytes):
                    payload = json.dumps(payload, ensure_ascii=False).encode()
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src data:")
                self.send_header("Connection", "close")
                self.end_headers()
                self.close_connection = True
                try:
                    self.wfile.write(payload)
                except (BrokenPipeError, ConnectionResetError):
                    pass
            def _path(self):
                parts = urlsplit(self.path).path.split("/")
                if len(parts) < 3 or not hmac.compare_digest(parts[1], owner.token):
                    return None
                return parts[2:]
            def do_GET(self):
                route = self._path()
                if route == ["phase"]:
                    self._send(200, owner._phase_reply())
                elif route and len(route) == 2 and route[0] == "page" and route[1].isdigit() and 0 <= int(route[1]) < owner.tabs:
                    self._send(200, owner._html(int(route[1])).encode(), "text/html; charset=utf-8")
                else:
                    self._send(404, {"error": "not found"})
            def do_POST(self):
                if self._path() != ["report"]:
                    self._send(404, {"error": "not found"})
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 131072:
                        raise ValueError("Invalid body length")
                    if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                        raise ValueError("Expected application/json")
                    self.connection.settimeout(3)
                    result = owner._receive(json.loads(self.rfile.read(length)))
                    self._send(200, result)
                except (ValueError, OSError, TypeError):
                    self._send(400, {"error": "invalid telemetry"})
        return Handler

    def _html(self, page):
        title = t(f"page.title.{page % 8}")
        paragraphs = "".join(f"<section><h3>{i:02d}. Component {i * 17 + page}</h3><p>Fixed local documentation for repeatable browser workload. Read files, validate input, build the project and inspect results. No external resources are loaded.</p><pre>const item_{i} = {{ index: {i}, valid: true, source: 'local-fixture' }};</pre></section>" for i in range(1, 65))
        rows = "".join(f"<tr><td>module/{i:04d}</td><td>{(i * 31 + page) % 199}</td><td>verified</td><td>{(i * 17) % 53}.0 ms</td></tr>" for i in range(240))
        source = "\n".join(f"export function task_{i}(value) {{ return (value + {i}) * 7; }}" for i in range(250))
        if page % 3 == 0:
            body = paragraphs
        elif page % 3 == 1:
            body = "<table><thead><tr><th>File</th><th>Cases</th><th>Status</th><th>Time</th></tr></thead><tbody>" + rows + "</tbody></table>"
        else:
            body = "<textarea spellcheck='false' aria-label='Fixed sample source code'>" + source + "</textarea>" + paragraphs[:12000]
        script = r"""
const page = PAGE_NUMBER, base = BASE_URL;
let phase = 'browser-startup', epoch = 0, seq = 0, sending = false;
let samples = fresh(), rafPrevious = null, timerPrevious = null;
let visibilityStart = performance.now(), wasVisible = document.visibilityState === 'visible';
function fresh() { return {raf:[],timer:[],visible_ms:0,hidden_ms:0,visibility_changes:0,hidden_raf_callbacks:0,hidden_timer_callbacks:0,buffer_dropped_samples:0}; }
function add(name, value) { if(samples[name].length < 4096) samples[name].push(value); else samples.buffer_dropped_samples++; }
function accountVisibility() { const now=performance.now(); samples[wasVisible?'visible_ms':'hidden_ms'] += now-visibilityStart; visibilityStart=now; }
document.addEventListener('visibilitychange',()=>{accountVisibility();wasVisible=document.visibilityState==='visible';samples.visibility_changes++;rafPrevious=null;timerPrevious=null;});
function frame(t) {
  if(document.visibilityState==='visible') {
    if(rafPrevious!==null) add('raf', Math.max(0,t-rafPrevious));
    rafPrevious=t;
    document.getElementById('cursor').style.transform=`translateX(${80 + 75*Math.sin(t/1700)}px)`;
  } else {samples.hidden_raf_callbacks++;rafPrevious=null;}
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
setInterval(()=>{
  const t=performance.now();
  if(document.visibilityState==='visible') {if(timerPrevious!==null)add('timer',Math.max(0,t-timerPrevious-100));timerPrevious=t;}
  else {samples.hidden_timer_callbacks++;timerPrevious=null;}
},100);
async function send() {
  if(sending)return; sending=true;
  accountVisibility();
  const batch=samples;samples=fresh();
  const payload={...batch,page,seq:seq++,phase_id:epoch,visibility:document.visibilityState,user_agent:navigator.userAgent,viewport:{width:innerWidth,height:innerHeight,dpr:devicePixelRatio}};
  try {
    const response=await fetch(base+'/report',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),signal:AbortSignal.timeout(4000)});
    if(!response.ok)throw Error('HTTP '+response.status);
    const state=await response.json();
    if(state.phase_id!==epoch) {phase=state.phase;epoch=state.phase_id;samples=fresh();rafPrevious=null;timerPrevious=null;visibilityStart=performance.now();}
    document.getElementById('phase').textContent=state.phase;
    document.getElementById('connection').textContent=TEXT_SAMPLING;
  } catch(e) { document.getElementById('connection').textContent=TEXT_NO_RESPONSE; }
  finally {sending=false;setTimeout(send,document.visibilityState==='visible'?1000:5000);}
}
send();
""".replace("PAGE_NUMBER", str(page)).replace("BASE_URL", json.dumps("/" + self.token)) \
      .replace("TEXT_SAMPLING", json.dumps(t("page.sampling"))).replace("TEXT_NO_RESPONSE", json.dumps(t("page.no_response")))
        heading = html.escape(t("page.heading", title=title, n=page + 1, total=self.tabs))
        return f"""<!doctype html><html lang="{i18n.current()}"><meta charset="utf-8"><title>Bench {page+1} · {html.escape(title)}</title>
<style>body{{margin:0;background:#f4f6f8;color:#172636;font:15px system-ui,sans-serif}}header{{position:sticky;top:0;padding:18px 28px;background:#162a3d;color:white}}h1{{font-size:22px;margin:0 0 10px}}header p{{margin:5px 0;font-size:13px}}main{{max-width:1000px;margin:auto;padding:28px}}section{{margin:0 0 24px;padding:16px 22px;background:white;border:1px solid #dbe3ea;border-radius:8px}}pre,textarea{{font:13px monospace;background:#edf1f6;padding:12px}}textarea{{box-sizing:border-box;width:100%;height:490px;border:1px solid #bac8d5}}table{{border-collapse:collapse;width:100%;background:white}}td,th{{text-align:left;border-bottom:1px solid #dbe3ea;padding:9px 16px}}.track{{height:4px;margin-top:12px;background:#364e66}}#cursor{{height:4px;width:24px;background:#6edfc3}}small{{color:#c4d6e8}}</style>
<header><h1>{heading}</h1><p>{html.escape(t("page.phase"))} <strong id="phase">{html.escape(t("page.preparing"))}</strong> · <span id="connection">{html.escape(t("page.waiting"))}</span></p><small>{html.escape(t("page.keep_visible"))}</small><div class="track"><div id="cursor"></div></div></header><main>{body}</main><script>{script}</script></html>"""

    def start(self):
        if self.started is not None or self.closed:
            raise RuntimeError("BrowserSession cannot be reused")
        if not (os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY")):
            raise RuntimeError(t("browser.need_display"))
        browser = next((shutil.which(x) for x in ("chromium", "chromium-browser", "google-chrome-stable", "google-chrome") if shutil.which(x)), None)
        if not browser:
            raise RuntimeError(t("browser.not_found"))
        if os.geteuid() == 0:
            raise RuntimeError(t("browser.no_root"))
        self.work.mkdir(parents=True, exist_ok=True)
        self.out.mkdir(parents=True, exist_ok=True)
        self.started = time.monotonic()
        self.profile = tempfile.TemporaryDirectory(prefix="bench-browser-profile-", dir=self.work)
        try:
            self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler_class())
            self.server.daemon_threads = True
            self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.server_thread.start()
            port = self.server.server_address[1]
            urls = [f"http://127.0.0.1:{port}/{self.token}/page/{i}" for i in range(self.tabs)]
            argv = [browser, "--user-data-dir=" + self.profile.name, "--new-window", "--no-first-run",
                    "--no-default-browser-check", "--disable-background-networking", "--disable-sync",
                    "--disable-component-update", "--disable-default-apps", "--metrics-recording-only",
                    "--window-size=1280,800"] + urls
            self.log = (self.out / "daily-browser.stderr.log").open("w")
            self.proc = subprocess.Popen(argv, stdout=self.log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                version = subprocess.run([browser, "--version"], capture_output=True, text=True, timeout=5).stdout.strip()
            except (OSError, subprocess.TimeoutExpired):
                version = "unavailable"
            # Wait for actual in-page telemetry, not just process creation.
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if self.proc.poll() is not None:
                    raise RuntimeError(t("browser.exited"))
                with self.lock:
                    if len(self.pages) == self.tabs and any(p["visibility"] == "visible" for p in self.pages.values()):
                        break
                time.sleep(.1)
            with self.lock:
                loaded = len(self.pages)
                visible = any(p["visibility"] == "visible" for p in self.pages.values())
            if loaded != self.tabs:
                raise RuntimeError(t("browser.partial", loaded=loaded, tabs=self.tabs))
            if not visible:
                raise RuntimeError(t("browser.not_visible"))
            self.metadata.update(browser=browser, browser_version=version, pid=self.proc.pid,
                    startup_to_tab_telemetry_s=round(time.monotonic()-self.started, 3),
                    loaded_tabs=loaded, fixture_sha256=hashlib.sha256(self._html(0).replace(self.token, "TOKEN").encode()).hexdigest())
            return dict(self.metadata)
        except BaseException:
            self.close()
            raise

    def metrics(self):
        with self.lock:
            now = time.monotonic()
            result = {"metadata": dict(self.metadata), "phases": {}, "pages_seen": len(self.pages),
                    "expected_pages": self.tabs, "missing_pages": [p for p in range(self.tabs) if p not in self.pages],
                    "missing_report_batches": self.missing_report_batches,
                    "stale_pages": [p for p, v in self.pages.items() if now-v["last_seen_monotonic"] > 10],
                    "pages": {str(k): {**v, "last_seen_age_s": round(now-v["last_seen_monotonic"], 2)} for k,v in self.pages.items()},
                    "notes": [t(key) for key in ("browser.note_fixture", "browser.note_raf", "browser.note_timer",
                                                 "browser.note_throttling", "browser.note_network", "browser.note_batches")]}
            for name, row in self.phases.items():
                result["phases"][name] = {k: v for k, v in row.items() if k not in ("raf", "timer")}
                result["phases"][name].update(raf_interval_ms=_summary(row["raf"]),
                      timer_lateness_ms=_summary(row["timer"]),
                      measurement_status="OBSERVED" if len(row["raf"]) >= 30 and len(row["timer"]) >= 10 else "INSUFFICIENT_SAMPLES")
            return result

    def close(self):
        if self.closed:
            return
        self.closed = True
        errors = []
        if self.proc:
            # Only the group created by start_new_session; existing browser
            # windows, terminal jobs and package updates are never targeted.
            # A launcher/leader can exit while renderer processes still live.
            # Reaping just the leader is therefore not sufficient cleanup.
            def group_running():
                try:
                    os.killpg(self.proc.pid, 0)
                except ProcessLookupError:
                    return False
                try:
                    for item in Path("/proc").iterdir():
                        if not item.name.isdigit():
                            continue
                        try:
                            fields = (item / "stat").read_text().rsplit(")", 1)[1].split()
                            if int(fields[2]) == self.proc.pid and fields[0] not in {"Z", "X"}:
                                return True
                        except (OSError, ValueError, IndexError):
                            continue
                    return False
                except OSError:
                    return True
            try:
                os.killpg(self.proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            until = time.monotonic() + 3
            while group_running() and time.monotonic() < until:
                self.proc.poll()
                time.sleep(.05)
            if group_running():
                try:
                    os.killpg(self.proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                errors.append(t("browser.not_reaped"))
            until = time.monotonic() + 1
            while group_running() and time.monotonic() < until:
                time.sleep(.05)
            if group_running():
                errors.append(t("browser.group_alive"))
        if self.server:
            try:
                if self.server_thread and self.server_thread.is_alive():
                    self.server.shutdown()
                self.server.server_close()
            except Exception as exc:
                errors.append(str(exc))
        if self.server_thread:
            self.server_thread.join(timeout=2)
        if self.log:
            self.log.close()
        if self.profile:
            try:
                self.profile.cleanup()
            except Exception as exc:
                errors.append(str(exc))
        if errors:
            self.metadata["cleanup_errors"] = errors
            raise RuntimeError("; ".join(errors))


def simulated_update(work: Path, stop_event: threading.Event, checkpoint):
    """Repeat unpack + fsync of 32 MiB fixed pseudo-random local files.

    This is update-LIKE disk/decompression competition, NOT a real update.
    At most ~66 MiB files at a time, no package hooks, root changes or network.
    Caller runs in a worker thread and sets stop_event to finish. checkpoint()
    is called regularly for the caller's temperature/interrupt safeguards.
    Returns counters; exceptions propagate so the parent cannot mark failure
    as successful load. It does not claim to reproduce a package manager.
    """
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(work).free < 128 * 1024**2:
        raise RuntimeError(t("sim.space"))
    started = time.monotonic()
    result = {"kind": "SIMULATED unpack + fsync; NOT system update", "fixture": "unpack32m-v1",
              "cycles_completed": 0, "files_written": 0, "bytes_written": 0,
              "archive_bytes": 0, "setup_s": 0., "duration_s": 0.}
    class Finish(Exception):
        pass
    def check():
        checkpoint()
        if stop_event.is_set():
            raise Finish()
    try:
        with tempfile.TemporaryDirectory(prefix="bench-update-simulation-", dir=work) as tmp:
            root = Path(tmp)
            archive = root / "payload.tar.gz"
            rng = random.Random(20261003)
            # Author our own archive; never unpack a downloaded/user archive.
            with archive.open("wb") as raw:
                with gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=1, mtime=0) as gz:
                    with tarfile.open(fileobj=gz, mode="w|") as tar:
                        for i in range(128):
                            check()
                            payload = rng.randbytes(256 * 1024)
                            member = tarfile.TarInfo(f"package-file-{i:04d}.bin")
                            member.size = len(payload)
                            member.mtime = 0
                            tar.addfile(member, io.BytesIO(payload))
                raw.flush()
                os.fsync(raw.fileno())
            result["archive_bytes"] = archive.stat().st_size
            result["setup_s"] = round(time.monotonic()-started, 3)
            while True:
                check()
                dest = root / "unpacked"
                dest.mkdir()
                with tarfile.open(archive, "r|gz") as tar:
                    for i, member in enumerate(tar):
                        check()
                        if not member.isfile() or member.name != f"package-file-{i:04d}.bin" or member.size != 256 * 1024:
                            raise RuntimeError("Generated archive fixture is inconsistent")
                        source = tar.extractfile(member)
                        if source is None:
                            raise RuntimeError("Generated archive member unreadable")
                        with source, (dest / member.name).open("xb") as target:
                            count = 0
                            while True:
                                check()
                                block = source.read(64 * 1024)
                                if not block:
                                    break
                                target.write(block)
                                count += len(block)
                                result["bytes_written"] += len(block)
                            target.flush()
                            os.fsync(target.fileno())
                        if count != member.size:
                            raise RuntimeError("Short generated archive read")
                        result["files_written"] += 1
                fd = os.open(dest, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
                result["cycles_completed"] += 1
                shutil.rmtree(dest)
    except Finish:
        pass
    result["duration_s"] = round(time.monotonic()-started, 3)
    return result
