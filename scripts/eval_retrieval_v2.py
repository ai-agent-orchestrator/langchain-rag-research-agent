"""Quote-aware retrieval and extractive end-to-end evaluation; no generation calls."""
import argparse
import html
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rag_research_agent.embed.registry import create_embedder
from rag_research_agent.observe.golden_v2 import load, score_item, report, METRICS
from rag_research_agent.observe.evaluate import calibrate
from rag_research_agent.rag.library import Library
from rag_research_agent.rag.profile import Equalizer


def _input_policy():
    try:
        from rag_research_agent.guard.intake_guard_adapter import IntakeInputPolicy
        return IntakeInputPolicy()
    except (ImportError, RuntimeError):
        return None


def evaluate(set_path, embedder="fake", split=None, k=3, e2e=False, profile="research", out=".runs/eval_v2",
             library_factory=Library, embedder_factory=create_embedder, policy="auto", corpus=None):
    dataset = load(set_path, corpus)
    policy = _input_policy() if policy == "auto" else policy
    if policy is not None and type(policy).__name__ == "FakeInputPolicy":
        policy = None
    emb = embedder_factory(embedder)
    with TemporaryDirectory(prefix="rra-golden-v2-") as temp:
        lib = library_factory(Path(temp) / "index", embedder=emb)
        lib.build([(a["id"], a["title"], a["text"]) for a in dataset["corpus"]])
        rankings, statuses, calibration_rows = {}, {}, []
        try:
            for item in dataset["items"]:
                status = None
                if policy is not None:
                    status = "OK" if policy.check(item["question"]).allowed else "BLOCKED"
                statuses[item["id"]] = status
                hits = [] if status == "BLOCKED" else lib.search(item["question"], k=max(k, len(lib.chunks)), mode="vector")
                rankings[item["id"]] = [{"source": chunk.document_id, "text": chunk.safe_text, "score": score} for chunk, score, _ in hits]
                scores = [h["score"] for h in rankings[item["id"]]]
                if item["type"] != "injection" and item["split"] == "compare":
                    calibration_rows.append({"expected": [e["source"] for e in item["relevant"]],
                                             "vector": {"top1": scores[0] if scores else 0,
                                                        "gap": scores[0] - scores[1] if len(scores) > 1 else 0}})
            rule = calibrate(calibration_rows, "vector", use_gap=False) if calibration_rows else None
            rows = []
            for item in dataset["items"]:
                if split and item["split"] != split:
                    continue
                hits = rankings[item["id"]]
                accepted = bool(rule and hits and hits[0]["score"] >= rule["tau_abs"] and statuses[item["id"]] != "BLOCKED")
                kept = None
                if e2e and item["type"] != "injection":
                    draft = "\n\n".join(h["text"] for h in hits[:k]) if accepted else ""
                    brief, trace = Equalizer.from_profile(profile).brief(draft, task=item["question"])
                    kept = [r["text"] for r in trace.rows if r.get("kept")]
                rows.append(score_item(item, hits, accepted, k, kept, statuses[item["id"]]))
            result = {**report(rows), "name": dataset["name"], "model_id": emb.model_id, "revision": emb.revision,
                      "k": k, "e2e": e2e, "calibration": rule,
                      "calibrated_on": [i["id"] for i in dataset["items"] if i["split"] == "compare" and i["type"] != "injection"]}
        finally:
            if lib.index is not None:
                lib.index.close()
    lines = ["# 검색 골든셋 v2", "", result["note"], "", "| 범위 | n | " + " | ".join(METRICS) + " |",
             "| --- | --- | " + " | ".join("---" for _ in METRICS) + " |"]
    groups = {"overall": result["overall"], **{"type:" + k: v for k,v in result["by_type"].items()},
              **{"split:" + k: v for k,v in result["by_split"].items()}}
    for name, group in groups.items():
        lines.append("| " + name + " | " + str(group["count"]) + " | " + " | ".join(str(group[m]) for m in METRICS) + " |")
    text = "\n".join(lines)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "report.md").write_text(text, encoding="utf-8")
    (out / "report.html").write_text('<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>검색 골든셋 v2</title><body style="background:#0e141b;color:#e6edf6"><h1>검색 골든셋 v2</h1><pre style="overflow-x:auto">' + html.escape(text) + '</pre></body></html>', encoding="utf-8")
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--set", required=True)
    ap.add_argument("--embedder", default="fake", choices=["fake", "e5", "bge-m3"])
    ap.add_argument("--split", choices=["compare", "confirm"])
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--e2e", action="store_true")
    ap.add_argument("--profile", default="research")
    ap.add_argument("--out", default=".runs/eval_v2")
    args = ap.parse_args(argv)
    result = evaluate(args.set, args.embedder, args.split, args.k, args.e2e, args.profile, args.out)
    print(result["overall"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
