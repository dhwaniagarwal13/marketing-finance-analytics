"""
The replay ticker.

The cursor walks the existing timeline rather than synthesising new rows. The
dataset already spans 2024-02-25 to 2025-12-31, so `bundle.as_of(cursor)` is
the entire simulation — and it carries real seasonality, real Black Friday
spikes, real cohort maturation, and TikTok launching mid-stream, none of which
a per-tick random generator would produce.

It also gives a correctness oracle for free: when the cursor reaches the end of
the data, the live app must return exactly the numbers in the notebooks and the
PDF. `tests/test_truncation.py::test_converges_exactly_on_the_static_analysis`
asserts that.

## Why the cursor is derived from wall-clock

`tick = f(now)`, not a counter that increments. Consequences, all of them good:

* **Stateless across restarts.** A redeploy, an OOM respawn or a Fly machine
  move lands the cursor where it should be, instead of resetting to zero.
* **Every client agrees by construction** — no coordination, no drift.
* **A slow tick drops a frame instead of accumulating lag.** If a recompute
  overruns its budget, the next cursor is still correct.

Total mutable state is two integers: an offset and an optional pause point.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pandas as pd

from analytics.config import DEFAULTS, AnalysisParams
from analytics.ingest import DatasetBundle
from analytics.snapshot import build_snapshot

from .settings import Settings

log = logging.getLogger("mfa.sim")

# Fixed reference point for the wall-clock cursor. Arbitrary but constant: the
# cursor depends on elapsed time since this instant, so it must never move.
SIM_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)

HEARTBEAT_SECONDS = 15


def sse_frame(event: str, payload: dict) -> bytes:
    """
    One Server-Sent Event.

    `allow_nan=False` on purpose: NaN is not valid JSON and `JSON.parse` rejects
    it, so a non-finite value must fail loudly here rather than silently break
    the stream in a browser. `analytics.snapshot.sanitize` should have converted
    them to null already.
    """
    body = json.dumps(payload, separators=(",", ":"), allow_nan=False, default=str)
    return f"event: {event}\ndata: {body}\n\n".encode()


@dataclass
class Cursor:
    date: pd.Timestamp
    tick: int
    total_ticks: int
    holding_at_end: bool


class SimulationEngine:
    """Advances a cursor over the demo dataset and broadcasts snapshots."""

    def __init__(self, bundle: DatasetBundle, settings: Settings,
                 params: AnalysisParams = DEFAULTS):
        self.bundle = bundle
        self.settings = settings
        self.params = params

        self.sim_start = pd.Timestamp(min(
            df[col].min()
            for col, df in (
                ("date", bundle.campaigns),
                ("acquisition_date", bundle.customers),
                ("transaction_date", bundle.transactions),
            )
            if df is not None and len(df)
        ))
        self.sim_end = pd.Timestamp(bundle.max_date)

        span_days = (self.sim_end - self.sim_start).days
        self.total_ticks = max(1, -(-span_days // settings.days_per_tick))  # ceil

        self.offset = 0
        self.paused_at: int | None = None

        self.latest: bytes | None = None
        self.latest_payload: dict | None = None
        self.version = 0
        self.subscribers: set[asyncio.Queue[bytes]] = set()
        self._last_key: tuple | None = None
        self._task: asyncio.Task | None = None

    # -- cursor ------------------------------------------------------------
    @property
    def _cycle_length(self) -> int:
        return self.total_ticks + self.settings.loop_pause_ticks

    def cursor(self, now: datetime | None = None) -> Cursor:
        if self.paused_at is not None:
            raw = self.paused_at
        else:
            elapsed = ((now or datetime.now(UTC)) - SIM_EPOCH).total_seconds()
            raw = self.offset + int(elapsed // self.settings.tick_seconds)

        tick = raw % self._cycle_length
        holding = tick >= self.total_ticks

        date = self.sim_start + timedelta(days=tick * self.settings.days_per_tick)
        return Cursor(
            date=min(date, self.sim_end),
            tick=tick,
            total_ticks=self.total_ticks,
            holding_at_end=holding,
        )

    def state(self) -> dict:
        c = self.cursor()
        return {
            "mode": "replay",
            "cursor_date": str(c.date.date()),
            "tick": c.tick,
            "total_ticks": c.total_ticks,
            "holding_at_end": c.holding_at_end,
            "sim_start": str(self.sim_start.date()),
            "sim_end": str(self.sim_end.date()),
            "tick_seconds": self.settings.tick_seconds,
            "days_per_tick": self.settings.days_per_tick,
            "paused": self.paused_at is not None,
            "connected_clients": len(self.subscribers),
            "snapshot_version": self.version,
        }

    # -- controls ----------------------------------------------------------
    def pause(self) -> None:
        if self.paused_at is None:
            self.paused_at = self.cursor().tick

    def resume(self) -> None:
        if self.paused_at is None:
            return
        # Re-anchor the offset so resuming continues from where it paused
        # rather than jumping to wherever wall-clock has since reached.
        elapsed = (datetime.now(UTC) - SIM_EPOCH).total_seconds()
        natural = int(elapsed // self.settings.tick_seconds)
        self.offset = self.paused_at - natural
        self.paused_at = None

    def reset(self) -> None:
        elapsed = (datetime.now(UTC) - SIM_EPOCH).total_seconds()
        self.offset = -int(elapsed // self.settings.tick_seconds)
        self.paused_at = None

    def seek(self, target: pd.Timestamp) -> None:
        target = pd.Timestamp(target)
        days = max(0, (target - self.sim_start).days)
        tick = min(self.total_ticks, days // self.settings.days_per_tick)
        if self.paused_at is not None:
            self.paused_at = int(tick)
        else:
            elapsed = (datetime.now(UTC) - SIM_EPOCH).total_seconds()
            self.offset = int(tick) - int(elapsed // self.settings.tick_seconds)

    # -- broadcast ---------------------------------------------------------
    def subscribe(self) -> asyncio.Queue[bytes]:
        # maxsize=1 with drop-oldest: a slow client gets the newest state rather
        # than a growing backlog. Missing intermediate frames is correct here —
        # each snapshot is complete, not a delta.
        queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=1)
        self.subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[bytes]) -> None:
        self.subscribers.discard(queue)

    def _publish(self, frame: bytes) -> None:
        """One serialization, one shared buffer, fanned out to every client."""
        for queue in list(self.subscribers):
            if queue.full():
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(frame)

    async def _compute(self, cursor: Cursor) -> dict:
        sliced = self.bundle.as_of(cursor.date)
        # Offloaded: a ~1s blocking pandas recompute on the event loop would
        # stall every SSE heartbeat and every other request in flight.
        snapshot = await asyncio.to_thread(
            build_snapshot, sliced, self.params, cursor.date)
        snapshot["sim"] = self.state()
        return snapshot

    async def refresh(self, force: bool = False) -> dict:
        cursor = self.cursor()
        key = (cursor.date, self.params.fingerprint())
        if not force and key == self._last_key:
            return self.latest_payload or {}

        started = time.perf_counter()
        payload = await self._compute(cursor)
        elapsed = time.perf_counter() - started

        budget = self.settings.tick_seconds * self.settings.tick_budget_warn_ratio
        if elapsed > budget:
            log.warning(
                "tick compute %.2fs exceeded %.0f%% of the %.1fs budget at cursor %s",
                elapsed, self.settings.tick_budget_warn_ratio * 100,
                self.settings.tick_seconds, cursor.date.date(),
            )

        self.latest_payload = payload
        self.latest = sse_frame("snapshot", payload)
        self.version += 1
        self._last_key = key
        return payload

    # -- loop --------------------------------------------------------------
    async def _sleep_to_next_boundary(self) -> None:
        """Align to the tick grid so the cursor does not drift from wall-clock."""
        period = self.settings.tick_seconds
        now = (datetime.now(UTC) - SIM_EPOCH).total_seconds()
        await asyncio.sleep(period - (now % period))

    async def run(self) -> None:
        await self.refresh(force=True)
        while True:
            try:
                await self._sleep_to_next_boundary()
                payload = await self.refresh()
                if payload and self.latest:
                    self._publish(self.latest)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 — one bad tick must not end the stream
                log.exception("tick failed; continuing")

    def start(self) -> None:
        self._task = asyncio.create_task(self.run())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None
