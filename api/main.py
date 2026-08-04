"""
FastAPI application.

Serves the API and, when present, the built frontend from the same origin —
no CORS, no preflight on the event stream, one URL, one artifact, one rollback.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from analytics.errors import AnalysisError

from .routers import analysis, meta, stream
from .settings import get_settings
from .simulation import SimulationEngine
from .store import DatasetStore

log = logging.getLogger("mfa")

SWEEP_INTERVAL_SECONDS = 60


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper())

    app.state.store = DatasetStore(settings)
    bundle = app.state.store.bootstrap_demo()
    log.info(
        "demo dataset loaded: %s rows, %s flagged quality issues",
        bundle.provenance.rows_clean, len(bundle.quality.flagged),
    )

    app.state.sim = SimulationEngine(bundle, settings)
    app.state.sim.start()
    log.info(
        "replay ticker: %s -> %s over %d ticks of %ds",
        app.state.sim.sim_start.date(), app.state.sim.sim_end.date(),
        app.state.sim.total_ticks, settings.tick_seconds,
    )

    sweeper = asyncio.create_task(_sweep_forever(app))
    try:
        yield
    finally:
        await stream.shutdown(app.state.sim)
        sweeper.cancel()
        try:
            await sweeper
        except asyncio.CancelledError:
            pass


async def _sweep_forever(app: FastAPI) -> None:
    """Drop idle uploads so a long-running instance cannot grow without bound."""
    while True:
        await asyncio.sleep(SWEEP_INTERVAL_SECONDS)
        try:
            removed = app.state.store.sweep()
            if removed:
                log.info("swept %d idle dataset(s)", removed)
        except Exception:  # noqa: BLE001 — a sweep failure must not kill the loop
            log.exception("dataset sweep failed")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Marketing + Finance Analytics",
        version=settings.version,
        summary="Live marketing analytics over a replayed campaign timeline, "
                "or over your own uploaded CSVs.",
        lifespan=lifespan,
    )

    # NOTE: no GZipMiddleware. Starlette's gzip buffers the response body, which
    # silently breaks Server-Sent Events — it works locally and hangs forever
    # behind a proxy. Compression belongs at the edge, which can exclude
    # text/event-stream properly.

    @app.exception_handler(AnalysisError)
    async def analysis_error_handler(_: Request, exc: AnalysisError) -> JSONResponse:
        """Typed analysis failures are results, not server errors."""
        return JSONResponse(status_code=200, content={**exc.as_dict(), "data": None})

    app.include_router(meta.router, prefix="/api")
    app.include_router(analysis.router, prefix="/api")
    app.include_router(stream.router, prefix="/api")

    if settings.static_dir.is_dir():
        app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="static")

    return app


app = create_app()
