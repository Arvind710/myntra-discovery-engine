"""Entrypoint and router.

WHY NAVIGATION IS DECLARED EXPLICITLY
-------------------------------------
This app previously relied on Streamlit's implicit `app/pages/` discovery.
The sections were then reachable only through a sidebar that auto-collapses
on a narrow window, and nothing in the code stated what the app's sections
were — so "are Data Bank and Analysis reachable?" could not be answered by
reading the source, or asserted by a test.

`st.navigation` makes the section list an explicit, testable declaration.
Paths are built from `__file__`, never from a relative string: Streamlit
Cloud runs the process from the repo root while the script lives in `app/`,
so a relative path resolves against a directory that does not contain it.
That mismatch is what took the app down once already, and it did not
reproduce locally because the local run happened to start inside `app/`.
"""

from pathlib import Path

import streamlit as st

HERE = Path(__file__).resolve().parent
VIEWS = HERE / "views"

st.set_page_config(page_title="Myntra Discovery Engine", page_icon="🔎",
                   layout="wide", initial_sidebar_state="expanded")

# The project sections pinned by implementationplan.md §0.5, now complete: the
# four public sections are the four parts of the project, 1:1. A section
# appears here only once it is built, because a nav entry that leads nowhere
# tells an evaluator the section exists.
SECTIONS = [
    st.Page(VIEWS / "home.py", title="Home", icon="🔎", default=True),
    st.Page(VIEWS / "data_bank.py", title="Data Bank", icon="🗄️"),
    st.Page(VIEWS / "analysis.py", title="Analysis", icon="📊"),
    st.Page(VIEWS / "insights.py", title="Insights", icon="💡"),
    st.Page(VIEWS / "ask.py", title="Ask", icon="💬"),
]

st.navigation(SECTIONS).run()
