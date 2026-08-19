"""The app's sections must be reachable — asserted, not assumed.

This file exists because of a live outage. `st.page_link("pages/1_Data_Bank.py")`
resolves its path against the PROCESS working directory. Streamlit Cloud runs
from the repo root while the script lives in `app/`, so the path pointed at a
directory that does not contain it and the whole Home page died with a
KeyError. It passed pre-deploy because the check ran with cwd=`app/`.

The lesson generalises past this one bug: a check that runs in a different
working directory than production is not a check. Every test here chdirs to
the repo root first, because that is where Streamlit Cloud starts the process.

`architecture.md` treats the app as the deliverable and AC-1 / P5-6 require a
stranger to browse it unassisted. "Does the navigation work?" therefore
deserves a test, not a manual click-through that happens once before a demo.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = "app/Home.py"

# The sections pinned by implementationplan.md §0.5, as (page path, title).
SECTIONS = [
    ("views/home.py", "Home"),
    ("views/data_bank.py", "Data Bank"),
    ("views/analysis.py", "Analysis"),
]


@pytest.fixture
def at_repo_root():
    """Streamlit Cloud starts the process at the repo root, not in `app/`."""
    prev = os.getcwd()
    os.chdir(ROOT)
    yield
    os.chdir(prev)


def test_entrypoint_declares_every_section(at_repo_root):
    """The section list is a declaration in source, so a reviewer can answer
    'what does this app contain?' by reading one file."""
    src = (ROOT / ENTRYPOINT).read_text()
    assert "st.navigation" in src, "entrypoint must declare navigation explicitly"
    for page, title in SECTIONS:
        leaf = page.split("/")[-1]
        assert leaf in src, f"{leaf} is not declared in {ENTRYPOINT}"
        assert f'title="{title}"' in src, f"section {title!r} is not titled in the nav"


def test_no_relative_page_paths_in_entrypoint(at_repo_root):
    """The exact regression. Page paths must be built from __file__, never from
    a bare relative string, because the process cwd is not the script's dir."""
    src = (ROOT / ENTRYPOINT).read_text()
    assert "Path(__file__)" in src, "page paths must be anchored to __file__"
    for bad in ['st.Page("', "st.Page('", 'st.page_link("pages/', 'st.page_link("views/']:
        assert bad not in src, (
            f"{bad!r} is a cwd-relative page path — it resolves against the "
            "process working directory, which on Streamlit Cloud is the repo root")


@pytest.mark.parametrize("page,title", SECTIONS, ids=[t for _, t in SECTIONS])
def test_section_renders_without_exception(at_repo_root, page, title):
    """Runs the real script through Streamlit's harness from production's cwd.
    An import error, a bad path, or a broken query surfaces here rather than in
    front of an evaluator."""
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / ENTRYPOINT), default_timeout=180)
    at.switch_page(page)
    at.run()
    assert not at.exception, f"{title} raised: {at.exception[0].value}"
    # A page that renders nothing is "not crashing", which is not the same as
    # working. Every section must actually put something on screen.
    assert len(at.markdown) + len(at.dataframe) > 0, f"{title} rendered nothing"


def test_label_tool_is_not_a_public_section(at_repo_root):
    """§0.5 pins the public nav to the project sections. The gold labeller is an
    operator tool that writes to the DB; it must not be discoverable by, or
    reachable from, the deployed app."""
    src = (ROOT / ENTRYPOINT).read_text()
    assert "label" not in src.lower().replace("labelled", ""), \
        "the labelling tool must not appear in the public navigation"
    assert not (ROOT / "app" / "pages").exists(), (
        "app/pages/ is auto-discovered by Streamlit and would re-introduce an "
        "implicit second navigation alongside the declared one")
    assert (ROOT / "tools" / "label_app.py").exists(), "labeller should live in tools/"


# --------------------------------------------------------------------------
# Labelling tool — the gate must actually open, and must say when it doesn't
# --------------------------------------------------------------------------
def _labeller(pw: str = "correct-horse"):
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "tools" / "label_app.py"), default_timeout=180)
    at.secrets["LABEL_PASSWORD"] = pw
    return at.run()


def _unlocked(at) -> bool:
    try:
        return bool(at.session_state["label_ok"])
    except Exception:                                          # noqa: BLE001
        return False


def test_correct_password_opens_the_gate(at_repo_root):
    """This shipped broken: st.rerun() was called INSIDE the `with st.form`
    block, so submitting the right password did nothing at all. The failure was
    invisible to every check that only asserted the page renders — the gate
    rendered perfectly, it just never opened."""
    at = _labeller()
    at.text_input[0].input("correct-horse").run()
    at.button[0].click().run()
    assert _unlocked(at), "correct password did not unlock the labeller"
    assert not at.exception, at.exception[0].value
    labels = [b.label for b in at.button]
    assert any("Save and next" in b for b in labels), labels
    assert any("Skip" in b for b in labels), "skip control missing"


def test_wrong_password_says_so_rather_than_doing_nothing(at_repo_root):
    """A silent rejection and a broken gate look identical to the user, which
    is exactly how the bug above went unreported for a build."""
    at = _labeller()
    at.text_input[0].input("wrong").run()
    at.button[0].click().run()
    assert not _unlocked(at)
    assert at.error, "a wrong password must produce a visible message"
