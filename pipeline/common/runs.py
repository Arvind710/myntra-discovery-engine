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
# Confirmed 2026-08-19 against developers.openai.com/api/docs/pricing.
# Batch jobs bill at 50% -- applied in Run.cost_usd(), not duplicated here.
MODEL_RATES: dict[str, dict[str, float]] = {
    "gpt-5":                  {"in": 1.25, "cached_in": 0.125, "out": 10.00},
    "gpt-5-mini":             {"in": 0.25, "cached_in": 0.025, "out": 2.00},
    "gpt-5-nano":             {"in": 0.05, "cached_in": 0.005, "out": 0.40},
    "gpt-4.1":                {"in": 2.00, "cached_in": 0.50,  "out": 8.00},
    "gpt-4.1-mini":           {"in": 0.40, "cached_in": 0.10,  "out": 1.60},
    "text-embedding-3-small": {"in": 0.02, "cached_in": 0.02,  "out": 0.00},
}

# The classification model. architecture.md §6.2 and DECISIONS.md both refuse
# tier-splitting here: the C1-vs-C8 boundary is exactly where smaller models
# fail, and the analysis IS the project.
CLASSIFIER_MODEL = "gpt-5"
EMBEDDING_MODEL = "text-embedding-3-small"


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
