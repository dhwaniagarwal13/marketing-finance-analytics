"""
Revenue forecasting — notebook 05, unified.

`select_and_forecast()` is deliberately the *only* forecast path. NB05 ran a
three-method backtest and picked a winner, but NB06 and the PDF then refit a
linear trend directly, ignoring that choice. They agree today only because
Linear Trend happens to win; the moment ARIMA wins, the chapter and the report
would disagree silently.

Known limitation, tracked for Phase 5: on this dataset the fitted trend is
driven by how many of the 42 campaigns happen to overlap in a given month
rather than by any real growth or decline — `generate_campaign_daily` contains
no time-trend term at all. `trend_diagnostics()` reports that honestly; the
point forecast itself is still the notebook's, unchanged.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from scipy import stats

from .config import DEFAULTS, AnalysisParams
from .errors import InsufficientData

METHOD_LABELS = {
    "moving_average": "Moving Average",
    "linear_trend": "Linear Trend",
    "arima": "ARIMA(1,1,1)",
}

# Below this many observations an ARIMA(1,1,1) fit does not converge usefully.
MIN_ARIMA_POINTS = 8
MIN_TREND_POINTS = 3


def rmse(actual, pred) -> float:
    return float(np.sqrt(np.mean((np.asarray(actual) - np.asarray(pred)) ** 2)))


def mae(actual, pred) -> float:
    return float(np.mean(np.abs(np.asarray(actual) - np.asarray(pred))))


def _fit_predict(method: str, series: pd.Series, steps: int,
                 params: AnalysisParams) -> np.ndarray | None:
    """Fit one method and project `steps` ahead. None means 'not applicable here'."""
    values = np.asarray(series.values, dtype="float64")

    if method == "moving_average":
        if len(values) < 1:
            return None
        return np.repeat(values[-params.ma_window:].mean(), steps)

    if method == "linear_trend":
        if len(values) < MIN_TREND_POINTS:
            return None
        x = np.arange(len(values))
        slope, intercept = np.polyfit(x, values, 1)
        return slope * np.arange(len(values), len(values) + steps) + intercept

    if method == "arima":
        if len(values) < MIN_ARIMA_POINTS:
            return None
        try:
            from statsmodels.tsa.arima.model import ARIMA

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                model = ARIMA(values, order=params.arima_order).fit()
            return np.asarray(model.forecast(steps=steps), dtype="float64")
        except Exception:
            return None  # non-convergence is a reason to skip, not to fail

    raise ValueError(f"unknown forecast method {method!r}")


def backtest(monthly: pd.Series, params: AnalysisParams = DEFAULTS) -> dict:
    """Hold out the last `holdout_months` and rank each method by RMSE."""
    holdout = params.holdout_months
    if len(monthly) < holdout + MIN_TREND_POINTS:
        raise InsufficientData(
            "forecast_backtest",
            need=f"{holdout + MIN_TREND_POINTS} months",
            have=f"{len(monthly)}",
        )

    train, test = monthly.iloc[:-holdout], monthly.iloc[-holdout:]

    results: dict[str, dict] = {}
    skipped: list[str] = []
    for method in params.forecast_methods:
        pred = _fit_predict(method, train, holdout, params)
        if pred is None:
            skipped.append(METHOD_LABELS[method])
            continue
        results[method] = {
            "label": METHOD_LABELS[method],
            "forecast": [float(v) for v in pred],
            "rmse": rmse(test.values, pred),
            "mae": mae(test.values, pred),
        }

    if not results:
        raise InsufficientData(
            "forecast_backtest", need="at least one applicable method",
            have=f"{len(monthly)} months",
        )

    ranked = sorted(results, key=lambda m: results[m]["rmse"])
    return {
        "results": results,
        "ranked": ranked,
        "best_method": ranked[0],
        "best_label": METHOD_LABELS[ranked[0]],
        "train_months": int(len(train)),
        "test_months": int(len(test)),
        "test_actual": [float(v) for v in test.values],
        "test_index": [str(i) for i in test.index],
        "methods_skipped": skipped,
    }


def trend_diagnostics(monthly: pd.Series) -> dict:
    """
    Is the fitted trend distinguishable from noise?

    Reported alongside the forecast rather than gating it. On the demo dataset
    the answer is no, and the resulting extrapolation reaches zero within a
    year — which the UI needs to be able to say out loud.
    """
    values = np.asarray(monthly.values, dtype="float64")
    if len(values) < MIN_TREND_POINTS:
        return {"available": False}

    x = np.arange(len(values))
    reg = stats.linregress(x, values)

    months_to_zero = None
    if reg.slope < 0 and reg.intercept > 0:
        months_to_zero = float(-reg.intercept / reg.slope - len(values))

    return {
        "available": True,
        "slope_per_month": float(reg.slope),
        "p_value": float(reg.pvalue),
        "r_squared": float(reg.rvalue ** 2),
        "significant": bool(reg.pvalue < 0.05),
        "months_until_zero": months_to_zero,
        "caveat": (
            None if reg.pvalue < 0.05 else
            "The fitted trend is not statistically distinguishable from zero; "
            "treat the projection as a level estimate, not a direction."
        ),
    }


def select_and_forecast(monthly: pd.Series, params: AnalysisParams = DEFAULTS) -> dict:
    """
    Backtest, pick the winner, refit it on the full series, project forward.

    The single forecast path — NB05, NB06 and the PDF all route through here so
    they cannot diverge.
    """
    bt = backtest(monthly, params)
    method = bt["best_method"]
    horizon = params.forecast_horizon

    pred = _fit_predict(method, monthly, horizon, params)
    if pred is None:
        raise InsufficientData(
            "forecast", need=f"enough history for {METHOD_LABELS[method]}",
            have=f"{len(monthly)} months",
        )

    last = monthly.index[-1]
    period = last if isinstance(last, pd.Period) else pd.Period(last, freq="M")
    future = pd.period_range(period + 1, periods=horizon, freq="M")

    return {
        "method": method,
        "label": METHOD_LABELS[method],
        "selected_by": f"lowest holdout RMSE over {bt['test_months']} months",
        "horizon_months": horizon,
        "months": [
            {"month": str(p), "forecast_revenue": float(v)}
            for p, v in zip(future, pred)
        ],
        "total": float(np.sum(pred)),
        "history_months": int(len(monthly)),
        "last_actual_month": str(period),
        "backtest": bt,
        "diagnostics": trend_diagnostics(monthly),
    }


def build(bundle, params: AnalysisParams = DEFAULTS) -> dict:
    from .errors import require
    from .marketing import monthly_revenue

    require(bundle, "forecast", "campaigns")
    monthly = monthly_revenue(bundle.campaigns, params)
    monthly.index = monthly.index.to_period("M")
    return select_and_forecast(monthly, params)
