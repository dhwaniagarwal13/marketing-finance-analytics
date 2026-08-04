/** Shapes returned by /api. Mirrors analytics/snapshot.py. */

export type ModuleStatus = "ok" | "unavailable" | "insufficient_data" | "degraded" | "error";

export interface Envelope<T> {
  status: ModuleStatus;
  reason: string | null;
  computed_ms: number;
  data: T | null;
  need?: string;
  have?: string;
}

/** Every KPI carries its basis: two of them are not what a reader would assume. */
export interface Kpi {
  value: number | null;
  basis: string;
}

export interface ChannelRow {
  channel: string;
  impressions: number;
  clicks: number;
  conversions: number;
  spend: number;
  revenue: number;
  ctr: number | null;
  cvr: number | null;
  cpc: number | null;
  cpa: number | null;
  roas: number | null;
}

export interface FunnelStage {
  stage: string;
  value: number;
  pct_of_initial: number | null;
}

export interface MarketingData {
  funnel: {
    impressions: number;
    clicks: number;
    conversions: number;
    spend: number;
    revenue: number;
    ctr: number | null;
    cvr: number | null;
    cpc: number | null;
    cpa: number | null;
    roas: number | null;
    stages: FunnelStage[];
  };
  by_dimension: Record<string, ChannelRow[]>;
  seasonality: {
    months: { month: string; revenue: number }[];
    peak_month: string;
    peak_revenue: number;
    mean_revenue: number;
    months_used: number;
  };
}

export interface ProfitabilityRow {
  channel: string;
  campaign_revenue: number;
  marketing_spend: number;
  customer_gross_profit: number;
  net_profit: number;
  revenue_rank: number;
  profit_rank: number;
  rank_shift: number;
  contribution_margin: number | null;
  profit_per_customer: number | null;
  roi: number | null;
}

export interface FinanceData {
  kpis: Record<string, Kpi>;
  profitability: ProfitabilityRow[];
  cac_ltv: {
    channel: string;
    cac: number;
    ltv: number;
    ltv_cac_ratio: number | null;
    ratio_undefined: boolean;
    clears_benchmark: boolean | null;
  }[];
  reallocation: {
    shift_amount?: number;
    from_channels?: string[];
    to_channels?: string[];
    net_profit_change?: number;
    net_revenue_change?: number;
    basis?: string;
    status?: string;
    reason?: string;
  };
}

export interface ForecastData {
  method: string;
  label: string;
  selected_by: string;
  months: { month: string; forecast_revenue: number }[];
  total: number;
  last_actual_month: string;
  diagnostics: {
    available: boolean;
    slope_per_month?: number;
    p_value?: number;
    significant?: boolean;
    months_until_zero?: number | null;
    caveat?: string | null;
  };
}

export interface Snapshot {
  as_of: string | null;
  params_hash: string;
  capabilities: Record<string, boolean>;
  quality: {
    issues: {
      key: string;
      check: string;
      table: string;
      severity: "error" | "warning" | "info";
      issue_count: number;
      pct_of_rows: number;
      why_it_matters: string;
      production_handling: string;
    }[];
    rows_before: Record<string, number>;
    rows_after: Record<string, number>;
    total_flagged: number;
  };
  coverage: { months_of_history: number; max_date: string | null };
  computed_ms: number;
  modules: {
    marketing: Envelope<MarketingData>;
    customers: Envelope<unknown>;
    finance: Envelope<FinanceData>;
    experiments: Envelope<unknown>;
    forecast: Envelope<ForecastData>;
  };
}
