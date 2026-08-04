import type { Connection, SimState } from "../state/useLiveSnapshot";

/**
 * The replay strip: where the cursor is, and how to move it.
 *
 * States the honest thing about the demo — this is a replay of a fixed,
 * seeded dataset, not a live feed from a real business. Pretending otherwise
 * would be the one genuinely dishonest thing this app could do.
 */
export function LiveBar({
  sim,
  connection,
  onControl,
}: {
  sim: SimState | null;
  connection: Connection;
  onControl: (action: "pause" | "resume" | "reset") => void;
}) {
  if (!sim) {
    return (
      <div className="livebar">
        <span className="dot connecting" aria-hidden />
        <span>Connecting to the replay stream…</span>
      </div>
    );
  }

  const pct = Math.min(100, (sim.tick / Math.max(1, sim.total_ticks)) * 100);
  const status =
    connection === "live" && sim.paused ? "paused"
      : connection === "live" ? "live"
      : connection;

  return (
    <div className="livebar">
      <span className={`dot ${status}`} aria-hidden />
      <span className="livebar-label">
        {status === "live" ? "REPLAY" : status.toUpperCase()}
      </span>

      <strong className="cursor-date">{sim.cursor_date}</strong>

      <span className="livebar-progress" role="progressbar" aria-valuenow={Math.round(pct)}
            aria-valuemin={0} aria-valuemax={100}
            aria-label={`Replay position: ${sim.cursor_date}`}>
        <span className="livebar-fill" style={{ width: `${pct}%` }} />
      </span>

      <span className="livebar-meta">
        tick {sim.tick}/{sim.total_ticks}
        {sim.holding_at_end && " · complete"}
      </span>

      <span className="livebar-actions">
        <button className="btn" type="button"
                onClick={() => onControl(sim.paused ? "resume" : "pause")}>
          {sim.paused ? "Resume" : "Pause"}
        </button>
        <button className="btn" type="button" onClick={() => onControl("reset")}>
          Restart
        </button>
      </span>

      <span className="livebar-note">
        Replaying {sim.sim_start} → {sim.sim_end} at {sim.days_per_tick} days
        every {sim.tick_seconds}s. Seeded synthetic data, not a live feed.
      </span>
    </div>
  );
}
