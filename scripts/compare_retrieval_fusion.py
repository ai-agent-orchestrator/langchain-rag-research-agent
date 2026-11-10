"""Compare retrieval methods by question type; sweeps only use compare questions."""
import argparse
import html
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.eval_retrieval_v2 import evaluate


def compare(set_path, out=".runs/e7", embedder="fake", alphas=(.25, .5, .75), rrf_ks=(10, 60, 100), **kwargs):
    configs = [("lex", .5, 60), ("vector", .5, 60)]
    configs += [("rrf", .5, k) for k in rrf_ks] + [("weighted", a, 60) for a in alphas]
    results = []
    lines = ["# E7 검색 방식 비교", "", "같은 골든셋의 compare 문항만 사용. injection은 품질 분모에서 제외.", "",
             "| 방식 | α | RRF k | 문항 유형 | 지표 | fake: 경로 시험 | 실제 모델 |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for method, alpha, k in configs:
        tag = f"{method}-{alpha}-{k}"
        result = evaluate(set_path, embedder=embedder, split="compare", out=Path(out) / tag,
                          retrieval=method, alpha=alpha, rrf_k=k, **kwargs)
        if "by_type" not in result:
            results.append({"configuration": tag, "result": result})
            continue
        results.append({"configuration": tag, "result": result})
        for kind, group in {"overall": result["overall"], **result["by_type"]}.items():
            if kind == "injection":
                continue
            for metric in ("recall", "mrr", "false_accept", "false_refusal"):
                values = [str(group[metric]), "미실행"] if embedder == "fake" else ["미실행", str(group[metric])]
                lines.append(f"| {method} | {alpha} | {k} | {kind} | {metric} | " + " | ".join(values) + " |")
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    text = "\n".join(lines)
    (out / "fusion.json").write_text(json.dumps({"results": results,
        "score_scales": {"vector": "cosine", "lex": "term match count", "rrf": "sum 1/(k+rank)",
                         "weighted": "alpha*(cosine+1)/2 + (1-alpha)*lex/max_lex"}}, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "fusion.md").write_text(text, encoding="utf-8")
    (out / "fusion.html").write_text('<!doctype html><meta charset="utf-8"><title>E7 fusion</title><pre>' + html.escape(text) + '</pre>', encoding="utf-8")
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--set", required=True)
    ap.add_argument("--embedder", choices=["fake", "e5", "bge-m3"], default="fake")
    ap.add_argument("--alphas", nargs="+", type=float, default=[.25, .5, .75])
    ap.add_argument("--rrf-ks", nargs="+", type=int, default=[10,60,100])
    ap.add_argument("--out", default=".runs/e7")
    ap.add_argument("--chunk-size", type=int)
    ap.add_argument("--overlap", type=int, default=0)
    ap.add_argument("--instruction", default="default")
    args = ap.parse_args(argv)
    if not Path(args.out).resolve().is_relative_to(ROOT / ".runs"):
        ap.error("results must be inside .runs")
    compare(args.set, args.out, args.embedder, args.alphas, args.rrf_ks,
            chunk_size=args.chunk_size, overlap=args.overlap, instruction=args.instruction)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
