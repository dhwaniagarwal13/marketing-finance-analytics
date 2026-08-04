/**
 * Number formatting.
 *
 * `null` means genuinely undefined — ROAS with no spend, LTV:CAC with no CAC —
 * and renders as an em dash rather than 0 or NaN. The API converts every
 * non-finite value to null before it leaves the server, so this is the only
 * missing case the UI has to handle.
 */

const EM_DASH = "—";

export function currency(value: number | null | undefined, decimals = 0): string {
  if (value == null || !Number.isFinite(value)) return EM_DASH;
  return value.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

/** Compact form for axis ticks, where "$1.3M" beats "$1,291,170". */
export function currencyCompact(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return EM_DASH;
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `$${Math.round(value / 1_000)}k`;
  return `$${Math.round(value)}`;
}

export function percent(value: number | null | undefined, decimals = 1): string {
  if (value == null || !Number.isFinite(value)) return EM_DASH;
  return `${(value * 100).toFixed(decimals)}%`;
}

export function ratio(value: number | null | undefined, decimals = 2): string {
  if (value == null || !Number.isFinite(value)) return EM_DASH;
  return `${value.toFixed(decimals)}x`;
}

export function number(value: number | null | undefined, decimals = 0): string {
  if (value == null || !Number.isFinite(value)) return EM_DASH;
  return value.toLocaleString("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

export function monthLabel(iso: string): string {
  const [year, month] = iso.split("-");
  const names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                 "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${names[Number(month) - 1]} ${year.slice(2)}`;
}
