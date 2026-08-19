"""Single, tolerant reader for .env — and the ONLY place secrets are handled.

Two lessons are baked in here:

1. `.env` has been written by hand in both `KEY=value` and `KEY: value`
   form. A parser that understands only one silently returns nothing for
   the other, which looks exactly like "the key isn't set". Accept both.

2. NEVER print a secret. `masked()` is the only way values leave this
   module for display. Ad-hoc `cat .env` or `sed` masking is how keys end
   up in logs and transcripts.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT / ".env"

_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*[:=]\s*(.*?)\s*$")

# Hand-written .env files drift in naming. Map the variants onto canonical keys.
ALIASES = {
    "OPENAI_API_KEY": ("OPENAI_API_KEY", "OPENAI_KEY"),
    "YOUTUBE_API_KEY": ("YOUTUBE_API_KEY", "YOUTUBE", "YT_API_KEY"),
    "APIFY_TOKEN": ("APIFY_TOKEN", "APIFY_API_TOKEN", "APIFY_KEY"),
    "AUTHOR_SALT": ("AUTHOR_SALT",),
    "REDDIT_CLIENT_ID": ("REDDIT_CLIENT_ID",),
    "REDDIT_CLIENT_SECRET": ("REDDIT_CLIENT_SECRET",),
    "REDDIT_USER_AGENT": ("REDDIT_USER_AGENT",),
}


def parse(path: Path = ENV_PATH) -> dict[str, str]:
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = _LINE.match(line)
        if m:
            out[m.group(1).strip().upper()] = m.group(2).strip().strip('"\'')
    return out


def load(*, export: bool = True) -> dict[str, str]:
    """Resolve aliases to canonical names and (optionally) export to os.environ."""
    raw = parse()
    resolved: dict[str, str] = {}
    for canonical, names in ALIASES.items():
        for n in names:
            if raw.get(n):
                resolved[canonical] = raw[n]
                break
    if export:
        for k, v in resolved.items():
            os.environ[k] = v
    return resolved


def masked(value: str | None) -> str:
    """The ONLY safe way to show a credential."""
    if not value:
        return "not set"
    return f"set ({len(value)} chars, ends …{value[-4:]})" if len(value) > 8 else "set (short)"


def require(key: str) -> str:
    v = load().get(key) or os.environ.get(key, "")
    if not v:
        raise RuntimeError(f"{key} is not set in .env")
    return v


if __name__ == "__main__":
    vals = load()
    print("credentials in .env:")
    for k in ALIASES:
        print(f"  {k:<22} {masked(vals.get(k))}")
