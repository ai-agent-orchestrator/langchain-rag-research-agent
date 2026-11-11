"""Precompute the offline rule-based compare grid; never evaluates confirm cases.

Run: python scripts/research_grid.py
Outputs: .runs/research_eval/grid.json and board.html (with existing run history).
"""
from __future__ import annotations

MATURITY = "incubating"

import datetime as dt
import json
from dataclasses import asdict
from itertools import product
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.research_eval import (  # noqa: E402
    CASES, OUT, ResearchConfig, ResearchRunner, aggregate, git_sha, keyword_search, score,
)

KNOBS = ROOT / "evals" / "research" / "knobs.json"


def load_knobs():
    return json.loads(KNOBS.read_text(encoding="utf-8"))["knobs"]


def combinations(knobs):
    return [dict(zip(knobs, values)) for values in product(*(k["values"] for k in knobs.values()))]


def build_grid(dataset):
    knobs = load_knobs()
    cases = [c for c in dataset["cases"] if c["split"] == "compare" and c.get("type") != "injection"]
    if not cases:
        raise ValueError("compare cases are required")
    entries = []
    for selected in combinations(knobs):
        cfg = ResearchConfig(**selected)
        rows = []
        for case in cases:
            corpus = case["docs"]
            result = ResearchRunner(keyword_search(corpus), cfg).run(
                case["question"], tuple(case.get("checklist", ())))
            rows.append(score(case, result, " ".join(corpus.values())))
        entries.append({"knobs": selected, "config": asdict(cfg),
                        "summary": aggregate(rows), "cases": rows})
    return {"schema_version": 1, "at": dt.datetime.now().isoformat(timespec="seconds"),
            "sha": git_sha(), "split": "compare", "dataset": dataset["version"],
            "evaluation": "synthetic_rule_path_test", "tokens": "estimated_chars_per_2",
            "knobs": knobs, "defaults": {k: v["default"] for k, v in knobs.items()},
            "entries": entries}


def main():
    grid = build_grid(json.loads(CASES.read_text(encoding="utf-8")))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "grid.json").write_text(json.dumps(grid, ensure_ascii=False, indent=2), encoding="utf-8")
    history = OUT / "runs.jsonl"
    runs = [json.loads(line) for line in history.read_text(encoding="utf-8").splitlines() if line.strip()] if history.exists() else []
    from scripts.research_board import render
    (OUT / "board.html").write_text(render(runs, grid=grid), encoding="utf-8")
    print(f"compare grid: {len(grid['entries'])} combinations; {OUT / 'grid.json'}")


if __name__ == "__main__":
    main()
