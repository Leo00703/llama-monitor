"""Analytics: persistent per-request history (SQLite) + energy cost estimates.

Data source: the structured ``slot print_timing`` lines llama-server prints
for every completed request (already captured by LlamaServerManager's log
stream). Energy per request is estimated from the GPU ``power.draw`` samples
collected by the metrics loop (ring buffer of (ts, total_power_w) pairs),
averaged over the request's time window.
"""

from __future__ import annotations

import csv
import io
import logging
import re
import sqlite3
import time
from contextlib import contextmanager
from collections import deque
from pathlib import Path
from typing import Any, Callable, Optional

log = logging.getLogger("llama-monitor.analytics")

RANGES = ("day", "week", "month", "year", "all")

# llama-server prints one block of 3 lines per completed request.
# Newer builds right-align the numbers (padded with spaces), e.g.:
#   slot print_timing: id  3 | task 0 | prompt eval time =      30.47 ms /     9 tokens (    3.39 ms per token,   295.37 tokens per second)
#   slot print_timing: id  3 | task 0 |        eval time =      456.78 ms /   100 tokens (     4.57 ms per token,    218.89 tokens per second)
#   slot print_timing: id  3 | task 0 |       total time =     500.25 ms /   109 tokens
# Older builds use single spaces; both are matched by the \s+ below.
_PROMPT_RE = re.compile(
    r"slot print_timing: id\s+(\d+)\s*\|\s*task\s+(-?\d+)\s*\|\s*prompt eval time =\s*([\d.]+) ms /\s*(\d+) tokens"
    r"(?:\s*\(.*?([\d.]+) tokens per second\))?"
)
_EVAL_RE = re.compile(
    r"(?:^|\|)\s*eval time =\s*([\d.]+) ms /\s*(\d+) tokens(?:\s*\(.*?([\d.]+) tokens per second\))?"
)
_TOTAL_RE = re.compile(r"(?:^|\|)\s*total time =\s*([\d.]+) ms /\s*(\d+) tokens")
# With speculative decoding (MTP/draft) a fourth line follows the total line:
#   slot print_timing: id  3 | task 0 | draft acceptance = 0.65217 (   65 accepted /  100 generated), mean len =  1.65
_DRAFT_RE = re.compile(
    r"slot print_timing: id\s+(\d+)\s*\|\s*task\s+(-?\d+)\s*\|\s*"
    r"draft acceptance =\s*[\d.]+\s*\(\s*(\d+) accepted /\s*(\d+) generated\)"
)


def _f(value: Optional[str]) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _tps(tokens: int, ms: float, reported: Optional[float]) -> Optional[float]:
    """Trust the server-reported tps unless it is a division artifact of a
    near-zero time (the server prints e.g. 1000000.00 for a sub-millisecond
    eval). Fall back to tokens/ms, or None when the time rounds to zero."""
    if reported is not None and reported <= 10000.0:
        return reported
    if ms and ms > 0 and tokens:
        return tokens * 1000.0 / ms
    return None


class PrintTimingTracker:
    """Accumulates the print_timing block into one completed record.

    The block is printed back-to-back by the server, so a single pending
    slot is enough. With speculative decoding a fourth "draft acceptance"
    line follows the total line, so the block is finalized lazily: on the
    draft line, on the next log line of any kind, or via ``tick()`` once
    the total line is >1s old (server went silent).
    """

    def __init__(self, on_complete: Callable[[dict], None]) -> None:
        self._on_complete = on_complete
        self._pending: Optional[dict] = None
        self._seq = 0
        self.latest: Optional[dict] = None

    def feed(self, line: str) -> None:
        m = _PROMPT_RE.search(line)
        if m:
            if self._pending is not None and self._pending.get("total_seen"):
                self._finalize()
            self._pending = {
                "slot_id": int(m.group(1)),
                "task_id": int(m.group(2)),
                "prompt_ms": float(m.group(3)),
                "prompt_tokens": int(m.group(4)),
                "prompt_tps": _tps(int(m.group(4)), float(m.group(3)), _f(m.group(5))),
            }
            return
        if self._pending is None:
            return
        m = _EVAL_RE.search(line)
        if m:
            self._pending["eval_ms"] = float(m.group(1))
            self._pending["gen_tokens"] = int(m.group(2))
            self._pending["gen_tps"] = _tps(int(m.group(2)), float(m.group(1)), _f(m.group(3)))
            return
        m = _TOTAL_RE.search(line)
        if m:
            self._pending["total_ms"] = float(m.group(1))
            self._pending["total_tokens"] = int(m.group(2))
            self._pending["total_seen"] = True
            self._pending["total_ts"] = time.time()
            return
        m = _DRAFT_RE.search(line)
        if m:
            self._pending["draft_accepted"] = int(m.group(3))
            self._pending["draft_proposed"] = int(m.group(4))
            self._finalize()
            return
        if self._pending.get("total_seen"):
            self._finalize()

    def _finalize(self) -> None:
        rec, self._pending = self._pending, None
        if rec.get("gen_tokens") is None:
            rec["gen_tokens"] = max(rec.get("total_tokens", 0) - rec.get("prompt_tokens", 0), 0)
        if rec.get("total_ms") is None:
            rec["total_ms"] = (rec.get("prompt_ms") or 0.0) + (rec.get("eval_ms") or 0.0)
        self._seq += 1
        self.latest = {
            "seq": self._seq,
            "prompt_tps": rec.get("prompt_tps"),
            "gen_tps": rec.get("gen_tps"),
            "draft_proposed": rec.get("draft_proposed"),
            "draft_accepted": rec.get("draft_accepted"),
        }
        self._on_complete(rec)

    def tick(self) -> None:
        """Close a block whose total line arrived but was never followed by
        a draft line or any other log line (server went silent)."""
        p = self._pending
        if p and p.get("total_seen") and time.time() - p.get("total_ts", 0.0) > 1.0:
            self._finalize()

    def reset(self) -> None:
        """Drop a partially parsed block (e.g. on server stop/restart)."""
        self._pending = None
        self.latest = None


class PowerSampler:
    """Ring buffer of (ts, total_power_w) samples; estimates Wh over a window."""

    def __init__(self, max_samples: int = 3600) -> None:
        self._samples: deque[tuple[float, float]] = deque(maxlen=max_samples)

    def add(self, ts: float, power_w: Optional[float]) -> None:
        if power_w is None or power_w < 0:
            return
        self._samples.append((ts, power_w))

    def energy_wh(self, start_ts: float, end_ts: float) -> Optional[float]:
        """Average power in [start, end] x duration, in Wh. None if no samples."""
        if end_ts <= start_ts:
            return None
        window = [p for t, p in self._samples if start_ts <= t <= end_ts]
        if not window:
            return None
        avg_w = sum(window) / len(window)
        return avg_w * (end_ts - start_ts) / 3600.0


_SCHEMA = """
CREATE TABLE IF NOT EXISTS generation_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    preset_id TEXT DEFAULT '',
    preset_name TEXT DEFAULT '',
    model TEXT DEFAULT '',
    prompt_tokens INTEGER,
    gen_tokens INTEGER,
    prompt_tps REAL,
    gen_tps REAL,
    total_ms REAL,
    draft_proposed INTEGER,
    draft_accepted INTEGER,
    energy_wh REAL
)
"""

_FAILED_SCHEMA = """
CREATE TABLE IF NOT EXISTS failed_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    model TEXT DEFAULT '',
    status INTEGER,
    path TEXT DEFAULT ''
)
"""


class AnalyticsStore:
    """SQLite-backed per-request history with range aggregations."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._path = str(db_path)
        with self._conn() as conn:
            conn.execute(_SCHEMA)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_gen_ts ON generation_records(ts)")
            conn.execute(_FAILED_SCHEMA)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_failed_ts ON failed_requests(ts)")

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # write
    # ------------------------------------------------------------------

    def record(self, *, ts: float, preset_id: str, preset_name: str, model: str,
               rec: dict, energy_wh: Optional[float]) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO generation_records
                   (ts, preset_id, preset_name, model, prompt_tokens, gen_tokens,
                    prompt_tps, gen_tps, total_ms, draft_proposed, draft_accepted, energy_wh)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    ts,
                    preset_id or "",
                    preset_name or "",
                    model or "",
                    rec.get("prompt_tokens"),
                    rec.get("gen_tokens"),
                    rec.get("prompt_tps"),
                    rec.get("gen_tps"),
                    rec.get("total_ms"),
                    rec.get("draft_proposed"),
                    rec.get("draft_accepted"),
                    energy_wh,
                ),
            )

    def record_failure(self, *, ts: float, model: str, status: int, path: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO failed_requests (ts, model, status, path) VALUES (?,?,?,?)",
                (ts, model or "", status, path or ""),
            )

    # ------------------------------------------------------------------
    # read
    # ------------------------------------------------------------------

    def failed_count(self, range_name: str) -> int:
        start = self.range_start(range_name if range_name in RANGES else "all")
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM failed_requests WHERE ts >= ?", (start,)
            ).fetchone()
        return int(row["n"]) if row else 0

    @staticmethod
    def range_start(range_name: str, now: Optional[float] = None) -> float:
        now = now if now is not None else time.time()
        if range_name == "day":
            d = time.localtime(now)
            return time.mktime((d.tm_year, d.tm_mon, d.tm_mday, 0, 0, 0, 0, 0, 0))
        if range_name == "week":
            return now - 7 * 86400
        if range_name == "month":
            return now - 30 * 86400
        if range_name == "year":
            return now - 365 * 86400
        return 0.0

    def _fetch(self, range_name: str) -> list[dict[str, Any]]:
        start = self.range_start(range_name if range_name in RANGES else "all")
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT ts, preset_name, model, prompt_tokens, gen_tokens,
                          prompt_tps, gen_tps, total_ms, energy_wh
                   FROM generation_records WHERE ts >= ? ORDER BY ts""",
                (start,),
            ).fetchall()
        return [dict(r) for r in rows]

    def summary(self, range_name: str, price: float) -> dict:
        rows = self._fetch(range_name)
        n = len(rows)
        prompt = sum(r["prompt_tokens"] or 0 for r in rows)
        gen = sum(r["gen_tokens"] or 0 for r in rows)
        avg_gen = _avg([r["gen_tps"] for r in rows if r["gen_tps"] is not None])
        avg_prompt = _avg([r["prompt_tps"] for r in rows if r["prompt_tps"] is not None])
        max_gen = max([r["gen_tps"] for r in rows if r["gen_tps"] is not None] or [None])
        energies = [r["energy_wh"] for r in rows if r["energy_wh"] is not None]
        energy_wh = sum(energies) if energies else None
        cost = (energy_wh / 1000.0) * price if energy_wh is not None else None
        cost_per_1m = (cost / gen) * 1_000_000 if (cost is not None and gen > 0) else None
        return {
            "range": range_name,
            "requests": n,
            "failed": self.failed_count(range_name),
            "prompt_tokens": prompt,
            "gen_tokens": gen,
            "avg_prompt_tps": avg_prompt,
            "avg_gen_tps": avg_gen,
            "max_gen_tps": max_gen,
            "has_energy": bool(energies),
            "energy_wh": energy_wh,
            "cost_eur": cost,
            "cost_per_1m": cost_per_1m,
            "energy_price_eur_kwh": price,
        }

    def timeseries(self, range_name: str, price: float,
                   bucket: Optional[str] = None) -> dict:
        bucket = bucket or _default_bucket(range_name)
        rows = self._fetch(range_name)
        if not rows:
            return {"range": range_name, "bucket": bucket, "buckets": []}

        now = time.time()
        start = self.range_start(range_name, now)
        bounds = _bucket_sequence(bucket, start, now)
        by_bucket: dict[float, list[dict]] = {b: [] for b in bounds}
        for r in rows:
            b = _bucket_bounds(bucket, r["ts"])
            if b in by_bucket:
                by_bucket[b].append(r)

        out: list[dict] = []
        for b in bounds:
            group = by_bucket[b]
            gen = sum(r["gen_tokens"] or 0 for r in group)
            energies = [r["energy_wh"] for r in group if r["energy_wh"] is not None]
            energy_wh = sum(energies) if energies else None
            cost = (energy_wh / 1000.0) * price if energy_wh is not None else None
            out.append({
                "ts": b,
                "label": _bucket_label(bucket, b),
                "requests": len(group),
                "prompt_tokens": sum(r["prompt_tokens"] or 0 for r in group),
                "gen_tokens": gen,
                "avg_gen_tps": _avg([r["gen_tps"] for r in group if r["gen_tps"] is not None]),
                "avg_prompt_tps": _avg([r["prompt_tps"] for r in group if r["prompt_tps"] is not None]),
                "energy_wh": energy_wh,
                "cost_eur": cost,
            })
        return {"range": range_name, "bucket": bucket, "buckets": out}

    def models(self, range_name: str, price: float) -> list[dict]:
        rows = self._fetch(range_name)
        grouped: dict[str, list[dict]] = {}
        for r in rows:
            key = r["model"] or "(unknown)"
            grouped.setdefault(key, []).append(r)

        out: list[dict] = []
        for name, group in grouped.items():
            gen = sum(r["gen_tokens"] or 0 for r in group)
            energies = [r["energy_wh"] for r in group if r["energy_wh"] is not None]
            energy_wh = sum(energies) if energies else None
            cost = (energy_wh / 1000.0) * price if energy_wh is not None else None
            cost_per_1m = (cost / gen) * 1_000_000 if (cost is not None and gen > 0) else None
            out.append({
                "model": name,
                "requests": len(group),
                "prompt_tokens": sum(r["prompt_tokens"] or 0 for r in group),
                "gen_tokens": gen,
                "avg_gen_tps": _avg([r["gen_tps"] for r in group if r["gen_tps"] is not None]),
                "max_gen_tps": max([r["gen_tps"] for r in group if r["gen_tps"] is not None] or [None]),
                "energy_wh": energy_wh,
                "cost_eur": cost,
                "cost_per_1m": cost_per_1m,
            })
        out.sort(key=lambda m: m["gen_tokens"] or 0, reverse=True)
        return out

    def records(self, range_name: str, limit: int = 100) -> list[dict]:
        rows = self._fetch(range_name)
        return list(reversed(rows[-limit:]))

    def export_csv(self, range_name: str) -> str:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "timestamp", "preset", "model", "prompt_tokens", "gen_tokens",
            "prompt_tps", "gen_tps", "total_ms", "energy_wh",
        ])
        for r in self._fetch(range_name):
            writer.writerow([
                time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r["ts"])),
                r["preset_name"] or "",
                r["model"] or "",
                r["prompt_tokens"] if r["prompt_tokens"] is not None else "",
                r["gen_tokens"] if r["gen_tokens"] is not None else "",
                "" if r["prompt_tps"] is None else f"{r['prompt_tps']:.2f}",
                "" if r["gen_tps"] is None else f"{r['gen_tps']:.2f}",
                "" if r["total_ms"] is None else f"{r['total_ms']:.0f}",
                "" if r["energy_wh"] is None else f"{r['energy_wh']:.3f}",
            ])
        return buf.getvalue()


def _avg(values: list[float]) -> Optional[float]:
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _default_bucket(range_name: str) -> str:
    return {
        "day": "hour",
        "week": "day",
        "month": "day",
        "year": "week",
        "all": "month",
    }.get(range_name, "day")


def _bucket_bounds(bucket: str, ts: float) -> float:
    d = time.localtime(ts)
    if bucket == "hour":
        return ts - (ts % 3600)
    if bucket == "day":
        return time.mktime((d.tm_year, d.tm_mon, d.tm_mday, 0, 0, 0, 0, 0, 0))
    if bucket == "week":
        day = time.mktime((d.tm_year, d.tm_mon, d.tm_mday, 0, 0, 0, 0, 0, 0))
        return day - time.localtime(day).tm_wday * 86400
    if bucket == "month":
        return time.mktime((d.tm_year, d.tm_mon, 1, 0, 0, 0, 0, 0, 0))
    return ts - (ts % 86400)


def _bucket_next(bucket: str, ts: float) -> float:
    d = time.localtime(ts)
    if bucket == "hour":
        return ts + 3600
    if bucket == "day":
        return time.mktime((d.tm_year, d.tm_mon, d.tm_mday + 1, 0, 0, 0, 0, 0, 0))
    if bucket == "week":
        return ts + 7 * 86400
    if bucket == "month":
        y, m = d.tm_year, d.tm_mon + 1
        if m > 12:
            y, m = y + 1, 1
        return time.mktime((y, m, 1, 0, 0, 0, 0, 0, 0))
    return ts + 86400


def _bucket_sequence(bucket: str, start: float, end: float, cap: int = 1000) -> list[float]:
    # clamp far-past starts: Windows' mktime overflows on pre-epoch local times
    out: list[float] = []
    t = _bucket_bounds(bucket, max(start, 946684800.0))
    while t <= end and len(out) < cap:
        out.append(t)
        t = _bucket_next(bucket, t)
    return out


def _bucket_label(bucket: str, ts: float) -> str:
    d = time.localtime(ts)
    if bucket == "hour":
        return time.strftime("%H:%M", d)
    if bucket == "day":
        return time.strftime("%b %d", d)
    if bucket == "week":
        return f"W{time.strftime('%V', d)}"
    if bucket == "month":
        return time.strftime("%b %Y", d)
    return time.strftime("%b %d", d)
