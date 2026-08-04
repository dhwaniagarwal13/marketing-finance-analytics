"""
Keeps `web/src/theme.generated.ts` honest.

Colour lives in `analytics/palette.py` because the notebooks, the PDF and the
web app all draw from it. The frontend gets a generated copy rather than a
runtime fetch, so a chart never renders before its palette arrives — but a
generated copy can go stale, and a stale palette is invisible until someone
notices two channels sharing a hue.

Also asserts the accessibility facts the charts depend on, so a future palette
edit that quietly breaks them fails here rather than in review.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from analytics.palette import (
    CATEGORICAL,
    CATEGORICAL_DARK,
    CHANNEL_COLOR_ORDER,
    CHANNEL_COLORS,
    LOW_CONTRAST_CHANNELS,
)


@pytest.fixture(scope="module")
def generated(project_root) -> str:
    path = project_root / "web" / "src" / "theme.generated.ts"
    if not path.exists():
        pytest.skip("theme not generated — run python scripts/generate_theme.py")
    return path.read_text(encoding="utf-8")


def test_theme_file_is_current(project_root):
    """Regenerating must be a no-op. If this fails, run the generator."""
    result = subprocess.run(
        [sys.executable, "scripts/generate_theme.py"],
        cwd=project_root, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "updated" not in result.stdout, (
        "theme.generated.ts was stale and has just been rewritten; commit the change"
    )


def test_every_hue_reaches_the_frontend(generated):
    for hue in CATEGORICAL:
        assert hue in generated, f"light hue {hue} missing from generated theme"
    for hue in CATEGORICAL_DARK:
        assert hue in generated, f"dark hue {hue} missing from generated theme"


def test_channel_identity_is_carried_over(generated):
    for channel in CHANNEL_COLOR_ORDER:
        assert channel in generated, f"channel {channel} missing from generated theme"


def test_generated_file_is_ascii(generated):
    """Read by Python, Node and a bundler, each with its own default encoding."""
    generated.encode("ascii")


# ---------------------------------------------------------------------------
# Accessibility facts the charts are built on
# ---------------------------------------------------------------------------
def test_low_contrast_channels_are_exactly_the_three_known_ones(generated):
    """
    Instagram, Email and Affiliate sit below 3:1 on the light surface.

    Charts drawing them must ship direct value labels or a table view. If this
    set ever changes, the charts' relief has to change with it.
    """
    assert set(LOW_CONTRAST_CHANNELS) == {"Instagram", "Email", "Affiliate"}
    assert '"lowContrastChannels": ["Instagram", "Email", "Affiliate"]' in generated


def test_channel_colours_are_unique():
    """Two channels sharing a hue would make the legend meaningless."""
    assert len(set(CHANNEL_COLORS.values())) == len(CHANNEL_COLORS)


def test_dark_is_a_selected_palette_not_an_inversion():
    """
    Six of the eight dark steps differ from their light counterparts.

    Flipping the light palette onto a dark surface fails the dark lightness
    band on four slots; these steps were chosen and validated for that surface.
    """
    differing = sum(1 for a, b in zip(CATEGORICAL, CATEGORICAL_DARK) if a != b)
    assert differing >= 6, "dark palette looks like a copy of the light one"


def test_channel_colour_order_is_stable():
    """
    Hue follows the entity, never its rank.

    TikTok has no rows before 2024-07-01, so under the replay cursor a
    position-based assignment would repaint every channel the tick it appears.
    """
    assert CHANNEL_COLOR_ORDER[0] == "Google Ads"
    assert CHANNEL_COLORS["Google Ads"] == CATEGORICAL[0]
    assert CHANNEL_COLORS["TikTok"] == CATEGORICAL[5]


def test_resolve_channel_colors_is_order_independent():
    """A different input order must not change any channel's hue."""
    from analytics.palette import resolve_channel_colors

    forward = resolve_channel_colors(["Google Ads", "Email", "NewChannel", "Other Co"])
    shuffled = resolve_channel_colors(["Other Co", "NewChannel", "Email", "Google Ads"])
    assert forward == shuffled
    assert forward["Google Ads"] == CHANNEL_COLORS["Google Ads"]


def test_unknown_channels_never_steal_a_known_hue():
    from analytics.palette import resolve_channel_colors

    resolved = resolve_channel_colors(["Google Ads", "Reddit", "Snapchat"])
    assert resolved["Google Ads"] == CHANNEL_COLORS["Google Ads"]
    assert resolved["Reddit"] != resolved["Snapchat"]
    assert resolved["Reddit"] not in {CHANNEL_COLORS["Google Ads"]}


def test_overflow_folds_to_other_rather_than_generating_a_hue():
    """A ninth categorical colour is never invented — it folds to muted."""
    from analytics.palette import OTHER_COLOR, resolve_channel_colors

    many = [f"Channel {i}" for i in range(12)]
    resolved = resolve_channel_colors(many)
    assert list(resolved.values()).count(OTHER_COLOR) >= 4
