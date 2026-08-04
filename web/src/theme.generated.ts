// GENERATED FILE - do not edit.
// Source: analytics/palette.py   Regenerate: python scripts/generate_theme.py
//
// Colour lives in Python because the notebooks, the PDF report and this app all
// have to agree. tests/test_theme_sync.py fails if this file drifts from it.
//
// Accessibility constraints carried in this data, not just in review notes:
//   * lowContrastChannels - sub-3:1 on the light surface. Charts drawing these
//     MUST ship direct value labels or a table view. Not optional.
//   * maxSeriesAllPairs - scatter/bubble compare every series to every other,
//     which the full eight slots cannot clear. Bars and lines compare
//     neighbours only and are fine with all of them.

export const theme = {
  "categorical": ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"],
  "sequentialBlue": ["#cde2fb", "#9ec5f4", "#5598e7", "#2a78d6", "#184f95"],
  "diverging": ["#e34948", "#f0efec", "#2a78d6"],
  "status": {
    "good": "#0ca30c",
    "warning": "#fab219",
    "serious": "#ec835a",
    "critical": "#d03b3b",
  },
  "chrome": {
    "surface": "#fcfcfb",
    "page": "#f9f9f7",
    "primaryInk": "#0b0b0b",
    "secondaryInk": "#52514e",
    "muted": "#898781",
    "gridline": "#e1e0d9",
    "baseline": "#c3c2b7",
    "successText": "#006300",
    "border": "rgba(11,11,11,0.10)",
  },
  "channelColors": {
    "Google Ads": "#2a78d6",
    "Facebook": "#eb6834",
    "Instagram": "#1baf7a",
    "Email": "#eda100",
    "Affiliate": "#e87ba4",
    "TikTok": "#008300",
    "Organic": "#4a3aa7",
  },
  "channelOrder": ["Google Ads", "Facebook", "Instagram", "Email", "Affiliate", "TikTok", "Organic"],
  "otherColor": "#898781",
  "contrastVsSurface": {
    "#2a78d6": 4.28,
    "#eb6834": 3.29,
    "#1baf7a": 2.74,
    "#eda100": 2.11,
    "#e87ba4": 2.62,
    "#008300": 4.63,
    "#4a3aa7": 9.24,
    "#e34948": 3.85,
  },
  "lowContrastHues": ["#1baf7a", "#eda100", "#e87ba4"],
  "dark": {
    "categorical": ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"],
    "channelColors": {
      "Google Ads": "#3987e5",
      "Facebook": "#d95926",
      "Instagram": "#199e70",
      "Email": "#c98500",
      "Affiliate": "#d55181",
      "TikTok": "#008300",
      "Organic": "#9085e9",
    },
    "diverging": ["#e66767", "#383835", "#3987e5"],
    "chrome": {
      "surface": "#1a1a19",
      "page": "#0d0d0d",
      "primaryInk": "#ffffff",
      "secondaryInk": "#c3c2b7",
      "muted": "#898781",
      "gridline": "#2c2c2a",
      "baseline": "#383835",
      "successText": "#0ca30c",
      "border": "rgba(255,255,255,0.10)",
    },
  },
  "sequentialBlueFull": ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7", "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"],
  "lowContrastChannels": ["Instagram", "Email", "Affiliate"],
  "maxSeriesAllPairs": 3,
} as const;

export type ChannelName = keyof typeof theme.channelColors;

/** Hue for a channel in the active mode, falling back to muted for unknowns. */
export function channelColor(name: string, dark = false): string {
  const map = dark ? theme.dark.channelColors : theme.channelColors;
  return (map as Record<string, string>)[name] ?? theme.otherColor;
}

/** True when this channel's hue needs direct labels or a table view. */
export function needsLabelRelief(name: string, dark = false): boolean {
  return !dark && (theme.lowContrastChannels as readonly string[]).includes(name);
}
