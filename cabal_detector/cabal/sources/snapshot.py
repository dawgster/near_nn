"""Snapshot persistence.

Ingestion is slow and rate-limited; scoring is fast and gets iterated on. Keeping
the raw pull on disk means you tune detector weights without re-hammering the RPC,
and it makes a flagged wallet list reproducible by anyone holding the same file.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..models import TokenSnapshot


def save_snapshot(snapshot: TokenSnapshot, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot.to_json(), indent=2))
    return path


def load_snapshot(path: str | Path) -> TokenSnapshot:
    return TokenSnapshot.from_json(json.loads(Path(path).read_text()))
