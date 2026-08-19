"""Read-only DB access for the Streamlit app.

The app COMPUTES NOTHING. Every figure it renders is a SELECT from a
materialised `analysis_*` table written by the offline pipeline. That is
what guarantees the charts and the chatbot cannot disagree with each other,
and it is what makes NFR-3 reproducibility real: numbers do not move
between page loads.

Streamlit re-executes the whole script on every widget interaction, so
uncached reads would re-hit disk constantly (arch §10).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "corpus.db"


@st.cache_resource
def connection() -> sqlite3.Connection | None:
    if not DB_PATH.exists():
        return None
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


@st.cache_data(ttl=None)
def query(sql: str, params: tuple = ()) -> pd.DataFrame:
    con = connection()
    if con is None:
        return pd.DataFrame()
    return pd.read_sql_query(sql, con, params=params)


@st.cache_data(ttl=None)
def published_run_id() -> str | None:
    """EC-OPS-8 / X-4: the app reads a PINNED run, never 'latest'. A pipeline
    re-run mid-demo must not change what an evaluator is looking at."""
    df = query("SELECT run_id FROM published WHERE singleton = 1")
    return None if df.empty else str(df.iloc[0]["run_id"])


def corpus_is_populated() -> bool:
    df = query("SELECT count(*) AS n FROM records")
    return (not df.empty) and int(df.iloc[0]["n"]) > 0
