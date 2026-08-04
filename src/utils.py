"""
Notebook-facing shim over the `analytics` engine.

The palette and the KPI formulas now live in `analytics/palette.py` and
`analytics/formulas.py` — pure data and pure functions, importable by the API
without pulling in matplotlib, seaborn, plotly or kaleido.

What stays here is everything that is *not* pure: the resolved project paths,
the `reports/figures/` directory creation, the matplotlib/seaborn theme, and
the mutation of `plotly.io.templates.default`. Those are genuinely useful in a
notebook and genuinely unwanted in a web process, so this is the boundary.

The public surface is unchanged, so `import utils as u` keeps working in all
six notebooks and in `src/generate_report.py` with no edits.

Removed: `ltv_simple` and `retention_rate`, which had no call sites.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import plotly.graph_objects as go
import plotly.io as pio
import seaborn as sns

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# The engine is a top-level package at the repo root; notebooks only put `src/`
# on the path, so make the root importable before reaching for it.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from analytics.formulas import (  # noqa: E402  (re-exported for notebooks)
    cac,
    contribution_margin,
    cpa,
    cpc,
    ctr,
    cvr,
    fmt_currency,
    fmt_pct,
    roas,
    roi,
    safe_divide,
)
from analytics.palette import (  # noqa: E402  (re-exported for notebooks)
    CATEGORICAL,
    CHANNEL_COLOR_ORDER,
    CHANNEL_COLORS,
    CHROME,
    DIVERGING,
    SEQUENTIAL_BLUE,
    STATUS,
)

__all__ = [
    "PROJECT_ROOT", "DATA_RAW", "DATA_DB", "FIGURES_DIR",
    "CATEGORICAL", "SEQUENTIAL_BLUE", "DIVERGING", "STATUS", "CHROME",
    "CHANNEL_COLOR_ORDER", "CHANNEL_COLORS", "PLOTLY_TEMPLATE",
    "apply_chart_theme", "save_fig",
    "ctr", "cvr", "cpc", "cpa", "roas", "roi", "cac", "contribution_margin",
    "safe_divide", "fmt_currency", "fmt_pct",
]

# ---------------------------------------------------------------------------
# Paths (side effect: creates reports/figures/ on import)
# ---------------------------------------------------------------------------
DATA_RAW = PROJECT_ROOT / "data" / "raw"
DATA_DB = PROJECT_ROOT / "data" / "marketing_finance.db"
FIGURES_DIR = PROJECT_ROOT / "reports" / "figures"
FIGURES_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Chart styling
# ---------------------------------------------------------------------------
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
