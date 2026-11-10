"""Owner-run Chroma embedding comparison; tests inject a local index and fake embedder."""
import argparse
import html
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from rag_research_agent.core.contracts import RetrievalUnavailable
from rag_research_agent.embed.providers import EmbeddingError
from rag_research_agent.embed.registry import create_embedder
from rag_research_agent.observe import golden
from rag_research_agent.observe.calibration import summarize_calibration
from rag_research_agent.observe.evaluate import two_axis_report
from rag_research_agent.rag.library import Library
from rag_research_agent.observe.experiments import QueryInstruction, instruction_option, score_summary, metric_table
from rag_research_agent.rag.learning import chunk_diagnostics
from scripts.eval_retrieval_v2 import _cleanup_library


def _write_comparison(results, out, instruction):
    report = ["# 임베더 비교", "", "합성 소규모 골든셋, 통계적 결론 아님", "",
              "| 모델 | 상태 | 지시문 |", "| --- | --- | --- |"]
    for result in results:
        report.append(f"| {result['model']} | {result['status']} | {instruction} |")
    for result in results:
        if "evaluation" in result:
            report.extend(["", f"{result['model']}: instruction={instruction}", *metric_table(result["evaluation"]), ""])
        if "chunking" in result:
            report.extend(["", "청크 진단: " + json.dumps(result["chunking"], ensure_ascii=False), ""])
    directory = Path(out) / "compare"
    directory.mkdir(parents=True, exist_ok=True)
    text = "\n".join(report)
    (directory / "comparison.md").write_text(text, encoding="utf-8")
    (directory / "comparison.html").write_text('<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>임베더 비교</title><body style="background:#0e141b;color:#e6edf6;font:14px/1.6 sans-serif"><h1>임베더 비교</h1><pre style="overflow-x:auto">' + html.escape(text) + '</pre></body></html>', encoding="utf-8")


def compare_models(models, set_path, no_evidence_path, corpus_path=ROOT / "data/articles.json", out=".runs",
                   embedder_factory=create_embedder, library_factory=Library, instruction="default", chunk_size=None, overlap=0):
    instruction_option(instruction)
    out = Path(out)
    articles = json.loads(Path(corpus_path).read_text(encoding="utf-8"))
    items = golden.assign_splits(golden.load([set_path, no_evidence_path], [a["id"] for a in articles]))
    results = []
    for name in models:
        if name not in ("fake", "e5", "bge-m3"):
            raise ValueError("unknown model name")
        try:
            embedder = QueryInstruction(embedder_factory(name), instruction)
        except EmbeddingError as exc:
            results.append({"model": name, "status": "미준비", "reason": str(exc)})
            continue
        try:
            docs = [(a["id"], a["title"], a["text"]) for a in articles]
            diagnostics = chunk_diagnostics(docs, embedder, chunk_size, overlap)
            if diagnostics["over_limit_chunks"]:
                results.append({"model": name, "status": "토큰 한도 초과: 평가 안 함", "chunking": diagnostics})
                continue
            lib = library_factory(out / "compare" / name / uuid4().hex, embedder=embedder)
            lib.build(docs, **({"chunk_size": chunk_size, "overlap": overlap} if chunk_size is not None else {}))
        except RetrievalUnavailable as exc:
            results.append({"model": name, "status": "저장소 미준비", "reason": str(exc)})
            continue
        try:
            rankings = {}
            def rank(query):
                grouped = {}
                for chunk, score, _ in lib.search(query, k=max(3, len(lib.chunks)), mode="vector"):
                    grouped[chunk.document_id] = max(grouped.get(chunk.document_id, float("-inf")), score)
                ranked = sorted(grouped.items(), key=lambda item: (-item[1], item[0]))
                rankings[query] = dict(ranked)
                return ranked
            rows = golden.to_rows(items, rank, "vector", k=max(3, len(articles)))
            for row, item in zip(rows, items):
                scores = rankings[item["question"]]
                right = [s for d, s in scores.items() if d in row["expected"]]
                wrong = [s for d, s in scores.items() if d not in row["expected"]]
                row.update(correct_score=max(right) if right else None, wrong_score=max(wrong) if wrong else None)
                top = row["vector"]["topk"]
                row["recall_at_3"] = len(set(top[:3]) & set(row["expected"])) / len(row["expected"]) if row["expected"] else None
                rank = next((i for i, d in enumerate(top, 1) if d in row["expected"]), None)
                row["reciprocal_rank"] = 1 / rank if rank else 0
            compare_rows = [r for r in rows if r["split"] == "compare"]
            calibration = summarize_calibration(compare_rows)
            record = {"model": name, "model_id": embedder.model_id, "revision": embedder.revision,
                      "status": "ready", **calibration,
                      "instruction": instruction, "evaluation": score_summary(compare_rows, name == "fake"), "evaluation_rows": rows,
                      "chunking": diagnostics,
                      "calibrated_on": [r["id"] for r in compare_rows],
                      "confirm": two_axis_report([r for r in rows if r["split"] == "confirm"], "vector", calibration["rule"]) if calibration["rule"] else None}
            directory = out / "calibration"
            directory.mkdir(parents=True, exist_ok=True)
            (directory / f"{name}.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
            results.append(record)
            _write_comparison(results, out, instruction)
        finally:
            _cleanup_library(lib, out)
    _write_comparison(results, out, instruction)
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--models", nargs="+", default=["fake", "e5", "bge-m3"])
    ap.add_argument("--set", default=str(ROOT / "data/golden_set.json"))
    ap.add_argument("--no-evidence", default=str(ROOT / "data/golden_no_evidence.json"))
    ap.add_argument("--corpus", default=str(ROOT / "data/articles.json"))
    ap.add_argument("--out", default=".runs")
    ap.add_argument("--instruction", default="default", type=instruction_option, metavar="{none,default,custom:<text>}")
    ap.add_argument("--chunk-size", type=int)
    ap.add_argument("--overlap", type=int, default=0)
    args = ap.parse_args(argv)
    if not Path(args.out).resolve().is_relative_to(ROOT / ".runs"):
        ap.error("results must be inside .runs")
    result = compare_models(args.models, args.set, args.no_evidence, args.corpus, args.out, instruction=args.instruction, chunk_size=args.chunk_size, overlap=args.overlap)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
