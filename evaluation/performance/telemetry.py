"""Sample server metrics and host resources for the duration of a run.

``TelemetryRecorder`` runs a background thread that, every ``interval`` seconds,
scrapes each service's ``/metrics`` endpoint and reads host CPU / memory (and GPU
utilisation when ``nvidia-smi`` is present). ``summary`` diffs the first
post-warm-up scrape against the last, so the figures line up with the scored
window the client-side aggregate uses.

The Prometheus parser only understands the handful of families the performance
report needs; everything else on the page is ignored.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

try:  # psutil is a load-test dependency, not a service one
    import psutil
except ImportError:  # pragma: no cover - exercised only where psutil is absent
    psutil = None  # type: ignore[assignment]

# Histogram families: mean seconds over the window come from _sum / _count.
_HISTOGRAMS = frozenset(
    {
        "http_server_request_duration_seconds",
        "retrieval_query_duration_seconds",
        "inference_generation_duration_seconds",
    }
)
# Counter families: the window value is the end-minus-start delta.
_COUNTERS = frozenset(
    {
        "http_server_requests_total",
        "retrieval_cache_events_total",
        "inference_tokens_total",
    }
)

_SAMPLE_RE = re.compile(
    r"^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)"
    r"(?:\{(?P<labels>[^}]*)\})?\s+(?P<value>[^\s]+)\s*$"
)
_LABEL_RE = re.compile(r'(\w+)="((?:[^"\\]|\\.)*)"')

Labels = tuple[tuple[str, str], ...]
Key = tuple[str, Labels]


def _parse_labels(raw: str | None) -> Labels:
    if not raw:
        return ()
    return tuple(sorted((key, value) for key, value in _LABEL_RE.findall(raw)))


def parse_metrics_text(text: str) -> tuple[dict[Key, list[float]], dict[Key, float]]:
    """Return ``(histograms, counters)`` for the families the report needs.

    ``histograms`` maps a base family + labels to ``[sum, count]``; ``counters``
    maps a family + labels to the current value.
    """
    histograms: dict[Key, list[float]] = {}
    counters: dict[Key, float] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = _SAMPLE_RE.match(line)
        if match is None:
            continue
        name = match.group("name")
        try:
            value = float(match.group("value"))
        except ValueError:
            continue
        labels = tuple((k, v) for k, v in _parse_labels(match.group("labels")) if k != "le")

        if name.endswith("_sum") and name[:-4] in _HISTOGRAMS:
            histograms.setdefault((name[:-4], labels), [0.0, 0.0])[0] = value
        elif name.endswith("_count") and name[:-6] in _HISTOGRAMS:
            histograms.setdefault((name[:-6], labels), [0.0, 0.0])[1] = value
        elif name in _COUNTERS:
            counters[(name, labels)] = value
    return histograms, counters


def _label_key(labels: Labels) -> str:
    parts = [f"{key}={value}" for key, value in labels if key != "service"]
    return ",".join(parts) or "(all)"


@dataclass
class _Scrape:
    at: float
    histograms: dict[Key, list[float]]
    counters: dict[Key, float]


@dataclass
class TelemetryRecorder:
    endpoints: list[str]
    interval: float = 2.0
    timeout: float = 2.0
    _scrapes: list[_Scrape] = field(default_factory=list, init=False)
    _cpu: list[tuple[float, float]] = field(default_factory=list, init=False)
    _mem_percent: list[tuple[float, float]] = field(default_factory=list, init=False)
    _mem_used_mb: list[tuple[float, float]] = field(default_factory=list, init=False)
    _gpu_util: list[tuple[float, float]] = field(default_factory=list, init=False)
    _gpu_mem_mb: list[tuple[float, float]] = field(default_factory=list, init=False)
    _endpoint_status: dict[str, str] = field(default_factory=dict, init=False)
    _gpu_name: str | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._started_at = 0.0

    def start(self) -> None:
        if psutil is not None:
            psutil.cpu_percent(interval=None)  # prime the delta
        self._started_at = time.monotonic()
        self._thread = threading.Thread(target=self._loop, name="perf-telemetry", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.interval * 2 + 5)

    def _loop(self) -> None:
        while not self._stop.wait(self.interval):
            self._collect()
        self._collect()

    def _collect(self) -> None:
        now = time.monotonic() - self._started_at
        self._collect_metrics(now)
        self._collect_host(now)
        self._collect_gpu(now)

    def _collect_metrics(self, now: float) -> None:
        merged_hist: dict[Key, list[float]] = {}
        merged_counters: dict[Key, float] = {}
        for endpoint in self.endpoints:
            try:
                with urllib.request.urlopen(endpoint, timeout=self.timeout) as response:
                    body = response.read().decode("utf-8")
            except (urllib.error.URLError, OSError, ValueError):
                self._endpoint_status[endpoint] = "unreachable"
                continue
            self._endpoint_status[endpoint] = "ok"
            histograms, counters = parse_metrics_text(body)
            for key, pair in histograms.items():
                merged_hist[key] = pair
            merged_counters.update(counters)
        if merged_hist or merged_counters:
            self._scrapes.append(_Scrape(now, merged_hist, merged_counters))

    def _collect_host(self, now: float) -> None:
        if psutil is None:
            return
        self._cpu.append((now, psutil.cpu_percent(interval=None)))
        memory = psutil.virtual_memory()
        self._mem_percent.append((now, memory.percent))
        self._mem_used_mb.append((now, (memory.total - memory.available) / 1024 / 1024))

    def _collect_gpu(self, now: float) -> None:
        if shutil.which("nvidia-smi") is None:
            return
        try:
            output = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,utilization.gpu,memory.used",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=True,
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return
        first = output.splitlines()[0] if output else ""
        parts = [item.strip() for item in first.split(",")]
        if len(parts) != 3:
            return
        self._gpu_name = parts[0]
        try:
            self._gpu_util.append((now, float(parts[1])))
            self._gpu_mem_mb.append((now, float(parts[2])))
        except ValueError:
            return

    @staticmethod
    def _window(series: list[tuple[float, float]], warmup: float) -> list[float]:
        scored = [value for at, value in series if at >= warmup]
        return scored or [value for _, value in series]

    def _histogram_window(self, warmup: float) -> tuple[_Scrape | None, _Scrape | None]:
        """Baseline = the last scrape at or before the warm-up boundary; final = the last."""
        if not self._scrapes:
            return None, None
        before = [scrape for scrape in self._scrapes if scrape.at <= warmup]
        baseline = before[-1] if before else self._scrapes[0]
        return baseline, self._scrapes[-1]

    def summary(self, *, warmup_seconds: float) -> dict:
        server: dict[str, dict] = {}
        first, last = self._histogram_window(warmup_seconds)
        if first is not None and last is not None:
            for (name, labels), pair in last.histograms.items():
                start = first.histograms.get((name, labels), [0.0, 0.0])
                delta_count = pair[1] - start[1]
                if delta_count <= 0:
                    continue
                delta_sum = pair[0] - start[0]
                server.setdefault(name, {})[_label_key(labels)] = {
                    "count": round(delta_count),
                    "mean_ms": round(delta_sum / delta_count * 1000, 3),
                }
            for (name, labels), value in last.counters.items():
                delta = value - first.counters.get((name, labels), 0.0)
                if delta <= 0:
                    continue
                server.setdefault(name, {})[_label_key(labels)] = round(delta, 3)

        host: dict[str, float] = {}
        if self._cpu:
            cpu = self._window(self._cpu, warmup_seconds)
            mem_pct = self._window(self._mem_percent, warmup_seconds)
            mem_mb = self._window(self._mem_used_mb, warmup_seconds)
            host = {
                "cpu_percent_mean": round(sum(cpu) / len(cpu), 2),
                "cpu_percent_max": round(max(cpu), 2),
                "mem_percent_mean": round(sum(mem_pct) / len(mem_pct), 2),
                "mem_used_mb_max": round(max(mem_mb), 1),
            }

        if self._gpu_util:
            util = self._window(self._gpu_util, warmup_seconds)
            mem = self._window(self._gpu_mem_mb, warmup_seconds)
            gpu: dict = {
                "available": True,
                "name": self._gpu_name,
                "util_percent_mean": round(sum(util) / len(util), 2),
                "util_percent_max": round(max(util), 2),
                "mem_used_mb_max": round(max(mem), 1),
            }
        else:
            gpu = {"available": False}

        return {
            "scrapes": len(self._scrapes),
            "endpoints": dict(self._endpoint_status),
            "server_metrics": server,
            "host": host,
            "gpu": gpu,
        }
