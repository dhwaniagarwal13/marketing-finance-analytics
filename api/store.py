"""
In-memory dataset registry.

Uploaded CSVs are parsed to DataFrames and the original bytes discarded —
nothing touches disk. That removes a whole category of failure (temp-file
cleanup, path traversal, read-only container filesystems) and costs nothing,
since a 2.7 MB CSV is ~15 MB in memory and the cap is 20 datasets.

`demo` is reserved, pinned, and never evicted.
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field

from analytics.config import DEFAULTS, AnalysisParams
from analytics.ingest import DatasetBundle, load_from_paths

from .settings import Settings, get_settings

DEMO_ID = "demo"


@dataclass
class Entry:
    bundle: DatasetBundle
    created_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    pinned: bool = False

    def touch(self) -> None:
        self.last_seen = time.time()


class DatasetNotFound(KeyError):
    pass


class DatasetStore:
    """TTL + LRU registry. Thread-safe: the tick loop reads while requests write."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._entries: dict[str, Entry] = {}
        self._lock = threading.RLock()

    # -- lifecycle ---------------------------------------------------------
    def bootstrap_demo(self, params: AnalysisParams = DEFAULTS) -> DatasetBundle:
        bundle = load_from_paths(self.settings.data_dir, params)
        with self._lock:
            self._entries[DEMO_ID] = Entry(bundle=bundle, pinned=True)
        return bundle

    def get(self, dataset_id: str) -> DatasetBundle:
        with self._lock:
            entry = self._entries.get(dataset_id)
            if entry is None:
                raise DatasetNotFound(dataset_id)
            entry.touch()
            return entry.bundle

    def add(self, bundle: DatasetBundle) -> str:
        dataset_id = secrets.token_urlsafe(16)
        with self._lock:
            self._evict_if_needed()
            self._entries[dataset_id] = Entry(bundle=bundle)
        return dataset_id

    def delete(self, dataset_id: str) -> bool:
        if dataset_id == DEMO_ID:
            return False
        with self._lock:
            return self._entries.pop(dataset_id, None) is not None

    # -- maintenance -------------------------------------------------------
    def sweep(self) -> int:
        """Drop idle datasets. Returns how many were removed."""
        cutoff = time.time() - self.settings.dataset_ttl_seconds
        with self._lock:
            stale = [
                key for key, entry in self._entries.items()
                if not entry.pinned and entry.last_seen < cutoff
            ]
            for key in stale:
                del self._entries[key]
        return len(stale)

    def _evict_if_needed(self) -> None:
        """Least-recently-seen eviction, never touching pinned entries."""
        evictable = {k: e for k, e in self._entries.items() if not e.pinned}
        while len(evictable) >= self.settings.max_datasets:
            oldest = min(evictable, key=lambda k: evictable[k].last_seen)
            del self._entries[oldest]
            del evictable[oldest]

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._entries)

    def expires_at(self, dataset_id: str) -> float | None:
        with self._lock:
            entry = self._entries.get(dataset_id)
            if entry is None or entry.pinned:
                return None
            return entry.last_seen + self.settings.dataset_ttl_seconds
