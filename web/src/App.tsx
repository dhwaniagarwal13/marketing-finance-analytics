import { LiveBar } from "./components/LiveBar";
import { useColorMode } from "./components/primitives";
import { useLiveSnapshot } from "./state/useLiveSnapshot";
import { Overview } from "./pages/Overview";

export default function App() {
  const [mode, setMode] = useColorMode();
  const { snapshot, sim, connection, error, control } = useLiveSnapshot();

  return (
    <div className="shell">
      <header className="masthead">
        <div>
          <h1>Marketing + Finance Analytics</h1>
          <p className="sub">
            Channel profitability, customer value and a quantified growth plan.
          </p>
        </div>
        <div className="toolbar">
          {snapshot && (
            <span className="chip" title="Server-side compute time for this snapshot">
              {snapshot.computed_ms} ms
            </span>
          )}
          <button
            className="btn"
            type="button"
            onClick={() => setMode(mode === "dark" ? "light" : "dark")}
            aria-label={`Switch to ${mode === "dark" ? "light" : "dark"} theme`}
          >
            {mode === "dark" ? "Light" : "Dark"}
          </button>
        </div>
      </header>

      <LiveBar sim={sim} connection={connection} onControl={control} />

      {error && (
        <div className="state err" role="alert">
          {error}
        </div>
      )}

      {!snapshot && <div className="state">Loading analysis…</div>}

      {snapshot && (
        // Reduced opacity while the stream is down, rather than a skeleton
        // flash: the numbers on screen are still real, just no longer current.
        <div
          className={connection === "offline" ? "stale" : undefined}
          aria-live="polite"
          aria-busy={connection !== "live"}
        >
          <Overview snapshot={snapshot} mode={mode} />
        </div>
      )}
    </div>
  );
}
