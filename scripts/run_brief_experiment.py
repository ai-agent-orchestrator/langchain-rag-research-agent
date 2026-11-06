"""Run the long-prompt briefing experiment: strategies x tasks on a synthetic 40+ page prompt.

  python scripts/run_brief_experiment.py --embedder fake
  HF_HUB_OFFLINE=1 python scripts/run_brief_experiment.py --embedder e5 --revision <commit>

Writes docs/evidence/brief/brief_<embedder>.json and .md. Network is blocked; synthetic data only.
The fake embedder hashes character bigrams, so its "vector" results behave like keywords and are
never reported as semantic results.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from memvid_guardrail.guard.network import ATTEMPTS, block_network, scrub_environment  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--embedder", choices=["fake", "e5"], default="fake")
    parser.add_argument("--revision")
    parser.add_argument("--budget", type=int, default=6000)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out-dir", default="docs/evidence/brief")
    args = parser.parse_args()
    scrub_environment()
    block_network()

    from memvid_guardrail.embed.providers import make_embedder
    from memvid_guardrail.lab.briefing.pipeline import STRATEGIES, build_brief
    from memvid_guardrail.lab.briefing.synthetic import generate, score_brief

    embedder = make_embedder(args.embedder, args.revision)
    prompt = generate(seed=args.seed)

    def encode(texts):
        return embedder.encode_documents(texts)

    def encode_task_aware(texts):
        # E5 uses a query instruction for the task and none for passages; the pipeline calls
        # encode([task]) separately, so route single short inputs to encode_query.
        if len(texts) == 1 and len(texts[0]) < 400:
            return [embedder.encode_query(texts[0])]
        return embedder.encode_documents(texts)

    rows = []
    for task in prompt.tasks:
        for strategy in STRATEGIES:
            t0 = time.monotonic()
            brief = build_brief(prompt.text, task["text"], budget=args.budget, strategy=strategy,
                                encode=encode_task_aware if args.embedder == "e5" else encode)
            rows.append({"task": task["id"], "strategy": strategy, "ms": round((time.monotonic() - t0) * 1000, 1),
                         "expanded_terms": brief.expanded_terms[:12], "excluded_injection_segments": len(brief.excluded_injection),
                         **score_brief(brief.text, task, prompt)})
    summary = {}
    for strategy in STRATEGIES:
        mine = [r for r in rows if r["strategy"] == strategy]
        summary[strategy] = {
            "mean_needle_recall": round(sum(r["needle_recall_value"] for r in mine) / len(mine), 3),
            "attack_leaks": sum(len(r["attack_leak"]) for r in mine),
            "pii_leaks": sum(r["pii_leak"] for r in mine),
            "superseded_included": sum(len(r["superseded_included"]) for r in mine),
            "mean_brief_chars": round(sum(r["brief_chars"] for r in mine) / len(mine)),
        }
    report = {"embedder": args.embedder, "semantic": args.embedder != "fake", "model": embedder.model_id,
              "revision": embedder.revision, "source_chars": len(prompt.text), "pages": prompt.pages,
              "budget": args.budget, "summary": summary, "rows": rows, "network_attempts": ATTEMPTS}
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"brief_{args.embedder}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = [f"# Briefing experiment ({args.embedder}{'' if report['semantic'] else ', not semantic'})", "",
             f"Source {len(prompt.text):,} chars ({prompt.pages} pages), budget {args.budget:,} chars, seed {args.seed}.", "",
             "| strategy | mean needle recall | attack leaks | PII leaks | superseded included | mean brief chars |",
             "| --- | --- | --- | --- | --- | --- |"]
    for s, v in summary.items():
        lines.append(f"| {s} | {v['mean_needle_recall']} | {v['attack_leaks']} | {v['pii_leaks']} | {v['superseded_included']} | {v['mean_brief_chars']:,} |")
    lines += ["", "| task | strategy | needle recall | missing | superseded |", "| --- | --- | --- | --- | --- |"]
    lines += [f"| {r['task']} | {r['strategy']} | {r['needle_recall']} | {', '.join(r['missing']) or '-'} | {', '.join(r['superseded_included']) or '-'} |" for r in rows]
    (out / f"brief_{args.embedder}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:4 + 2 + len(summary)]))
    return 0 if not ATTEMPTS else 1


if __name__ == "__main__":
    sys.exit(main())
