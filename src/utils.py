"""
Shared KPI formulas and chart styling for the Marketing + Finance Analytics
case study. Imported by every notebook so calculations and visuals stay
consistent across the six-chapter analysis.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import seaborn as sns

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_RAW = PROJECT_ROOT / "data" / "raw"
DATA_DB = PROJECT_ROOT / "data" / "marketing_finance.db"
FIGURES_DIR = PROJECT_ROOT / "reports" / "figures"
FIGURES_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Palette (validated categorical / sequential / diverging / chrome roles)
# ---------------------------------------------------------------------------
CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100",
               "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
SEQUENTIAL_BLUE = ["#cde2fb", "#9ec5f4", "#5598e7", "#2a78d6", "#184f95"]
DIVERGING = ["#e34948", "#f0efec", "#2a78d6"]          # red -> neutral -> blue
STATUS = {"good": "#0ca30c", "warning": "#fab219",
          "serious": "#ec835a", "critical": "#d03b3b"}

CHROME = {
    "surface": "#fcfcfb",
    "primary_ink": "#0b0b0b",
    "secondary_ink": "#52514e",
    "muted": "#898781",
    "gridline": "#e1e0d9",
    "baseline": "#c3c2b7",
}

CHANNEL_COLOR_ORDER = ["Google Ads", "Facebook", "Instagram", "Email",
                        "Affiliate", "TikTok", "Organic"]
CHANNEL_COLORS = dict(zip(CHANNEL_COLOR_ORDER, CATEGORICAL))


def apply_chart_theme():
    """Consistent matplotlib/seaborn theme: thin marks, recessive grid, no chart-junk."""
    sns.set_theme(style="white", rc={
        "figure.facecolor": CHROME["surface"],
        "axes.facecolor": CHROME["surface"],
        "axes.edgecolor": CHROME["baseline"],
        "axes.labelcolor": CHROME["secondary_ink"],
        "text.color": CHROME["primary_ink"],
        "xtick.color": CHROME["muted"],
        "ytick.color": CHROME["muted"],
        "grid.color": CHROME["gridline"],
        "axes.grid": True,
        "axes.grid.axis": "y",
        "grid.linewidth": 0.8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.spines.left": False,
        "font.family": "sans-serif",
        "font.size": 11,
    })
    plt.rcParams["axes.prop_cycle"] = plt.cycler(color=CATEGORICAL)


PLOTLY_TEMPLATE = go.layout.Template(
    layout=go.Layout(
        colorway=CATEGORICAL,
        paper_bgcolor=CHROME["surface"],
        plot_bgcolor=CHROME["surface"],
        font=dict(family="system-ui, -apple-system, Segoe UI, sans-serif",
                  color=CHROME["primary_ink"], size=12),
        xaxis=dict(gridcolor=CHROME["gridline"], zerolinecolor=CHROME["baseline"],
                    linecolor=CHROME["baseline"]),
        yaxis=dict(gridcolor=CHROME["gridline"], zerolinecolor=CHROME["baseline"],
                    linecolor=CHROME["baseline"]),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
    )
)
pio.templates["case_study"] = PLOTLY_TEMPLATE
pio.templates.default = "case_study"


def save_fig(fig, name: str, is_plotly: bool = False, width: int = 1200, height: int = 700):
    """Export a chart to reports/figures/<name>.png for reuse in the PDF report and README."""
    out_path = FIGURES_DIR / f"{name}.png"
    if is_plotly:
        fig.write_image(str(out_path), width=width, height=height, scale=2)
    else:
        fig.savefig(out_path, dpi=200, bbox_inches="tight", facecolor=CHROME["surface"])
    return out_path


# ---------------------------------------------------------------------------
# KPI formulas
# ---------------------------------------------------------------------------
def ctr(clicks, impressions):
    """Click-through rate: clicks / impressions."""
    return clicks / impressions.replace(0, np.nan)


def cvr(conversions, clicks):
    """Conversion rate: conversions / clicks."""
    return conversions / clicks.replace(0, np.nan)


def cpc(spend, clicks):
    """Cost per click: spend / clicks."""
    return spend / clicks.replace(0, np.nan)


def cpa(spend, conversions):
    """Cost per acquisition/conversion: spend / conversions."""
    return spend / conversions.replace(0, np.nan)


def roas(revenue, spend):
    """Return on ad spend: revenue / spend."""
    return revenue / spend.replace(0, np.nan)


def roi(profit, spend):
    """Return on investment: (profit - spend) / spend."""
    return (profit - spend) / spend.replace(0, np.nan)


def cac(spend_by_channel: pd.Series, new_customers_by_channel: pd.Series) -> pd.Series:
    """Customer acquisition cost per channel: marketing spend / new customers acquired."""
    return spend_by_channel / new_customers_by_channel.replace(0, np.nan)


def contribution_margin(revenue, variable_cost):
    """Contribution margin ratio: (revenue - variable_cost) / revenue."""
    return (revenue - variable_cost) / revenue.replace(0, np.nan)


def ltv_simple(avg_order_value, purchase_frequency, gross_margin, avg_lifespan_years):
    """
    Simplified customer lifetime value:
    LTV = avg_order_value * purchase_frequency * gross_margin * avg_lifespan_years
    """
    return avg_order_value * purchase_frequency * gross_margin * avg_lifespan_years


def retention_rate(active_end, active_start):
    """Period-over-period retention rate: customers active at end / customers active at start."""
    return active_end / active_start.replace(0, np.nan)


def fmt_currency(x, decimals=0):
    return f"${x:,.{decimals}f}"


def fmt_pct(x, decimals=1):
    return f"{x * 100:.{decimals}f}%"
