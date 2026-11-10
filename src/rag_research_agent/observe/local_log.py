"""Allowlisted local summaries. No source, prompt, task or exception text is written."""
from __future__ import annotations

MATURITY = "incubating"

from hashlib import sha256
import json
import math
from pathlib import Path
import re

ALLOWED = {"input_hash", "segment_ids", "scores", "labels", "status", "versions"}


def append_trace(state, path=".runs/trace.jsonl"):
    rows = [row for row in state.get("rows", []) if re.fullmatch(r"s\d+", str(row.get("id", "")))]
    payload = {"input_hash": sha256(state["raw_draft"].encode()).hexdigest(),
               "segment_ids": [row["id"] for row in rows],
               "scores": [{key: row[key] for key in ("relevance", "edge", "final")
                           if isinstance(row.get(key), (int, float)) and math.isfinite(row[key])} for row in rows],
               "labels": [str(row["label"])[:80] for row in rows], "status": str(state["status"]),
               "versions": {key: state.get("versions", {}).get(key) for key in ("rule_version", "equalizer")}}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, allow_nan=False) + "\n")
    return payload
