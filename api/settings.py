"""Runtime configuration, overridable by environment variable."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MFA_", env_file=".env", extra="ignore")

    # --- data ---------------------------------------------------------------
    data_dir: Path = PROJECT_ROOT / "data" / "raw"
    static_dir: Path = PROJECT_ROOT / "static"

    # --- simulation ---------------------------------------------------------
    # 7 sim-days per tick replays the full 22 months in roughly five minutes.
    #
    # Measured cost of one tick (slice + full snapshot + serialize) on a warm
    # process: ~1.1 s at the end of the timeline, ~0.7 s mid-way. That is well
    # under a 3 s tick locally, but a shared-cpu Fly machine is slower, so the
    # deployed default is 5 s. Overrun is not fatal — the cursor is derived
    # from wall-clock rather than counted, so a slow tick drops a frame instead
    # of drifting — but sustained overrun means clients see stale data.
    tick_seconds: float = 5.0
    days_per_tick: int = 7
    # Warn when a tick uses more than this share of its budget.
    tick_budget_warn_ratio: float = 0.6
    # Hold at the end so a visitor arriving late sees the complete picture —
    # the one that matches the notebooks — before the loop restarts.
    loop_pause_ticks: int = 10

    # --- upload limits ------------------------------------------------------
    # This is a public endpoint feeding pandas; every cap here is load-bearing.
    max_upload_bytes: int = 25 * 1024 * 1024
    max_datasets: int = 20
    dataset_ttl_seconds: int = 30 * 60
    max_rows: dict[str, int] = {
        "campaigns": 200_000,
        "customers": 100_000,
        "transactions": 500_000,
        "ab_test": 10_000,
    }

    # --- ops ----------------------------------------------------------------
    log_level: str = "info"
    version: str = "0.1.0"


@lru_cache
def get_settings() -> Settings:
    return Settings()
