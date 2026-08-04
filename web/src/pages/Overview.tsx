import { useState } from "react";

import {
  ChannelBars,
  ChannelTable,
  RevenueTrend,
  RevenueVsProfit,
} from "../components/charts";
import type { Mode } from "../components/primitives";
import { Card, ModuleGate, StatTile, ViewToggle } from "../components/primitives";
import { currency, monthLabel, percent, ratio } from "../lib/format";
import type { Snapshot } from "../lib/types";
import { useGrowingMax } from "../state/useLiveSnapshot";

export function Overview({ snapshot, mode }: { snapshot: Snapshot; mode: Mode }) {
  const [showChannelTable, setShowChannelTable] = useState(false);
  const { marketing, finance, forecast } = snapshot.modules;
  const kpis = finance.status === "ok" ? finance.data?.kpis : undefined;

  // Hold the peak so the revenue axis grows but never shrinks: recomputing it
  // per frame would slide the scale under the line and hide the trend.
  const peak = marketing.status === "ok" ? marketing.data?.seasonality.peak_revenue : undefined;
  const revenueMax = useGrowingMax(peak);

  return (
    <>
      {kpis && (
        <div className="tiles">
          <StatTile label="Revenue" value={currency(kpis.total_revenue?.value)}
                    basis={kpis.total_revenue?.basis} />
          <StatTile label="Marketing spend" value={currency(kpis.total_spend?.value)}
                    basis={kpis.total_spend?.basis} />
          <StatTile label="Net profit" value={currency(kpis.total_net_profit?.value)}
                    basis={kpis.total_net_profit?.basis} />
          <StatTile label="LTV : CAC" value={`${(kpis.ltv_cac_ratio?.value ?? 0).toFixed(2)} : 1`}
                    basis={kpis.ltv_cac_ratio?.basis} />
          <StatTile label="ROAS" value={ratio(kpis.blended_roas?.value)}
                    basis={kpis.blended_roas?.basis} />
          <StatTile label="Repeat rate" value={percent(kpis.repeat_rate?.value)}
                    basis={kpis.repeat_rate?.basis} />
        </div>
      )}

      <div className="grid">
        <Card
          title="Monthly revenue"
          note={
            marketing.status === "ok" && marketing.data
              ? `${marketing.data.seasonality.months_used} complete months. Peak: ${monthLabel(
                  marketing.data.seasonality.peak_month,
                )} at ${currency(marketing.data.seasonality.peak_revenue)}.`
              : undefined
          }
          wide
        >
          <ModuleGate envelope={marketing}>
            {(data) => (
              <RevenueTrend
                months={data.seasonality.months}
                mode={mode}
                yMax={revenueMax ? Math.ceil(revenueMax * 1.1) : undefined}
              />
            )}
          </ModuleGate>
        </Card>

        <Card
          title="Channel efficiency"
          note="ROAS and CPA are different scales, so they are two charts. Overlaying them on one plot with two y-axes would imply a relationship that the data does not contain."
          action={<ViewToggle showTable={showChannelTable} onChange={setShowChannelTable} />}
          wide
        >
          <ModuleGate envelope={marketing}>
            {(data) => {
              const rows = data.by_dimension.channel ?? [];
              if (showChannelTable) return <ChannelTable rows={rows} mode={mode} />;
              return (
                <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))" }}>
                  <div>
                    <p className="note">Return on ad spend</p>
                    <ChannelBars rows={rows} metric="roas" mode={mode} />
                  </div>
                  <div>
                    <p className="note">Cost per acquisition</p>
                    <ChannelBars rows={rows} metric="cpa" mode={mode} />
                  </div>
                </div>
              );
            }}
          </ModuleGate>
        </Card>

        <Card
          title="Revenue is not profit"
          note="Campaign-attributed revenue against net profit after marketing spend. Where a channel's two bars disagree in rank, a revenue-only leaderboard would misdirect budget."
          wide
        >
          <ModuleGate envelope={finance}>
            {(data) => <RevenueVsProfit rows={data.profitability} mode={mode} />}
          </ModuleGate>
        </Card>

        <Card title="Next-quarter forecast">
          <ModuleGate envelope={forecast}>
            {(data) => (
              <>
                <div className="tiles" style={{ margin: "4px 0 12px" }}>
                  <StatTile
                    label="Forecast total"
                    value={currency(data.total)}
                    basis={`${data.label}, ${data.selected_by}`}
                  />
                </div>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th scope="col">Month</th>
                        <th scope="col">Forecast revenue</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.months.map((m) => (
                        <tr key={m.month}>
                          <td>{monthLabel(m.month)}</td>
                          <td>{currency(m.forecast_revenue)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {data.diagnostics.caveat && (
                  <div className="banner" style={{ marginTop: 12, marginBottom: 0 }}>
                    <span aria-hidden>⚠</span>
                    <span>
                      <b>Read this forecast carefully.</b> {data.diagnostics.caveat}
                    </span>
                  </div>
                )}
              </>
            )}
          </ModuleGate>
        </Card>

        <Card
          title="Data quality"
          note={`${snapshot.quality.total_flagged} checks flagged on load. Rows removed before any KPI was computed.`}
        >
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">Check</th>
                  <th scope="col">Table</th>
                  <th scope="col">Rows</th>
                </tr>
              </thead>
              <tbody>
                {snapshot.quality.issues
                  .filter((i) => i.issue_count > 0)
                  .map((issue) => (
                    <tr key={issue.key}>
                      <td title={issue.why_it_matters}>{issue.check}</td>
                      <td style={{ textAlign: "left" }}>{issue.table}</td>
                      <td>{issue.issue_count}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </>
  );
}
