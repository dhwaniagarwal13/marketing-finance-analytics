"""
Phase 0 — freeze the truth.

Captures every value the current analysis produces into `expected.json`, so the
Phase 1 refactor into `analytics/` can be proven numerically faithful.

Two sources, both executed rather than retranscribed:

1. `src/generate_report.py` — imported and called directly.
2. `notebooks/01..06` — the code cells are read out of the .ipynb JSON and
   exec'd in a fresh namespace. Nothing is re-implemented here, so the captured
   numbers are exactly what the notebooks compute.

Plotting is neutralized (Agg backend, `save_fig` stubbed, `Figure.show` stubbed)
because rendering is slow (kaleido spawns headless Chromium) and irrelevant to
the numbers.

Usage:  python tests/golden/capture_golden.py
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import sys
import traceback
from datetime import date, datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
NOTEBOOKS = ROOT / "notebooks"
OUT_PATH = Path(__file__).resolve().parent / "expected.json"

# DataFrames larger than this are summarized rather than dumped row-by-row, so
# expected.json stays reviewable. The summary still pins every numeric column.
MAX_ROWS_VERBATIM = 200
# Significant digits, not decimal places: values here span 1e-3 (rates) to 1e6
# (revenue), so a fixed decimal place would destroy precision on the small ones.
# 12 of float64's ~15-17 digits keeps last-bit noise out without losing signal.
FLOAT_SIGDIGITS = 12

sys.path.insert(0, str(SRC))


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------
def _round(x: float) -> float:
    """Round to significant digits to kill last-bit float noise without hiding real changes."""
    if x is None:
        return None
    x = float(x)
    if np.isnan(x) or np.isinf(x):
        return str(x)
    return float(f"{x:.{FLOAT_SIGDIGITS}g}")


def _frame_hash(df: pd.DataFrame) -> str:
    try:
        return hashlib.sha256(
            pd.util.hash_pandas_object(df, index=True).values.tobytes()
        ).hexdigest()[:16]
    except Exception:
        return "unhashable"


def _numeric_summary(df: pd.DataFrame) -> dict:
    out = {}
    for col in df.columns:
        s = df[col]
        if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
            out[str(col)] = {
                "sum": _round(s.sum()),
                "mean": _round(s.mean()),
                "min": _round(s.min()),
                "max": _round(s.max()),
                "nulls": int(s.isna().sum()),
            }
        elif pd.api.types.is_bool_dtype(s):
            out[str(col)] = {"true": int(s.sum()), "nulls": int(s.isna().sum())}
        else:
            out[str(col)] = {"nunique": int(s.nunique(dropna=True)),
                             "nulls": int(s.isna().sum())}
    return out


def encode(obj, _depth=0):
    """Convert an arbitrary analysis value into stable, diffable JSON."""
    if _depth > 6:
        return "<max-depth>"

    if obj is None or isinstance(obj, (bool, str)):
        return obj
    if isinstance(obj, (int, np.integer)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        return _round(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (pd.Timestamp, datetime, date)):
        return str(obj)
    if isinstance(obj, pd.Period):
        return str(obj)
    if isinstance(obj, pd.Timedelta):
        return str(obj)

    if isinstance(obj, pd.Series):
        s = obj
        if len(s) <= MAX_ROWS_VERBATIM:
            return {
                "_type": "Series", "name": str(s.name), "dtype": str(s.dtype),
                "len": int(len(s)),
                "values": {str(k): encode(v, _depth + 1) for k, v in s.items()},
            }
        return {
            "_type": "Series", "name": str(s.name), "dtype": str(s.dtype),
            "len": int(len(s)), "summary": _numeric_summary(s.to_frame("v")).get("v"),
            "head": {str(k): encode(v, _depth + 1) for k, v in s.head(10).items()},
        }

    if isinstance(obj, pd.DataFrame):
        df = obj
        base = {
            "_type": "DataFrame",
            "shape": list(df.shape),
            "columns": [str(c) for c in df.columns],
            "dtypes": {str(c): str(t) for c, t in df.dtypes.items()},
            "hash": _frame_hash(df),
        }
        if len(df) <= MAX_ROWS_VERBATIM:
            base["index"] = [str(i) for i in df.index]
            base["records"] = [
                {str(k): encode(v, _depth + 1) for k, v in row.items()}
                for row in df.to_dict(orient="records")
            ]
        else:
            base["summary"] = _numeric_summary(df)
        return base

    if isinstance(obj, np.ndarray):
        if obj.size <= MAX_ROWS_VERBATIM:
            return [encode(v, _depth + 1) for v in obj.tolist()]
        return {"_type": "ndarray", "shape": list(obj.shape),
                "sum": _round(np.nansum(obj)), "mean": _round(np.nanmean(obj))}

    if isinstance(obj, dict):
        return {str(k): encode(v, _depth + 1) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        seq = list(obj)
        if len(seq) <= MAX_ROWS_VERBATIM:
            return [encode(v, _depth + 1) for v in seq]
        return {"_type": "seq", "len": len(seq),
                "head": [encode(v, _depth + 1) for v in seq[:10]]}

    return None  # not a value we can meaningfully freeze


# Values that are not analysis results and would add churn to the diff.
SKIP_NAMES = {
    "In", "Out", "exit", "quit", "get_ipython", "display", "json", "sys", "os",
    "Path", "np", "pd", "plt", "sns", "go", "px", "pio", "u", "utils", "warnings",
    "stats", "ARIMA", "proportions_ztest", "confint_proportions_2indep",
    "make_subplots", "matplotlib", "seaborn", "plotly", "statsmodels", "scipy",
}


def is_capturable(name: str, value) -> bool:
    if name.startswith("_") or name in SKIP_NAMES:
        return False
    if callable(value) or isinstance(value, type):
        return False
    mod = type(value).__module__ or ""
    if mod.startswith(("matplotlib", "seaborn", "plotly", "IPython")):
        return False
    return isinstance(
        value,
        (int, float, bool, str, np.integer, np.floating, np.bool_, np.ndarray,
         list, tuple, set, dict, pd.Series, pd.DataFrame, pd.Timestamp,
         pd.Period, pd.Timedelta, datetime, date),
    )


# ---------------------------------------------------------------------------
# Notebook execution
# ---------------------------------------------------------------------------
def notebook_source(path: Path) -> str:
    """Concatenate a notebook's code cells, dropping IPython magics."""
    nb = json.loads(path.read_text(encoding="utf-8"))
    chunks = []
    for cell in nb.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        lines = [
            ln for ln in cell.get("source", [])
            if not ln.lstrip().startswith(("%", "!", "?"))
        ]
        if lines:
            chunks.append("".join(lines))
    return "\n\n".join(chunks)


def neutralize_plotting():
    """Stub every rendering path so capture is fast and headless."""
    import plotly.graph_objects as go
    import plotly.io as pio

    import utils as u

    u.save_fig = lambda *a, **k: None
    go.Figure.show = lambda self, *a, **k: None
    pio.show = lambda *a, **k: None
    plt.show = lambda *a, **k: None


def run_notebook(path: Path) -> dict:
    """Exec a notebook's code in a fresh namespace; return its capturable values."""
    src = notebook_source(path)
    ns: dict = {
        "__name__": "__nb__",
        "__file__": str(path),
        "display": lambda *a, **k: None,
    }
    prev_cwd = Path.cwd()
    os.chdir(NOTEBOOKS)  # notebooks resolve src/ via Path.cwd().parent
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            exec(compile(src, str(path), "exec"), ns)
    finally:
        os.chdir(prev_cwd)
        plt.close("all")

    return {k: encode(v) for k, v in sorted(ns.items()) if is_capturable(k, v)}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    golden: dict = {
        "_meta": {
            "captured_at": datetime.now().isoformat(timespec="seconds"),
            "python": sys.version.split()[0],
            "pandas": pd.__version__,
            "numpy": np.__version__,
            "note": "Phase 0 baseline. Frozen as-is, including the known "
                    "forecast-fits-noise defect (see task #2).",
        }
    }

    print("=" * 68)
    print("src/generate_report.py")
    print("=" * 68)
    import generate_report as gr

    neutralize_plotting()

    campaigns, customers, transactions, ab_test = gr.load_data()
    profitability = gr.compute_channel_profitability(campaigns, customers, transactions)
    golden["generate_report"] = {
        "load_data": {
            "campaigns": encode(campaigns), "customers": encode(customers),
            "transactions": encode(transactions), "ab_test": encode(ab_test),
        },
        "compute_kpis": encode(gr.compute_kpis(campaigns, customers, transactions)),
        "compute_channel_profitability": encode(profitability),
        "compute_budget_reallocation": encode(gr.compute_budget_reallocation(profitability)),
        "compute_ab_test": encode(gr.compute_ab_test(ab_test)),
        "compute_forecast": encode(gr.compute_forecast(campaigns)),
    }
    for k in golden["generate_report"]:
        print(f"  captured {k}")

    failures = []
    for nb_path in sorted(NOTEBOOKS.glob("0*.ipynb")):
        print()
        print("=" * 68)
        print(nb_path.name)
        print("=" * 68)
        try:
            values = run_notebook(nb_path)
            golden[nb_path.stem] = values
            print(f"  captured {len(values)} values")
        except Exception:
            failures.append(nb_path.name)
            print("  FAILED:")
            traceback.print_exc()

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(golden, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )

    print()
    print("=" * 68)
    size_kb = OUT_PATH.stat().st_size / 1024
    print(f"Wrote {OUT_PATH.relative_to(ROOT)} ({size_kb:,.0f} KB)")
    if failures:
        print(f"INCOMPLETE — these notebooks failed: {', '.join(failures)}")
        return 1
    print("All sources captured.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
