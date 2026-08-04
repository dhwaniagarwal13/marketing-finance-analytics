"""
Server-Sent Events, plus the simulation controls.

Only the demo dataset streams. Uploads are static — there is no cursor to
advance and nothing to push, so they use plain `GET /api/analysis`.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..simulation import HEARTBEAT_SECONDS, SimulationEngine, sse_frame

router = APIRouter(tags=["stream"])


def engine(request: Request) -> SimulationEngine:
    sim = getattr(request.app.state, "sim", None)
    if sim is None:
        raise HTTPException(status_code=503, detail="Simulation is not running.")
    return sim


@router.get("/sim")
def sim_state(request: Request) -> dict:
    return engine(request).state()


class SimControl(BaseModel):
    action: Literal["pause", "resume", "reset", "seek"]
    cursor_date: date | None = None


@router.post("/sim/control")
async def sim_control(request: Request, body: SimControl) -> dict:
    """
    Controls are global — any visitor can pause the shared stream.

    That is a deliberate trade for a portfolio demo: it keeps every client on
    one cursor and one snapshot per tick. Gate behind an admin token if the
    demo ever needs to be tamper-proof.
    """
    sim = engine(request)

    if body.action == "pause":
        sim.pause()
    elif body.action == "resume":
        sim.resume()
    elif body.action == "reset":
        sim.reset()
    elif body.action == "seek":
        if body.cursor_date is None:
            raise HTTPException(status_code=422, detail="seek requires cursor_date")
        sim.seek(body.cursor_date)

    payload = await sim.refresh(force=True)
    if sim.latest:
        sim._publish(sim.latest)
    return {"ok": True, "sim": payload.get("sim", sim.state())}


@router.get("/stream")
async def stream(request: Request, dataset: str = Query("demo")) -> StreamingResponse:
    if dataset != "demo":
        raise HTTPException(
            status_code=400,
            detail="Only the demo dataset streams; uploaded datasets are static. "
                   "Use GET /api/analysis instead.",
        )

    sim = engine(request)

    async def events():
        queue = sim.subscribe()
        try:
            yield sse_frame("hello", sim.state())
            # Send current state immediately so a client that connects mid-tick
            # renders straight away instead of waiting for the next boundary.
            if sim.latest:
                yield sim.latest

            while True:
                if await request.is_disconnected():
                    break
                try:
                    frame = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
                    yield frame
                except TimeoutError:
                    # Comment frame: keeps proxies from reaping an idle
                    # connection, and is ignored by EventSource.
                    yield b": ping\n\n"
        finally:
            sim.unsubscribe(queue)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            # Tells nginx and friends not to buffer. Without it the stream
            # works locally and silently hangs behind a proxy.
            "X-Accel-Buffering": "no",
        },
    )


async def shutdown(sim: SimulationEngine | None) -> None:
    if sim is not None:
        with contextlib.suppress(Exception):
            await sim.stop()
