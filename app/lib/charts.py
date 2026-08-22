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


def journey(stage_rows, *, height: int = 200):
    """The four stages as one horizontal band, drawn to scale.

    NOT a funnel. A funnel implies each stage passes survivors to the next and
    that the widths are drop-off — neither is true here. These are shares of
    CONVERSATION, and two of the four stages are under-detected by construction
    because forgetting and a hard-to-scroll list produce no complaint. Drawing
    them as a tapering funnel would put a false claim in the most eye-catching
    element on the page.

    So: one bar, segments proportional to what people talk about, with the
    quiet stages labelled as quiet rather than made to look small and settled.
    """
    fig = go.Figure()
    total = sum(r["n"] for r in stage_rows) or 1
    for r in stage_rows:
        share = r["n"] / total
        fig.add_trace(go.Bar(
            x=[r["n"]], y=["conversation"], orientation="h",
            name=r["title"], marker_color=r["colour"],
            # Horizontal or not at all. Plotly rotates a label that will not fit
            # and IGNORES textangle=0 when it decides the segment is too narrow —
            # a 5% segment rendered its title vertically down a 40px column,
            # unreadable and worse than absent because it still draws the eye.
            # So the decision is made here rather than delegated: below 10% the
            # segment carries no text and the stage cards underneath carry its
            # numbers instead.
            text=[f"<b>{r['title']}</b><br>{share:.0%} · n={r['n']:,}"
                  if share >= 0.10 else ""],
            textposition="inside", insidetextanchor="middle", textangle=0,
            hovertemplate=f"<b>{r['title']}</b><br>{r['n']:,} records"
                          f"<br>{share:.1%} of coded conversation<extra></extra>",
        ))
    fig.update_layout(
        barmode="stack", height=height, showlegend=False,
        margin=dict(l=6, r=6, t=10, b=6),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(visible=False), yaxis=dict(visible=False),
        uniformtext=dict(mode="hide", minsize=10),
    )
    return fig


def contribution(df: pd.DataFrame, label_col: str, components: dict[str, str],
                 *, title: str, height: int = 420,
                 weights: dict[str, float] | None = None) -> go.Figure:
    """The opportunity score taken apart, one stacked bar per barrier.

    WHY A STACK AND NOT A TOTAL
    ---------------------------
    A single bar per barrier says which one won and nothing about why. The
    score is a mean of six stored components, so each component contributes a
    knowable slice of the total -- and the interesting reading is almost always
    in the slices. Price loses on one narrow slice (it cannot be fixed without
    a discount) despite the widest prevalence slice in the corpus; a total bar
    hides exactly that, which is the one thing a reader needs to argue with.

    `components` maps column name -> the plain label shown in the legend, in
    stacking order. Each column is scaled by its share of the total weight, so
    the bar length IS the score rather than merely proportional to it.

    `weights` re-scales the slices live. Passing the reader's slider settings
    makes one chart do the work of two: the ORDER answers "what wins" and the
    SLICES answer "why", and both move together when a weight is changed. With
    no weights the components are equally weighted, which is the baseline.
    """
    d = df.copy()
    w = weights or {c: 1.0 for c in components}
    total = sum(w.get(c, 0.0) for c in components) or 1.0
    fig = go.Figure()
    for i, (col, label) in enumerate(components.items()):
        fig.add_trace(go.Bar(
            y=d[label_col], x=d[col] * w.get(col, 0.0) / total, orientation="h",
            name=label, marker_color=PALETTE[i % len(PALETTE)],
            hovertemplate=f"<b>{label}</b><br>component %{{customdata:.2f}} of 1.0"
                          f"<br>adds %{{x:.3f}} to the score<extra></extra>",
            customdata=d[col],
        ))
    fig.update_layout(
        barmode="stack", title=title, height=height,
        margin=dict(l=10, r=10, t=50, b=70),
        plot_bgcolor="rgba(0,0,0,0)",
        # Below the plot, never above it: a horizontal legend at y>1 collides
        # with the title on a narrow window and the two render on top of each
        # other, which is how this chart first shipped.
        legend=dict(orientation="h", yanchor="top", y=-0.18, x=0, font=dict(size=11),
                    traceorder="normal"),
        # No axis title: it sits exactly where the legend has to go, and the
        # caption under the chart already says that bar length is the score.
        xaxis=dict(range=[0, 1]),
    )
    return fig


def attrition(labels: list[str], values: list[int], *, title: str,
              height: int = 260) -> go.Figure:
    """Records surviving each cut, one colour, longest at the top.

    Deliberately NOT `bar()`: that helper colours each bar differently because
    its bars are usually different categories. These four are the SAME quantity
    measured at four points, and four colours would say otherwise. It is also
    deliberately not a funnel shape — this is attrition of RECORDS under stated
    rules, which is a real filter, but the app elsewhere insists that nothing
    here is a user funnel, and a tapering polygon is the one shape that would
    undo that everywhere it appeared.
    """
    fig = go.Figure(go.Bar(
        x=values[::-1], y=labels[::-1], orientation="h",
        marker_color=PALETTE[0],
        text=[f"{v:,}" for v in values[::-1]], textposition="outside",
        hovertemplate="%{y}<br>%{x:,} records<extra></extra>",
    ))
    fig.update_layout(
        title=title, height=height, margin=dict(l=10, r=60, t=50, b=10),
        plot_bgcolor="rgba(0,0,0,0)", showlegend=False,
        xaxis=dict(visible=False, range=[0, max(values) * 1.15]),
    )
    return fig
