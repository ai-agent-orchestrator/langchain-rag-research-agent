"""Quote-aware retrieval and extractive end-to-end evaluation; no generation calls."""
import argparse
from contextlib import contextmanager
import html
import json
import logging
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rag_research_agent.embed.registry import create_embedder
from rag_research_agent.observe.golden_v2 import load, score_item, report, METRICS
from rag_research_agent.observe.evaluate import calibrate
from rag_research_agent.rag.library import Library
from rag_research_agent.rag.profile import Equalizer
from rag_research_agent.observe.experiments import QueryInstruction, instruction_option, score_summary, metric_table
from rag_research_agent.rag.learning import chunk_diagnostics
from rag_research_agent.lab.retrieval_fusion import search as fusion_search


def _cleanup_library(library, out, temporary=None):
    """Cleanup is best effort; keep durable diagnostics without masking evaluation errors."""
    def warning(stage, exc):
        record = {"stage": stage, "path": str(temporary.name if temporary else getattr(library, "path", out)),
                  "error": type(exc).__name__, "message": str(exc), "winerror": getattr(exc, "winerror", None)}
        logging.getLogger(__name__).warning("Chroma cleanup warning: %s", record)
        try:
            target = Path(out)
            target.mkdir(parents=True, exist_ok=True)
            with (target / "cleanup_warnings.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            logging.getLogger(__name__).exception("Could not persist Chroma cleanup warning")

    try:
        if library is not None and library.index is not None:
            library.index.close()
    except Exception as exc:
        warning("client.close", exc)
    finally:
        if temporary is not None:
            try:
                temporary.cleanup()
            except OSError as exc:
                warning("temporary.cleanup", exc)


@contextmanager
def _evaluation_library(index_root, out, library_factory, embedder):
    temporary = TemporaryDirectory(prefix="run-", dir=index_root)
    library = None
    try:
        library = library_factory(Path(temporary.name) / "index", embedder=embedder)
        yield library
    finally:
        _cleanup_library(library, out, temporary)


def _input_policy():
    try:
        from rag_research_agent.guard.intake_guard_adapter import IntakeInputPolicy
        return IntakeInputPolicy()
    except (ImportError, RuntimeError):
        return None


def evaluate(set_path, embedder="fake", split=None, k=3, e2e=False, profile="research", out=".runs/eval_v2",
             library_factory=Library, embedder_factory=create_embedder, policy="auto", corpus=None, instruction="default", chunk_size=None, overlap=0,
             retrieval="vector", alpha=.5, rrf_k=60):
    instruction_option(instruction)
    dataset = load(set_path, corpus)
    policy = _input_policy() if policy == "auto" else policy
    if policy is not None and type(policy).__name__ == "FakeInputPolicy":
        policy = None
    emb = QueryInstruction(embedder_factory(embedder), instruction)
    docs = [(a["id"], a["title"], a["text"]) for a in dataset["corpus"]]
    diagnostics = chunk_diagnostics(docs, emb, chunk_size, overlap, dataset["items"])
    if diagnostics["over_limit_chunks"]:
        result = {"status": "토큰 한도 초과: 평가 안 함", "chunking": diagnostics,
                  "overall": {}, "evaluation": {"path_test": None, "real_model": None}}
        target = Path(out)
        target.mkdir(parents=True, exist_ok=True)
        (target / "report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        (target / "report.md").write_text(result["status"] + "\n" + json.dumps(diagnostics, ensure_ascii=False), encoding="utf-8")
        return result
    index_root = Path(out) / "indexes"
    index_root.mkdir(parents=True, exist_ok=True)
    with _evaluation_library(index_root, out, library_factory, emb) as lib:
        lib.build(docs, **({"chunk_size": chunk_size, "overlap": overlap} if chunk_size is not None else {}))
        rankings, statuses, calibration_rows = {}, {}, []
        for item in dataset["items"]:
            status = None
            if policy is not None:
                status = "OK" if policy.check(item["question"]).allowed else "BLOCKED"
            statuses[item["id"]] = status
            hits = [] if status == "BLOCKED" else fusion_search(lib, item["question"], max(k, len(lib.chunks)), retrieval, alpha, rrf_k)
            rankings[item["id"]] = [{"source": chunk.document_id, "text": chunk.safe_text, "score": score} for chunk, score, _ in hits]
            scores = [h["score"] for h in rankings[item["id"]]]
            if item["type"] != "injection" and item["split"] == "compare":
                calibration_rows.append({"expected": [e["source"] for e in item["relevant"]],
                                         "vector": {"top1": scores[0] if scores else 0,
                                                    "gap": scores[0] - scores[1] if len(scores) > 1 else 0}})
        rule = calibrate(calibration_rows, "vector", use_gap=False) if calibration_rows else None
        rows = []
        evaluation_rows = []
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
            if item["type"] != "injection":
                correct = [h["score"] for h in hits if any(h["source"] == r["source"] and r["quote"] in h["text"] for r in item["relevant"])]
                metrics3 = score_item(item, hits, accepted, 3)
                evaluation_rows.append({"id": item["id"], "split": item["split"], "type": item["type"],
                                        "expected": [r["source"] for r in item["relevant"]],
                                        "correct_score": max(correct) if correct else None,
                                        "recall_at_3": metrics3["recall"], "reciprocal_rank": metrics3["mrr"],
                                        "vector": {"top1": hits[0]["score"] if hits else 0,
                                                   "gap": hits[0]["score"] - hits[1]["score"] if len(hits) > 1 else 0}})
        result = {**report(rows), "name": dataset["name"], "model_id": emb.model_id, "revision": emb.revision,
                  "k": k, "e2e": e2e, "calibration": rule,
                  "instruction": instruction, "evaluation_rows": evaluation_rows,
                  "chunking": diagnostics,
                  "retrieval": {"method": retrieval, "alpha": alpha, "rrf_k": rrf_k},
                  "evaluation": score_summary(evaluation_rows, embedder == "fake"),
                  "calibrated_on": [i["id"] for i in dataset["items"] if i["split"] == "compare" and i["type"] != "injection"]}
        lines = ["# 검색 골든셋 v2", "", result["note"], "", "| 범위 | n | 지표 | fake: 경로 시험 | 실제 모델 |",
                 "| --- | --- | --- | --- | --- |"]
        groups = {"overall": result["overall"], **{"type:" + k: v for k,v in result["by_type"].items()},
                  **{"split:" + k: v for k,v in result["by_split"].items()}}
        for name, group in groups.items():
            for metric in METRICS:
                values = [str(group[metric]), "미실행"] if embedder == "fake" else ["미실행", str(group[metric])]
                lines.append(f"| {name} | {group['count']} | {metric} | " + " | ".join(values) + " |")
        text = "\n".join(lines)
        text += "\n\n" + "\n".join(metric_table(result["evaluation"]))
        text += "\n\n청크 진단: " + json.dumps(diagnostics, ensure_ascii=False)
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
    ap.add_argument("--instruction", default="default", type=instruction_option, metavar="{none,default,custom:<text>}")
    ap.add_argument("--chunk-size", type=int)
    ap.add_argument("--overlap", type=int, default=0)
    ap.add_argument("--retrieval", choices=["lex", "vector", "rrf", "weighted"], default="vector")
    ap.add_argument("--alpha", type=float, default=.5)
    ap.add_argument("--rrf-k", type=int, default=60)
    args = ap.parse_args(argv)
    if not Path(args.out).resolve().is_relative_to(ROOT / ".runs"):
        ap.error("results must be inside .runs")
    result = evaluate(args.set, args.embedder, args.split, args.k, args.e2e, args.profile, args.out, instruction=args.instruction, chunk_size=args.chunk_size, overlap=args.overlap,
                      retrieval=args.retrieval, alpha=args.alpha, rrf_k=args.rrf_k)
    print(result["overall"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
