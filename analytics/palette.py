"""
The project's colour system, as pure data.

Lifted verbatim out of `src/utils.py` so it can be imported by the API and
emitted to the frontend without dragging in matplotlib, seaborn, plotly or
kaleido — and without the import-time side effects that `utils` performs
(creating `reports/figures/`, mutating `plotly.io.templates.default`).

Nothing in this module executes anything. `src/utils.py` re-exports it, so
the notebooks keep working unchanged.

Accessibility constraints these values carry (validated against the `#fcfcfb`
surface) are documented in `CONTRAST_VS_SURFACE` below — read that before
using a hue for a thin mark.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Categorical / sequential / diverging ramps
# ---------------------------------------------------------------------------
CATEGORICAL: list[str] = [
    "#2a78d6", "#eb6834", "#1baf7a", "#eda100",
    "#e87ba4", "#008300", "#4a3aa7", "#e34948",
]

# Dark mode is *selected*, not flipped. Inverting the light hues fails the dark
# lightness band on four of eight slots; these are the same eight hues re-stepped
# for the dark surface and validated as a set (worst adjacent CVD dE 8.4, all
# eight clear 3:1 — dark actually has better contrast than light here).
CATEGORICAL_DARK: list[str] = [
    "#3987e5", "#d95926", "#199e70", "#c98500",
    "#d55181", "#008300", "#9085e9", "#e66767",
]

SEQUENTIAL_BLUE: list[str] = ["#cde2fb", "#9ec5f4", "#5598e7", "#2a78d6", "#184f95"]

# Full ramp for continuous encoding (the cohort heatmap). The lightest steps are
# only legal for sequential magnitude, where near-surface means "near zero"; an
# ordinal ramp must start no lighter than #86b6ef on light.
SEQUENTIAL_BLUE_FULL: list[str] = [
    "#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec",
    "#5598e7", "#3987e5", "#2a78d6", "#256abf", "#1c5cab",
    "#184f95", "#104281", "#0d366b",
]

DIVERGING: list[str] = ["#e34948", "#f0efec", "#2a78d6"]  # red -> neutral -> blue
DIVERGING_DARK: list[str] = ["#e66767", "#383835", "#3987e5"]

# Status is fixed and never themed — a status colour must never impersonate a
# series. On light, warning and serious are sub-3:1 by design; the icon + label
# pairing is the mitigation, so status never rides on colour alone.
STATUS: dict[str, str] = {
    "good": "#0ca30c",
    "warning": "#fab219",
    "serious": "#ec835a",
    "critical": "#d03b3b",
}

CHROME: dict[str, str] = {
    "surface": "#fcfcfb",
    "page": "#f9f9f7",
    "primary_ink": "#0b0b0b",
    "secondary_ink": "#52514e",
    "muted": "#898781",
    "gridline": "#e1e0d9",
    "baseline": "#c3c2b7",
    "success_text": "#006300",
    "border": "rgba(11,11,11,0.10)",
}

CHROME_DARK: dict[str, str] = {
    "surface": "#1a1a19",
    "page": "#0d0d0d",
    "primary_ink": "#ffffff",
    "secondary_ink": "#c3c2b7",
    "muted": "#898781",
    "gridline": "#2c2c2a",
    "baseline": "#383835",
    "success_text": "#0ca30c",
    "border": "rgba(255,255,255,0.10)",
}

# ---------------------------------------------------------------------------
# Channel identity
# ---------------------------------------------------------------------------
# Order is load-bearing: it fixes each channel's hue. Never reorder, and never
# assign colours by position in a *currently present* channel list — TikTok
# launches 2024-07-01, so under the replay cursor a position-based scheme would
# repaint every channel the moment TikTok appears.
CHANNEL_COLOR_ORDER: list[str] = [
    "Google Ads", "Facebook", "Instagram", "Email",
    "Affiliate", "TikTok", "Organic",
]

CHANNEL_COLORS: dict[str, str] = dict(zip(CHANNEL_COLOR_ORDER, CATEGORICAL))
CHANNEL_COLORS_DARK: dict[str, str] = dict(zip(CHANNEL_COLOR_ORDER, CATEGORICAL_DARK))

# 7 known channels against 8 categorical tokens: exactly one spare. Uploaded
# datasets will exceed this, so anything rendering arbitrary channels must fold
# the overflow into a single "Other" bucket (see `resolve_channel_colors`).
OTHER_COLOR: str = CHROME["muted"]

# ---------------------------------------------------------------------------
# Accessibility
# ---------------------------------------------------------------------------
# WCAG contrast ratio of each categorical hue against CHROME["surface"].
# Three fall below the 3:1 non-text threshold. That is acceptable for solid
# fills (bars, cells) but NOT for thin marks — any chart relying on these hues
# must also carry direct value labels or a paired table, and 1-2px lines should
# use a darkened step instead.
CONTRAST_VS_SURFACE: dict[str, float] = {
    "#2a78d6": 4.28,
    "#eb6834": 3.29,
    "#1baf7a": 2.74,   # below 3:1
    "#eda100": 2.11,   # below 3:1
    "#e87ba4": 2.62,   # below 3:1
    "#008300": 4.63,
    "#4a3aa7": 9.24,
    "#e34948": 3.85,
}

LOW_CONTRAST_HUES: list[str] = [
    hue for hue, ratio in CONTRAST_VS_SURFACE.items() if ratio < 3.0
]

# Channels whose light-mode hue is sub-3:1. Any chart drawing these must carry
# direct value labels or a paired table view — the relief is required, not
# optional, and thin marks (1-2px lines) make it worse than solid fills do.
LOW_CONTRAST_CHANNELS: list[str] = [
    name for name, hue in CHANNEL_COLORS.items() if hue in LOW_CONTRAST_HUES
]

# Forms that compare every series against every other (scatter, bubble) cannot
# use all eight slots: past the third, adjacent-pair validation no longer holds.
# Bars, lines and stacks compare neighbours only and are fine with all eight.
MAX_SERIES_ALL_PAIRS = 3


def resolve_channel_colors(channels: list[str]) -> dict[str, str]:
    """
    Map arbitrary channel names to hues, stably.

    Known channels keep their fixed identity colour. Unknown ones take the
    remaining categorical tokens in sorted order — sorted, not first-seen, so
    the mapping depends only on the *set* of channels and never shifts when a
    new channel appears mid-stream or a filter changes. Anything past the
    palette's capacity collapses to a single muted "Other".
    """
    resolved: dict[str, str] = {}
    used = set()

    for name in channels:
        if name in CHANNEL_COLORS:
            resolved[name] = CHANNEL_COLORS[name]
            used.add(CHANNEL_COLORS[name])

    spare = [c for c in CATEGORICAL if c not in used]
    for name in sorted(n for n in channels if n not in resolved):
        if spare:
            resolved[name] = spare.pop(0)
        else:
            resolved[name] = OTHER_COLOR

    return resolved


def as_theme_dict() -> dict:
    """The payload served at `GET /api/theme` and emitted to `theme.generated.ts`."""
    return {
        "categorical": CATEGORICAL,
        "sequential_blue": SEQUENTIAL_BLUE,
        "diverging": DIVERGING,
        "status": STATUS,
        "chrome": CHROME,
        "channel_colors": CHANNEL_COLORS,
        "channel_order": CHANNEL_COLOR_ORDER,
        "other_color": OTHER_COLOR,
        "contrast_vs_surface": CONTRAST_VS_SURFACE,
        "low_contrast_hues": LOW_CONTRAST_HUES,
        "dark": {
            "categorical": CATEGORICAL_DARK,
            "channel_colors": CHANNEL_COLORS_DARK,
            "diverging": DIVERGING_DARK,
            "chrome": CHROME_DARK,
        },
        "sequential_blue_full": SEQUENTIAL_BLUE_FULL,
        "low_contrast_channels": LOW_CONTRAST_CHANNELS,
        "max_series_all_pairs": MAX_SERIES_ALL_PAIRS,
    }
