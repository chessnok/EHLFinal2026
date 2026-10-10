"""Telemetry for a run: structured event log, HTTP log, metrics, transcripts and a log file.

Every run gets a folder `runs/<run_id>/`:
  events.jsonl     one JSON object per event (session opened, message sent, reply, claim results, deal, ...)
  http.jsonl       one line per HTTP attempt: method, path, status, latency, retry, move id
  run.log          the human-readable log
  sessions/<sid>.json        full transcript of one case: case file, e-mails, decisions, result, trace
  sessions/<sid>/<file>      the documents suppliers attached (quote PDF, cost breakdown, ...)
  metrics.json, summary.json, report.md   written at the end (see report.py)
"""

import json
import logging
import statistics
import threading
import time
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from rich.logging import RichHandler

log = logging.getLogger("negotiator")


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _json_default(value):
    if isinstance(value, bytes):
        return f"<{len(value)} bytes>"
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, set):
        return sorted(value)
    return repr(value)


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=_json_default)


class Metrics:
    """Thread-safe counters and timings."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.counters: Counter[str] = Counter()
        self.timings: defaultdict[str, list[float]] = defaultdict(list)

    def incr(self, name: str, by: int = 1) -> None:
        with self._lock:
            self.counters[name] += by

    def observe(self, name: str, seconds: float) -> None:
        with self._lock:
            self.timings[name].append(seconds)

    @contextmanager
    def timer(self, name: str):
        start = time.perf_counter()
        try:
            yield
        finally:
            self.observe(name, time.perf_counter() - start)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "counters": dict(sorted(self.counters.items())),
                "timings": {name: summarize(values) for name, values in sorted(self.timings.items())},
            }


def summarize(values: list[float]) -> dict:
    if not values:
        return {"n": 0}
    ordered = sorted(values)

    def pct(p: float) -> float:
        return round(ordered[min(len(ordered) - 1, int(p * len(ordered)))], 3)

    return {
        "n": len(values),
        "mean": round(statistics.fmean(values), 3),
        "p50": pct(0.5),
        "p95": pct(0.95),
        "max": round(ordered[-1], 3),
        "total": round(sum(values), 3),
    }


class Recorder:
    """Writes everything a run does to its folder. One recorder per run, shared by all threads."""

    def __init__(self, runs_dir: Path, label: str = "run", console_level: int = logging.INFO) -> None:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.run_id = f"{stamp}-{label}"
        self.dir = Path(runs_dir) / self.run_id
        (self.dir / "sessions").mkdir(parents=True, exist_ok=True)
        self.metrics = Metrics()
        self.started = time.time()
        self._lock = threading.Lock()
        self._events = (self.dir / "events.jsonl").open("a", encoding="utf-8")
        self._http = (self.dir / "http.jsonl").open("a", encoding="utf-8")
        self._configure_logging(console_level)
        self.event("run_started", run_id=self.run_id)

    def _configure_logging(self, console_level: int) -> None:
        root = logging.getLogger("negotiator")
        root.setLevel(logging.DEBUG)
        for handler in list(root.handlers):
            root.removeHandler(handler)
        console = RichHandler(level=console_level, show_path=False, rich_tracebacks=True, markup=False)
        logfile = logging.FileHandler(self.dir / "run.log", encoding="utf-8")
        logfile.setLevel(logging.DEBUG)
        logfile.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(threadName)s %(message)s"))
        root.addHandler(console)
        root.addHandler(logfile)
        root.propagate = False

    def _write(self, handle, record: dict) -> None:
        line = dumps(record)
        with self._lock:
            handle.write(line + "\n")
            handle.flush()

    def event(self, kind: str, /, **fields) -> None:
        self.metrics.incr(f"event.{kind}")
        self._write(self._events, {"ts": utc_now(), "t": round(time.time() - self.started, 3), **fields, "kind": kind})

    def http(self, **fields) -> None:
        self._write(self._http, {"ts": utc_now(), **fields})

    def session_dir(self, session_id: str) -> Path:
        path = self.dir / "sessions" / safe_name(session_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_json(self, relative: str, obj) -> Path:
        path = self.dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
        return path

    def close(self) -> None:
        self.event("run_finished", seconds=round(time.time() - self.started, 3))
        self.save_json("metrics.json", self.metrics.snapshot())
        with self._lock:
            self._events.close()
            self._http.close()


def safe_name(value: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in value)
