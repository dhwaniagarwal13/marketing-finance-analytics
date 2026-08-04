import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { currency, currencyCompact, monthLabel, number, ratio } from "../lib/format";
import type { ChannelRow } from "../lib/types";
import { channelColor, theme } from "../theme.generated";
import type { Mode } from "./primitives";

/** Chrome for the active mode. Dark is a validated set of steps, not a flip. */
function chrome(mode: Mode) {
  return mode === "dark" ? theme.dark.chrome : theme.chrome;
}

const AXIS_TICK = { fontSize: 11, fontVariantNumeric: "tabular-nums" as const };

interface TooltipRow {
  label: string;
  value: string;
}

function Tip({ title, rows }: { title: string; rows: TooltipRow[] }) {
  return (
    <div className="tooltip">
      <div className="t-title">{title}</div>
      {rows.map((row) => (
        <div className="t-row" key={row.label}>
          <span>{row.label}</span>
          <b>{row.value}</b>
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ trend */

/**
 * Monthly revenue.
 *
 * One series, so no legend box — the card title names it. Crosshair plus
 * tooltip is the default interaction for a line, and the endpoint carries a
 * direct label so the most recent value is readable without hovering.
 */
export function RevenueTrend({
  months,
  mode,
  yMax,
}: {
  months: { month: string; revenue: number }[];
  mode: Mode;
  /** Held maximum, so the axis does not rescale under the line each tick. */
  yMax?: number;
}) {
  const c = chrome(mode);
  const hue = mode === "dark" ? theme.dark.categorical[0] : theme.categorical[0];
  const data = months.map((m) => ({ ...m, label: monthLabel(m.month) }));

  return (
    <ResponsiveContainer width="100%" height={260}>
      <LineChart data={data} margin={{ top: 8, right: 20, bottom: 4, left: 4 }}>
        <CartesianGrid stroke={c.gridline} strokeWidth={1} vertical={false} />
        <XAxis
          dataKey="label"
          tick={{ ...AXIS_TICK, fill: c.muted }}
          axisLine={{ stroke: c.baseline }}
          tickLine={false}
          minTickGap={24}
        />
        <YAxis
          domain={[0, yMax ?? "auto"]}
          tickFormatter={(v) => currencyCompact(v as number)}
          tick={{ ...AXIS_TICK, fill: c.muted }}
          axisLine={false}
          tickLine={false}
          width={54}
        />
        <Tooltip
          cursor={{ stroke: c.baseline, strokeWidth: 1 }}
          content={({ active, payload }) =>
            active && payload?.length ? (
              <Tip
                title={payload[0].payload.label}
                rows={[{ label: "Revenue", value: currency(payload[0].value as number) }]}
              />
            ) : null
          }
        />
        <Line
          type="monotone"
          dataKey="revenue"
          stroke={hue}
          strokeWidth={2}
          dot={false}
          activeDot={{ r: 4, strokeWidth: 2, stroke: c.surface }}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

/* --------------------------------------------------------------- channels */

/**
 * ROAS and CPA by channel — deliberately two charts, never one with two y-axes.
 *
 * A dual-axis plot invents a correlation by choosing where the two scales line
 * up. The notebook already drew these as two subplots; a React port is exactly
 * where that would get "simplified" into one chart with two <YAxis>.
 *
 * Bars carry direct value labels because three of the seven channel hues
 * (Instagram, Email, Affiliate) sit below 3:1 against the light surface. That
 * relief is required, not stylistic.
 */
export function ChannelBars({
  rows,
  metric,
  mode,
}: {
  rows: ChannelRow[];
  metric: "roas" | "cpa";
  mode: Mode;
}) {
  const c = chrome(mode);
  const dark = mode === "dark";

  // Zero-spend channels are excluded, not plotted at zero. Organic's CPA is
  // $0.00 only because it has no attributable media cost — drawn as a bar it
  // reads as "cheapest acquisition", which inverts the meaning.
  const data = rows
    .filter((r) => r.spend > 0 && r[metric] != null)
    .slice()
    .sort((a, b) => (b[metric] ?? 0) - (a[metric] ?? 0));

  const fmt = metric === "roas" ? (v: number) => ratio(v) : (v: number) => currency(v, 2);

  // ROAS spans 1.6x to 88x here: Email is a near-zero-media-cost owned channel,
  // so on a linear scale its bar flattens every paid channel into a stub and
  // the comparison the chart exists to make becomes unreadable. A log axis is
  // the standard treatment for ratio data across two orders of magnitude, and
  // the direct labels carry the exact values regardless.
  const useLog = metric === "roas" && data.length > 1 &&
    (data[0][metric] ?? 0) / (data[data.length - 1][metric] || 1) > 12;

  const excluded = rows.filter((r) => r.spend <= 0).map((r) => r.channel);

  return (
    <>
    <ResponsiveContainer width="100%" height={Math.max(180, data.length * 32 + 56)}>
      <BarChart
        data={data}
        layout="vertical"
        margin={{ top: 4, right: 60, bottom: 4, left: 4 }}
        barCategoryGap={6}
      >
        <CartesianGrid stroke={c.gridline} strokeWidth={1} horizontal={false} />
        <XAxis
          type="number"
          scale={useLog ? "log" : "linear"}
          domain={useLog ? [1, "dataMax"] : [0, "dataMax"]}
          allowDataOverflow={false}
          ticks={useLog ? [1, 3, 10, 30, 100] : undefined}
          tickFormatter={(v) => (metric === "roas" ? `${v}x` : `$${v}`)}
          tick={{ ...AXIS_TICK, fill: c.muted }}
          axisLine={{ stroke: c.baseline }}
          tickLine={false}
          height={20}
        />
        <YAxis
          type="category"
          dataKey="channel"
          tick={{ fontSize: 12, fill: c.muted }}
          axisLine={{ stroke: c.baseline }}
          tickLine={false}
          width={86}
        />
        <Tooltip
          cursor={{ fill: c.gridline, fillOpacity: 0.5 }}
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const row = payload[0].payload as ChannelRow;
            return (
              <Tip
                title={row.channel}
                rows={[
                  { label: "ROAS", value: ratio(row.roas) },
                  { label: "CPA", value: currency(row.cpa, 2) },
                  { label: "Spend", value: currency(row.spend) },
                  { label: "Revenue", value: currency(row.revenue) },
                ]}
              />
            );
          }}
        />
        <Bar dataKey={metric} radius={[0, 4, 4, 0]} isAnimationActive={false}>
          {data.map((row) => (
            <Cell key={row.channel} fill={channelColor(row.channel, dark)} />
          ))}
          <LabelList
            dataKey={metric}
            position="right"
            offset={8}
            style={{ fill: c.secondaryInk, fontSize: 11, fontVariantNumeric: "tabular-nums" }}
            formatter={(v: number) => fmt(v)}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
    {(useLog || excluded.length > 0) && (
      <p className="note" style={{ margin: "6px 0 0", fontSize: 11.5 }}>
        {useLog && "Log scale — Email's near-zero media cost puts its ROAS two orders of magnitude above the paid channels. "}
        {excluded.length > 0 &&
          `${excluded.join(", ")} excluded: no attributable media spend, so this metric is not defined.`}
      </p>
    )}
    </>
  );
}

/**
 * Campaign revenue against net profit.
 *
 * Two measures in the same unit (dollars), so one axis is honest here — this
 * is a grouped bar, not a dual axis. Two series means a legend is required.
 */
export function RevenueVsProfit({
  rows,
  mode,
}: {
  rows: { channel: string; campaign_revenue: number; net_profit: number }[];
  mode: Mode;
}) {
  const c = chrome(mode);
  const palette = mode === "dark" ? theme.dark.categorical : theme.categorical;
  const data = rows.slice().sort((a, b) => b.campaign_revenue - a.campaign_revenue);

  return (
    <>
      <div style={{ display: "flex", gap: 16, marginBottom: 8, fontSize: 12, color: c.secondaryInk }}>
        <LegendKey color={palette[0]} label="Campaign revenue" />
        <LegendKey color={palette[2]} label="Net profit" />
      </div>
      <ResponsiveContainer width="100%" height={272}>
        <BarChart data={data} margin={{ top: 4, right: 8, bottom: 4, left: 4 }} barGap={2}>
          <CartesianGrid stroke={c.gridline} strokeWidth={1} vertical={false} />
          <XAxis
            dataKey="channel"
            tick={{ fontSize: 11, fill: c.muted }}
            axisLine={{ stroke: c.baseline }}
            tickLine={false}
            interval={0}
            angle={-22}
            textAnchor="end"
            height={54}
          />
          <YAxis
            tickFormatter={(v) => currencyCompact(v as number)}
            tick={{ ...AXIS_TICK, fill: c.muted }}
            axisLine={false}
            tickLine={false}
            width={54}
          />
          <Tooltip
            cursor={{ fill: c.gridline, fillOpacity: 0.5 }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const row = payload[0].payload as { channel: string; campaign_revenue: number; net_profit: number };
              return (
                <Tip
                  title={row.channel}
                  rows={[
                    { label: "Campaign revenue", value: currency(row.campaign_revenue) },
                    { label: "Net profit", value: currency(row.net_profit) },
                  ]}
                />
              );
            }}
          />
          <Bar dataKey="campaign_revenue" fill={palette[0]} radius={[4, 4, 0, 0]} isAnimationActive={false} />
          <Bar dataKey="net_profit" fill={palette[2]} radius={[4, 4, 0, 0]} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </>
  );
}

function LegendKey({ color, label }: { color: string; label: string }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
      <span className="swatch" style={{ background: color }} aria-hidden />
      {label}
    </span>
  );
}

/* ------------------------------------------------------------ table twin */

/** The table view every chart needs — and the relief for the sub-3:1 hues. */
export function ChannelTable({ rows, mode }: { rows: ChannelRow[]; mode: Mode }) {
  const dark = mode === "dark";
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th scope="col">Channel</th>
            <th scope="col">Spend</th>
            <th scope="col">Revenue</th>
            <th scope="col">ROAS</th>
            <th scope="col">CPA</th>
            <th scope="col">CTR</th>
            <th scope="col">CVR</th>
            <th scope="col">Conversions</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.channel}>
              <td>
                <span
                  className="swatch"
                  style={{ background: channelColor(row.channel, dark) }}
                  aria-hidden
                />
                {row.channel}
              </td>
              <td>{currency(row.spend)}</td>
              <td>{currency(row.revenue)}</td>
              <td>{ratio(row.roas)}</td>
              <td>{currency(row.cpa, 2)}</td>
              <td>{row.ctr == null ? "—" : `${(row.ctr * 100).toFixed(2)}%`}</td>
              <td>{row.cvr == null ? "—" : `${(row.cvr * 100).toFixed(2)}%`}</td>
              <td>{number(row.conversions)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
