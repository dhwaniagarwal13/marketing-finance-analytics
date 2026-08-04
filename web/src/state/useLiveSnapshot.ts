import { useCallback, useEffect, useRef, useState } from "react";

import { fetchSnapshot } from "../lib/api";
import type { Snapshot } from "../lib/types";

export interface SimState {
  mode: string;
  cursor_date: string;
  tick: number;
  total_ticks: number;
  holding_at_end: boolean;
  sim_start: string;
  sim_end: string;
  tick_seconds: number;
  days_per_tick: number;
  paused: boolean;
  connected_clients: number;
}

export type Connection = "connecting" | "live" | "reconnecting" | "offline";

interface Live {
  snapshot: Snapshot | null;
  sim: SimState | null;
  connection: Connection;
  error: string | null;
  control: (action: "pause" | "resume" | "reset") => Promise<void>;
}

const MAX_BACKOFF_MS = 30_000;

/**
 * Follows the server's replay cursor over Server-Sent Events.
 *
 * Every frame is a complete snapshot, not a delta, so a dropped frame costs
 * nothing — the next one is authoritative. That is what lets the server hold a
 * single-slot queue per client and discard anything a slow reader missed.
 *
 * EventSource reconnects on its own, but with no jitter and no cap, so a
 * restart would have every open tab retry in lockstep. This manages the
 * lifecycle explicitly instead.
 */
export function useLiveSnapshot(): Live {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [sim, setSim] = useState<SimState | null>(null);
  const [connection, setConnection] = useState<Connection>("connecting");
  const [error, setError] = useState<string | null>(null);

  const sourceRef = useRef<EventSource | null>(null);
  const attemptRef = useRef(0);
  const timerRef = useRef<number | null>(null);

  const apply = useCallback((raw: string) => {
    try {
      const next = JSON.parse(raw) as Snapshot & { sim?: SimState };
      setSnapshot(next);
      if (next.sim) setSim(next.sim);
      setError(null);
    } catch {
      setError("Received a malformed frame from the server.");
    }
  }, []);

  useEffect(() => {
    let disposed = false;

    const connect = () => {
      if (disposed) return;
      const source = new EventSource("/api/stream?dataset=demo");
      sourceRef.current = source;

      source.addEventListener("hello", (event) => {
        attemptRef.current = 0;
        setConnection("live");
        try {
          setSim(JSON.parse((event as MessageEvent).data) as SimState);
        } catch {
          /* the following snapshot frame carries sim state too */
        }
      });

      source.addEventListener("snapshot", (event) => {
        setConnection("live");
        apply((event as MessageEvent).data);
      });

      source.onerror = () => {
        source.close();
        if (disposed) return;
        setConnection(attemptRef.current === 0 ? "reconnecting" : "offline");

        // Exponential backoff with jitter, so a server restart does not bring
        // every open tab back at the same instant.
        const attempt = Math.min(attemptRef.current++, 5);
        const base = Math.min(1000 * 2 ** attempt, MAX_BACKOFF_MS);
        const delay = base * (0.5 + Math.random() * 0.5);
        timerRef.current = window.setTimeout(connect, delay);
      };
    };

    connect();

    // If the stream is unavailable entirely, fall back to a one-shot fetch so
    // the page shows real analysis rather than an empty shell.
    fetchSnapshot()
      .then((initial) => setSnapshot((current) => current ?? initial))
      .catch(() => undefined);

    return () => {
      disposed = true;
      sourceRef.current?.close();
      if (timerRef.current) window.clearTimeout(timerRef.current);
    };
  }, [apply]);

  const control = useCallback(async (action: "pause" | "resume" | "reset") => {
    const response = await fetch("/api/sim/control", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action }),
    });
    if (response.ok) {
      const body = await response.json();
      if (body?.sim) setSim(body.sim);
    }
  }, []);

  return { snapshot, sim, connection, error, control };
}

/**
 * A y-domain that only ever grows.
 *
 * Recomputing the axis from the current slice would rescale the chart on every
 * tick, so the line appears to stay flat while the axis moves underneath it —
 * the growth is real but invisible. Holding the running maximum keeps new
 * points meaningful against the ones already drawn.
 */
export function useGrowingMax(value: number | undefined): number | undefined {
  const ref = useRef<number | undefined>(undefined);
  const [, force] = useState(0);

  useEffect(() => {
    if (value == null) return;
    if (ref.current == null || value > ref.current) {
      ref.current = value;
      force((n) => n + 1);
    }
  }, [value]);

  return ref.current == null ? value : Math.max(ref.current, value ?? 0);
}
