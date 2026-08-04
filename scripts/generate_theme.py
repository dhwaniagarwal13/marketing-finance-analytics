"""
Emit `web/src/theme.generated.ts` from `analytics/palette.py`.

One source of truth for colour. The file is generated and checked in, rather
than fetched at runtime, so a chart never renders before its palette arrives and
there is no build-order coupling between the Python and Node stages of the
Docker build. `tests/test_theme_sync.py` fails if the two drift.

    python scripts/generate_theme.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from analytics.palette import as_theme_dict  # noqa: E402

OUT_PATH = ROOT / "web" / "src" / "theme.generated.ts"

# ASCII only: this file is read by Node, Python and a bundler, each with its own
# idea of the default encoding.
HEADER = """\
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
"""

# Dicts whose *keys* are identifiers and should be camelised. Everything else
# keeps its keys verbatim - channelColors is keyed by channel name ("Google
# Ads"), which must survive untouched.
CAMEL_KEYED = {"chrome"}


def ts_literal(value, indent: int = 0) -> str:
    """Render Python data as a TypeScript literal with `as const`-friendly shape."""
    pad = "  " * indent
    inner = "  " * (indent + 1)

    if isinstance(value, dict):
        if not value:
            return "{}"
        lines = [f"{inner}{json.dumps(k)}: {ts_literal(v, indent + 1)}," for k, v in value.items()]
        return "{\n" + "\n".join(lines) + f"\n{pad}}}"

    if isinstance(value, list):
        if not value:
            return "[]"
        if all(isinstance(v, str) for v in value):
            return "[" + ", ".join(json.dumps(v) for v in value) + "]"
        lines = [f"{inner}{ts_literal(v, indent + 1)}," for v in value]
        return "[\n" + "\n".join(lines) + f"\n{pad}]"

    return json.dumps(value)


def to_camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(part.title() for part in rest)


def camelise(node: dict) -> dict:
    """Camelise this dict's keys, recursing only into dicts whose keys are identifiers."""
    out = {}
    for key, value in node.items():
        new_key = to_camel(key)
        if isinstance(value, dict) and (key in CAMEL_KEYED or key == "dark"):
            value = camelise(value)
        out[new_key] = value
    return out


def render() -> str:
    body = ts_literal(camelise(as_theme_dict()))
    return (
        f"{HEADER}\nexport const theme = {body} as const;\n\n"
        "export type ChannelName = keyof typeof theme.channelColors;\n\n"
        "/** Hue for a channel in the active mode, falling back to muted for unknowns. */\n"
        "export function channelColor(name: string, dark = false): string {\n"
        "  const map = dark ? theme.dark.channelColors : theme.channelColors;\n"
        "  return (map as Record<string, string>)[name] ?? theme.otherColor;\n"
        "}\n\n"
        "/** True when this channel's hue needs direct labels or a table view. */\n"
        "export function needsLabelRelief(name: string, dark = false): boolean {\n"
        "  return !dark && (theme.lowContrastChannels as readonly string[]).includes(name);\n"
        "}\n"
    )


def main() -> int:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    content = render()
    previous = OUT_PATH.read_text(encoding="utf-8") if OUT_PATH.exists() else None
    OUT_PATH.write_text(content, encoding="utf-8")

    verb = "unchanged" if previous == content else ("updated" if previous else "created")
    print(f"{verb}: {OUT_PATH.relative_to(ROOT)} ({len(content)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
