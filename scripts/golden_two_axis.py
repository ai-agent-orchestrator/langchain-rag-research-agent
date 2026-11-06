"""Print the two-axis golden-set report (rank vs gate decision) for one embedder.

  python scripts/golden_two_axis.py                         # fake embedder, keyword-level baseline
  HF_HUB_OFFLINE=1 python scripts/golden_two_axis.py --embedder e5 --revision <pinned>

The rule is frozen on the compare split, then applied once to the confirm split.
No network: the fake embedder is local; E5 loads from the local cache only.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from memvid_guardrail.embed.providers import make_embedder
from memvid_guardrail.observe import golden
from memvid_guardrail.observe.evaluate import confirm, freeze_rule, two_axis_report

DATA = Path(__file__).resolve().parents[1] / "data"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--embedder", default="fake")
    parser.add_argument("--revision")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    articles = json.loads((DATA / "articles.json").read_text(encoding="utf-8"))
    items = golden.assign_splits(golden.load([DATA / "golden_set.json", DATA / "golden_no_evidence.json"],
                                             [a["id"] for a in articles], min_no_evidence=0.3))
    emb = make_embedder(args.embedder, revision=args.revision)
    doc_vecs = emb.encode_documents([a["text"] for a in articles])

    def rank(question):
        q = emb.encode_query(question)
        scores = [(a["id"], sum(x * y for x, y in zip(q, v))) for a, v in zip(articles, doc_vecs)]
        return sorted(scores, key=lambda s: s[1], reverse=True)

    rows = golden.to_rows(items, rank, "vector")
    rule = freeze_rule([r for r in rows if r["split"] == "compare"], "vector", f"{emb.model_id}@{emb.revision}")
    report = {"embedder": emb.model_id, "revision": emb.revision,
              "compare": two_axis_report([r for r in rows if r["split"] == "compare"], "vector", rule),
              "confirm": confirm([r for r in rows if r["split"] == "confirm"], rule),
              "rule": {k: rule[k] for k in ("tau_abs", "tau_gap", "version")}}
    for part in ("compare", "confirm"):
        rep = report[part]
        print(f"[{part}] ranking {rep['ranking']}  decision {rep['decision']}  attention {rep['attention']}")
    if args.out:
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
