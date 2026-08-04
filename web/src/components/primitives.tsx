import type { ReactNode } from "react";
import { useEffect, useState } from "react";

import type { Envelope } from "../lib/types";

/**
 * A stat tile is a chart. When the story is one number, a one-bar bar chart is
 * the wrong form — the number is the whole encoding.
 *
 * `basis` is not decoration here: ROAS is campaign-attributed revenue over
 * spend while ROI is transaction profit over spend, so two adjacent tiles are
 * measuring different revenue universes. Saying so is the difference between a
 * dashboard and a misleading one.
 */
export function StatTile({
  label,
  value,
  basis,
}: {
  label: string;
  value: string;
  basis?: string;
}) {
  return (
    <div className="tile">
      <div className="label">
        {label}
        {basis && (
          <button className="info" type="button" title={basis} aria-label={`${label}: ${basis}`}>
            ⓘ
          </button>
        )}
      </div>
      <div className="value">{value}</div>
      {basis && <div className="basis">{basis}</div>}
    </div>
  );
}

export function Card({
  title,
  note,
  action,
  wide,
  children,
}: {
  title: string;
  note?: string;
  action?: ReactNode;
  wide?: boolean;
  children: ReactNode;
}) {
  return (
    <section className={wide ? "card wide" : "card"}>
      <div className="card-head">
        <h2>{title}</h2>
        {action}
      </div>
      {note && <p className="note">{note}</p>}
      {children}
    </section>
  );
}

/**
 * Renders a module's envelope, or explains precisely why it has nothing to show.
 *
 * Every non-ok state carries a reason from the server ("forecast needs 6
 * months; has 2"), so a greyed card never leaves the reader guessing whether
 * the app is broken or the data is thin.
 */
export function ModuleGate<T>({
  envelope,
  children,
}: {
  envelope: Envelope<T> | undefined;
  children: (data: T) => ReactNode;
}) {
  if (!envelope) return <div className="state">Loading…</div>;
  if (envelope.status !== "ok" || envelope.data == null) {
    return (
      <div className="state">
        {envelope.reason ?? "Not available for this dataset."}
      </div>
    );
  }
  return <>{children(envelope.data)}</>;
}

/** Toggle between a chart and its table-view twin. Every chart has one. */
export function ViewToggle({
  showTable,
  onChange,
}: {
  showTable: boolean;
  onChange: (next: boolean) => void;
}) {
  return (
    <button
      className="btn"
      type="button"
      aria-pressed={showTable}
      onClick={() => onChange(!showTable)}
    >
      {showTable ? "Chart" : "Table"}
    </button>
  );
}

export type Mode = "light" | "dark";

/** Tracks the effective colour mode so charts can pick their validated steps. */
export function useColorMode(): [Mode, (next: Mode) => void] {
  const [mode, setMode] = useState<Mode>(() => {
    const stamped = document.documentElement.dataset.theme as Mode | undefined;
    if (stamped) return stamped;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  });

  useEffect(() => {
    document.documentElement.dataset.theme = mode;
  }, [mode]);

  useEffect(() => {
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = (event: MediaQueryListEvent) => {
      // Only follow the OS while the user has not chosen explicitly.
      if (!localStorage.getItem("theme")) setMode(event.matches ? "dark" : "light");
    };
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  const choose = (next: Mode) => {
    localStorage.setItem("theme", next);
    setMode(next);
  };

  return [mode, choose];
}
