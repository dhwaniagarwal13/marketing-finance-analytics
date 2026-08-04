"""
The analysis engine.

Pure, importable, side-effect free. Every function takes DataFrames and
parameters and returns values — nothing reads from a fixed path at import
time, nothing writes files, nothing mutates global plotting state.

That constraint is what lets the same code back the notebooks, the PDF report
and the web API without any of them being able to disagree.

Rendering lives outside this package: `src/utils.py` keeps the matplotlib /
seaborn / plotly theming for notebook use, and the frontend gets colour tokens
via `palette.as_theme_dict()`.
"""

from __future__ import annotations

from . import formulas, palette

__all__ = ["formulas", "palette"]
