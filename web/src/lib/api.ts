import type { Snapshot } from "./types";

/**
 * Same-origin fetch helpers.
 *
 * In production FastAPI serves the built assets, so `/api` is a relative path
 * and there is no CORS surface. In dev, Vite proxies `/api` to the local
 * server, which keeps that true there too.
 */

export class ApiError extends Error {
  constructor(readonly status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

async function get<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
  const url = new URL(path, window.location.origin);
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value !== undefined) url.searchParams.set(key, String(value));
  }

  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body?.detail) detail = body.detail;
    } catch {
      // Non-JSON error body; the status line is all we have.
    }
    throw new ApiError(response.status, detail);
  }
  return response.json() as Promise<T>;
}

export function fetchSnapshot(opts: { dataset?: string; asOf?: string } = {}): Promise<Snapshot> {
  return get<Snapshot>("/api/analysis", {
    dataset: opts.dataset ?? "demo",
    as_of: opts.asOf,
  });
}

export interface Health {
  status: string;
  version: string;
  git_sha: string;
  uptime_s: number;
  datasets_loaded: number;
}

export function fetchHealth(): Promise<Health> {
  return get<Health>("/api/health");
}
