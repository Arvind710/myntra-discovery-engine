"""Per-pass provenance and cost accounting (NFR-4, X-1).

Every pipeline pass opens a run, records real token counts and cost, and
closes it. `architecture.md` §9 is an ESTIMATE; this table is what replaces
those figures with measurements, and it is what answers "how did you get
34%?" and "what did this actually cost?".
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

# Rates are confirmed at build time and recorded here, not guessed at
# read time. USD per 1M tokens. `cached_in` is the prompt-caching rate
# that applies to the stable codebook prefix (arch §6.2).
# NOTE: batch jobs bill at 50% -- see Run.finish(batch=True).
MODEL_RATES: dict[str, dict[str, float]] = {
    # filled in at P0 from the live pricing page; asserted non-empty by P0-7
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Run:
    def __init__(self, con: sqlite3.Connection, stage: str, **params: Any) -> None:
        self.con = con
        self.run_id = f"{stage}-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
        self.stage = stage
        self.params = params
        self.input_tokens = 0
        self.output_tokens = 0
        self.cached_tokens = 0
        self.n_input = 0
        self.n_output = 0
        self.model = params.get("model")
        self.batch = bool(params.get("batch", False))

    def __enter__(self) -> "Run":
        self.con.execute(
            "INSERT INTO runs (run_id, stage, started_at, model, prompt_version,"
            " codebook_version, params_json) VALUES (?,?,?,?,?,?,?)",
            (
                self.run_id, self.stage, _now(), self.model,
                self.params.get("prompt_version"),
                self.params.get("codebook_version"),
                json.dumps(self.params, default=str),
            ),
        )
        self.con.commit()
        return self

    def add_usage(self, *, input_tokens: int = 0, output_tokens: int = 0,
                  cached_tokens: int = 0) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.cached_tokens += cached_tokens

    def cost_usd(self) -> float | None:
        rates = MODEL_RATES.get(self.model or "")
        if not rates:
            return None
        fresh_in = max(self.input_tokens - self.cached_tokens, 0)
        usd = (
            fresh_in / 1e6 * rates["in"]
            + self.cached_tokens / 1e6 * rates.get("cached_in", rates["in"])
            + self.output_tokens / 1e6 * rates["out"]
        )
        return round(usd * (0.5 if self.batch else 1.0), 6)

    def __exit__(self, exc_type, exc, tb) -> None:
        self.con.execute(
            "UPDATE runs SET finished_at=?, n_input=?, n_output=?, input_tokens=?,"
            " output_tokens=?, cached_tokens=?, cost_usd=? WHERE run_id=?",
            (_now(), self.n_input, self.n_output, self.input_tokens,
             self.output_tokens, self.cached_tokens, self.cost_usd(), self.run_id),
        )
        self.con.commit()
