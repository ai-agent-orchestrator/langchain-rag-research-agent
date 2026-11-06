"""Compare embedding models on a golden set (1위 정답 / 3위 안 정답 / MRR / latency).

  python scripts/compare_embedders.py --golden data/golden_set.json --corpus data/articles.json --models fake
  HF_HUB_OFFLINE=1 python scripts/compare_embedders.py --golden ... --corpus ... --models fake,e5@<revision>
  python scripts/compare_embedders.py --legal-intake <path to legal-intake corpus/synthetic> --models fake,e5@<rev>

Network is blocked for the whole run; models must already be in the local cache.
Results go to docs/evidence/golden/. The fake model is a keyword-like baseline, not a semantic model.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from memvid_guardrail.guard.network import ATTEMPTS, block_network, scrub_environment  # noqa: E402


def build(spec: str):
    from memvid_guardrail.embed.providers import make_embedder
    kind, _, revision = spec.partition("@")
    return make_embedder(kind, revision or None)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden")
    parser.add_argument("--corpus")
    parser.add_argument("--legal-intake", help="path to legal-intake corpus/synthetic (uses evidence items)")
    parser.add_argument("--models", default="fake")
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--out", default="docs/evidence/golden/compare")
    args = parser.parse_args()
    scrub_environment()
    block_network()
    from memvid_guardrail.lab.golden import compare, from_legal_intake, load_json, to_markdown

    if args.legal_intake:
        root = Path(args.legal_intake)
        manifest = json.loads((root / "guides.json").read_text(encoding="utf-8"))
        golden, corpus = from_legal_intake(load_json(root / "eval" / "intakes.json"), root, manifest)
    else:
        golden, corpus = load_json(args.golden), load_json(args.corpus)
    embedders = {spec: build(spec) for spec in args.models.split(",")}
    report = compare(embedders, golden, corpus, args.k)
    report["network_attempts"] = ATTEMPTS
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    out.with_suffix(".md").write_text(to_markdown(report), encoding="utf-8")
    print(to_markdown(report))
    return 0 if not ATTEMPTS else 1


if __name__ == "__main__":
    sys.exit(main())
