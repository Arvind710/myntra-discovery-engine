"""Chart helpers. Two rules, enforced here rather than remembered per chart.

1. COLOUR-BLIND SAFE palette (assignment guideline, FR-2.6).
2. `n` IS ALWAYS SHOWN. No chart renders a percentage without its
   denominator -- R-6, quantification illusion. A precise-looking share
   with no n reads as funnel truth.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# Okabe-Ito: designed for deuteranopia/protanopia/tritanopia.
PALETTE = ["#0072B2", "#E69F00", "#009E73", "#CC79A7",
           "#56B4E9", "#D55E00", "#F0E442", "#000000"]

MIN_N_RANKED = 30   # AR-12 / arch §9.4 -- below this, not a ranked claim
MIN_N_VISIBLE = 15  # below this, greyed with the count shown


def bar(df: pd.DataFrame, x: str, y: str, *, title: str, n_col: str | None = None,
        orientation: str = "v", height: int = 380) -> go.Figure:
    d = df.copy()
    colours = PALETTE * (len(d) // len(PALETTE) + 1)
    if n_col and n_col in d.columns:
        # Under-evidenced bars are greyed, never hidden: a code with no
        # evidence is a reportable result (AC-10), an invisible one is a hole.
        colours = ["#BBBBBB" if v < MIN_N_RANKED else PALETTE[0] for v in d[n_col]]
    fig = go.Figure(go.Bar(
        x=d[x] if orientation == "v" else d[y],
        y=d[y] if orientation == "v" else d[x],
        orientation=orientation,
        marker_color=colours,
        text=[f"n={v}" for v in d[n_col]] if n_col and n_col in d.columns else None,
        textposition="outside",
    ))
    total = int(d[n_col].sum()) if n_col and n_col in d.columns else None
    fig.update_layout(
        title=f"{title}" + (f"  (total n={total:,})" if total else ""),
        height=height, margin=dict(l=10, r=10, t=50, b=10),
        plot_bgcolor="rgba(0,0,0,0)", showlegend=False,
    )
    return fig


def timeline(df: pd.DataFrame, x: str, y: str, *, title: str) -> go.Figure:
    fig = px.line(df, x=x, y=y, markers=True, color_discrete_sequence=PALETTE)
    fig.update_layout(title=title, height=320, margin=dict(l=10, r=10, t=50, b=10),
                      plot_bgcolor="rgba(0,0,0,0)")
    return fig


def caption_n(n: int, authors: int | None = None) -> str:
    """The standard sample-size caption. EC-COL-9: '200 records' and
    '200 people' are different claims."""
    s = f"n = {n:,}"
    if authors is not None:
        s += f" from {authors:,} distinct authors"
        if n and authors:
            s += f" ({n / authors:.1f} records per author)"
    return s
