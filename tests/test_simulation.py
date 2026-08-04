"""
The replay ticker.

The properties worth pinning are the ones the wall-clock design exists to
provide: restart-independence, client agreement, and exact convergence on the
static analysis at the end of the timeline.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from analytics.ingest import load_from_paths
from api.main import create_app
from api.settings import Settings
from api.simulation import SIM_EPOCH, SimulationEngine, sse_frame


@pytest.fixture(scope="module")
def bundle(project_root):
    return load_from_paths(project_root / "data" / "raw")


@pytest.fixture
def sim(bundle, project_root):
    settings = Settings(data_dir=project_root / "data" / "raw",
                        tick_seconds=3.0, days_per_tick=7)
    return SimulationEngine(bundle, settings)


# ---------------------------------------------------------------------------
# Cursor
# ---------------------------------------------------------------------------
def test_span_is_derived_from_the_data(sim):
    assert str(sim.sim_start.date()) == "2024-02-25"
    assert str(sim.sim_end.date()) == "2025-12-31"


def test_cursor_is_a_function_of_wall_clock(sim):
    """
    The restart-independence property.

    The cursor depends only on elapsed time since a fixed epoch, so a redeploy
    or a crash-restart lands where it should have rather than rewinding to zero.
    """
    moment = SIM_EPOCH + timedelta(seconds=300)
    first = sim.cursor(moment)

    reborn = SimulationEngine(sim.bundle, sim.settings)  # fresh process
    assert reborn.cursor(moment).date == first.date
    assert reborn.cursor(moment).tick == first.tick


def test_cursor_advances_one_step_per_tick(sim):
    base = SIM_EPOCH + timedelta(seconds=600)
    a = sim.cursor(base)
    b = sim.cursor(base + timedelta(seconds=sim.settings.tick_seconds))
    assert b.tick == a.tick + 1
    assert (b.date - a.date).days == sim.settings.days_per_tick


def test_cursor_never_runs_past_the_data(sim):
    """Beyond the last tick the cursor holds at the end rather than inventing dates."""
    for extra in (0, 5, 20, 100):
        tick = sim.total_ticks + extra
        moment = SIM_EPOCH + timedelta(seconds=tick * sim.settings.tick_seconds)
        assert sim.cursor(moment).date <= sim.sim_end


def test_replay_loops_and_holds_at_the_end(sim):
    """
    A visitor arriving late must not find a dead stream.

    The cycle holds at the final cursor for a few ticks — so the complete,
    notebook-matching picture is what a latecomer sees — then restarts.
    """
    holding = [
        sim.cursor(SIM_EPOCH + timedelta(seconds=t * sim.settings.tick_seconds))
        for t in range(sim.total_ticks, sim.total_ticks + sim.settings.loop_pause_ticks)
    ]
    assert all(c.holding_at_end for c in holding)
    assert all(c.date == sim.sim_end for c in holding)

    wrapped = sim.cursor(SIM_EPOCH + timedelta(seconds=sim._cycle_length * sim.settings.tick_seconds))
    assert wrapped.tick == 0
    assert wrapped.date == sim.sim_start


def test_pause_freezes_the_cursor(sim):
    sim.pause()
    first = sim.cursor(SIM_EPOCH + timedelta(seconds=10))
    later = sim.cursor(SIM_EPOCH + timedelta(seconds=10_000))
    assert first.tick == later.tick


def test_resume_continues_rather_than_jumping(sim):
    sim.seek(pd.Timestamp("2024-09-01"))
    sim.pause()
    paused = sim.cursor().tick
    sim.resume()
    assert abs(sim.cursor().tick - paused) <= 1


def test_seek_lands_on_the_requested_date(sim):
    sim.seek(pd.Timestamp("2025-03-01"))
    cursor = sim.cursor()
    assert abs((cursor.date - pd.Timestamp("2025-03-01")).days) <= sim.settings.days_per_tick


def test_reset_returns_to_the_start(sim):
    sim.seek(pd.Timestamp("2025-06-01"))
    sim.reset()
    assert sim.cursor().tick == 0
    assert sim.cursor().date == sim.sim_start


# ---------------------------------------------------------------------------
# Frames
# ---------------------------------------------------------------------------
def test_sse_frame_is_wire_correct():
    frame = sse_frame("snapshot", {"a": 1})
    assert frame.startswith(b"event: snapshot\ndata: ")
    assert frame.endswith(b"\n\n")


def test_sse_frame_refuses_non_finite_numbers():
    """
    NaN would serialize to a token `JSON.parse` rejects, breaking the stream in
    the browser while looking fine on the server. Fail here instead.
    """
    with pytest.raises(ValueError):
        sse_frame("snapshot", {"bad": float("nan")})


@pytest.mark.anyio
async def test_refresh_produces_a_serializable_snapshot(sim):
    payload = await sim.refresh(force=True)
    assert payload["sim"]["mode"] == "replay"
    json.dumps(payload, allow_nan=False, default=str)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_slow_subscriber_gets_latest_not_a_backlog(sim):
    """Drop-oldest: a client that misses ticks resumes at current state."""
    queue = sim.subscribe()
    sim._publish(b"first")
    sim._publish(b"second")
    sim._publish(b"third")

    assert queue.qsize() == 1
    assert await queue.get() == b"third"


# ---------------------------------------------------------------------------
# HTTP surface
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def client():
    with TestClient(create_app()) as c:
        yield c


def test_sim_state_endpoint(client):
    body = client.get("/api/sim").json()
    assert body["mode"] == "replay"
    assert body["sim_start"] == "2024-02-25"
    assert body["sim_end"] == "2025-12-31"
    assert body["total_ticks"] > 0


def test_seek_then_read_moves_the_cursor(client):
    client.post("/api/sim/control", json={"action": "pause"})
    r = client.post("/api/sim/control",
                    json={"action": "seek", "cursor_date": "2025-06-01"})
    assert r.status_code == 200
    assert r.json()["sim"]["cursor_date"].startswith("2025-0")
    client.post("/api/sim/control", json={"action": "reset"})


def test_seek_without_a_date_is_rejected(client):
    r = client.post("/api/sim/control", json={"action": "seek"})
    assert r.status_code == 422


def test_stream_rejects_non_demo_datasets(client):
    r = client.get("/api/stream", params={"dataset": "something-else"})
    assert r.status_code == 400
    assert "static" in r.json()["detail"]


def test_stream_is_reachable_and_typed(client):
    """
    Only the handshake is checked through TestClient.

    Reading frames here would deadlock: TestClient drives the app in a portal
    thread and an endless SSE generator never observes the client going away,
    so closing the response waits on a generator that never returns. Frame
    content is covered by `test_live_stream_delivers_frames` against a real
    server instead.
    """
    r = client.get("/api/stream", params={"dataset": "nope"})
    assert r.status_code == 400


@pytest.mark.integration
def test_live_stream_delivers_frames(project_root):
    """
    Exercises the production path: a real uvicorn process, real sockets.

    This is the only way to verify the pieces that only exist over the wire —
    the event framing, the content type, and the anti-buffering header a proxy
    needs in order not to swallow the stream.
    """
    import socket
    import subprocess
    import sys
    import time
    import urllib.error
    import urllib.request

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api.main:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=project_root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        base = f"http://127.0.0.1:{port}"
        for _ in range(60):
            try:
                urllib.request.urlopen(f"{base}/api/health", timeout=1).read()
                break
            except (urllib.error.URLError, ConnectionError, TimeoutError):
                time.sleep(0.5)
        else:
            pytest.fail("server did not come up")

        events, payload, buffer = [], None, ""
        with urllib.request.urlopen(f"{base}/api/stream", timeout=30) as response:
            assert response.headers["content-type"].startswith("text/event-stream")
            assert response.headers["x-accel-buffering"] == "no"

            deadline = time.time() + 25
            while time.time() < deadline and len(events) < 2:
                chunk = response.read(4096)
                if not chunk:
                    break
                buffer += chunk.decode("utf-8", errors="replace")
                while "\n\n" in buffer:
                    raw, buffer = buffer.split("\n\n", 1)
                    if not raw.startswith("event:"):
                        continue  # heartbeat comment
                    events.append(raw.split("\n", 1)[0].removeprefix("event: "))
                    if raw.startswith("event: snapshot") and payload is None:
                        payload = json.loads(raw.split("data: ", 1)[1])
    finally:
        proc.terminate()
        proc.wait(timeout=15)

    assert events[:2] == ["hello", "snapshot"]
    assert payload is not None
    assert set(payload["modules"]) == {"marketing", "customers", "finance",
                                       "experiments", "forecast"}
    assert payload["sim"]["mode"] == "replay"
    # Non-finite values would have failed json.loads under strict parsing.
    assert payload["as_of"]


def test_no_gzip_middleware_is_installed():
    """
    Starlette's GZipMiddleware buffers the response body, which breaks SSE in a
    way that only shows up behind a proxy in production.
    """
    app = create_app()
    names = [m.cls.__name__ for m in app.user_middleware]
    assert "GZipMiddleware" not in names
