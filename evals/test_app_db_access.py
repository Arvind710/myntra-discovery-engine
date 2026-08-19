"""The app's database access must fail loudly, legibly, and recoverably.

This file exists because of a live incident. `app/lib/db.py` cached the
connection with a bare `@st.cache_resource` and returned `None` when the file
was missing. Streamlit Cloud hot-reloads code WITHOUT restarting the process,
so a single moment with no readable file — mid-deploy, while a 20 MB database
is being replaced — cached a `None` that outlived every subsequent rerun. The
deployed app then reported an empty corpus until someone rebooted the
container by hand.

Two properties are asserted here, and they are different properties:

1. **Recoverability** — a cache keyed on the file's fingerprint cannot pin a
   stale or null result past a change to the file. A transient failure must
   not become permanent.
2. **Truthfulness** — "no file", "unreadable file", and "file with no rows"
   have different causes and different fixes. The app used to render all three
   as "the corpus has not been collected yet", which is a claim about the
   PIPELINE inferred from evidence that only concerned the FILE. An evaluator
   reading that would conclude the project never ran.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


@pytest.fixture
def appdb(monkeypatch, tmp_path):
    """The app's db module, pointed at a temporary path and with Streamlit's
    caches neutralised so each case is independent."""
    from lib import db as appdb_mod

    monkeypatch.setattr(appdb_mod, "DB_PATH", tmp_path / "corpus.db")
    for fn in (appdb_mod._connect, appdb_mod._query):
        try:
            fn.clear()
        except Exception:                                      # noqa: BLE001
            pass
    return appdb_mod


def _make_db(path: Path, rows: int) -> None:
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE records (record_id TEXT PRIMARY KEY)")
    con.executemany("INSERT INTO records VALUES (?)", [(f"r{i}",) for i in range(rows)])
    con.commit()
    con.close()


def test_missing_file_is_reported_as_missing_not_as_uncollected(appdb):
    """The exact mislabelling that shipped. A missing file must never be
    described as a pipeline that has not run."""
    status, detail = appdb.db_status()
    assert status == "missing"
    assert not appdb.corpus_is_populated()
    low = detail.lower()
    assert "not that the pipeline has not run" in low or "absent" in low, detail
    assert "has not been collected" not in low, \
        "a missing file is being reported as an uncollected corpus"


def test_empty_database_is_distinguished_from_a_missing_one(appdb):
    """Both mean 'no data to show' and both need a different fix, so the app
    must not collapse them into one message."""
    _make_db(appdb.DB_PATH, rows=0)
    status, detail = appdb.db_status()
    assert status == "empty", detail
    assert not appdb.corpus_is_populated()
    assert "collect" in detail.lower(), "an empty DB should point at the collectors"


def test_populated_database_reports_ok(appdb):
    _make_db(appdb.DB_PATH, rows=7)
    status, detail = appdb.db_status()
    assert status == "ok", detail
    assert appdb.corpus_is_populated()
    assert "7" in detail


def test_a_transient_missing_file_does_not_become_permanent(appdb):
    """THE regression. Read while the file is absent, then create it: the app
    must recover on its own. Under the old bare @st.cache_resource the None
    was pinned for the life of the process and only a reboot cleared it."""
    assert appdb.db_status()[0] == "missing"

    _make_db(appdb.DB_PATH, rows=3)

    status, detail = appdb.db_status()
    assert status == "ok", (
        f"the app did not recover after the file appeared ({status}: {detail}) — "
        "a transient failure has become permanent")
    assert appdb.corpus_is_populated()


def test_changed_file_is_not_served_from_a_stale_cache(appdb):
    """A 20 MB database being replaced mid-deploy is the real scenario. Results
    must follow the file, not the process lifetime."""
    _make_db(appdb.DB_PATH, rows=2)
    assert int(appdb.query("SELECT count(*) AS n FROM records").iloc[0]["n"]) == 2

    appdb.DB_PATH.unlink()
    _make_db(appdb.DB_PATH, rows=11)

    n = int(appdb.query("SELECT count(*) AS n FROM records").iloc[0]["n"])
    assert n == 11, f"served {n} rows from a stale cache after the file changed"


def test_connection_is_opened_read_only(appdb):
    """The app must never be able to write to the corpus it is rendering."""
    _make_db(appdb.DB_PATH, rows=1)
    con = appdb.connection()
    assert con is not None
    with pytest.raises(sqlite3.OperationalError):
        con.execute("INSERT INTO records VALUES ('should-not-write')")
