"""LAB: compare embedding models on a golden set instead of choosing by feel.

Golden set: [{"question": "...", "source": "제1조", "type": "paraphrase"?}, ...]
Corpus:     [{"id": "제1조", "text": "..."}, ...]

For each model the same corpus and questions are encoded (documents without a query
instruction, questions through encode_query), and we count:
  top1 = questions whose 1st result is the gold source
  top3 = questions whose gold source is within the first 3 results
Counts are reported as "n/total" because golden sets are small; per-question ranks are kept
so disagreements between models can be read one by one.
"""
from __future__ import annotations

MATURITY = "lab"

import json
import time
from pathlib import Path
from typing import Mapping, Sequence


def load_json(path: str | Path) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data["items"] if isinstance(data, dict) and "items" in data else data


def validate(golden: Sequence[dict], corpus: Sequence[dict]) -> None:
    ids = [c["id"] for c in corpus]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate corpus id")
    unknown = sorted({g["source"] for g in golden} - set(ids))
    if unknown:
        raise ValueError(f"golden sources missing from corpus: {unknown}")
    if any(not g["question"].strip() for g in golden):
        raise ValueError("empty question")


def evaluate_model(embedder, golden: Sequence[dict], corpus: Sequence[dict], k: int = 3) -> dict:
    validate(golden, corpus)
    t0 = time.monotonic()
    doc_vectors = embedder.encode_documents([c["text"] for c in corpus])
    doc_ms = (time.monotonic() - t0) * 1000
    items, query_ms = [], []
    for g in golden:
        t1 = time.monotonic()
        q = embedder.encode_query(g["question"])
        query_ms.append((time.monotonic() - t1) * 1000)
        scored = sorted(((sum(a * b for a, b in zip(q, v)), c["id"]) for v, c in zip(doc_vectors, corpus)),
                        key=lambda x: (-x[0], x[1]))
        ranking = [cid for _, cid in scored]
        rank = ranking.index(g["source"]) + 1
        items.append({"question": g["question"], "source": g["source"], "type": g.get("type", "-"),
                      "rank": rank, "top": ranking[:k], "top1_score": round(scored[0][0], 4),
                      "gold_score": round(scored[rank - 1][0], 4)})
    total = len(items)
    by_type: dict[str, list[int]] = {}
    for it in items:
        cell = by_type.setdefault(it["type"], [0, 0, 0])
        cell[0] += it["rank"] == 1
        cell[1] += it["rank"] <= k
        cell[2] += 1
    return {"model": embedder.model_id, "revision": embedder.revision,
            "top1": f"{sum(i['rank'] == 1 for i in items)}/{total}",
            f"top{k}": f"{sum(i['rank'] <= k for i in items)}/{total}",
            "mrr": round(sum(1 / i["rank"] for i in items) / total, 4),
            "by_type": {t: {"top1": f"{a}/{n}", f"top{k}": f"{b}/{n}"} for t, (a, b, n) in by_type.items()},
            "doc_encode_ms": round(doc_ms, 1), "median_query_ms": round(sorted(query_ms)[len(query_ms) // 2], 2),
            "items": items}


def compare(embedders: Mapping[str, object], golden: Sequence[dict], corpus: Sequence[dict], k: int = 3) -> dict:
    results = {name: evaluate_model(e, golden, corpus, k) for name, e in embedders.items()}
    disagreements = []
    for i, g in enumerate(golden):
        ranks = {name: r["items"][i]["rank"] for name, r in results.items()}
        if len({min(v, k + 1) for v in ranks.values()}) > 1:
            disagreements.append({"question": g["question"], "source": g["source"], "ranks": ranks})
    return {"k": k, "questions": len(golden), "documents": len(corpus), "results": results,
            "disagreements": disagreements}


def to_markdown(report: dict) -> str:
    k = report["k"]
    lines = [f"# Embedding comparison ({report['questions']} questions, {report['documents']} documents)", "",
             f"| model | revision | 1위 정답 | {k}위 안 정답 | MRR | 문서 인코딩 ms | 질문 중앙값 ms |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for name, r in report["results"].items():
        lines.append(f"| {name} | {r['revision']} | {r['top1']} | {r[f'top{k}']} | {r['mrr']} | "
                     f"{r['doc_encode_ms']} | {r['median_query_ms']} |")
    if report["disagreements"]:
        lines += ["", "모델 간 결과가 갈린 질문", "", "| 질문 | 정답 | 순위 |", "| --- | --- | --- |"]
        for d in report["disagreements"]:
            ranks = ", ".join(f"{n}: {v}" for n, v in d["ranks"].items())
            lines.append(f"| {d['question']} | {d['source']} | {ranks} |")
    return "\n".join(lines) + "\n"


def from_legal_intake(eval_items: Sequence[dict], guides_dir: Path, guides_manifest: dict) -> tuple[list[dict], list[dict]]:
    """Convert the legal-intake eval set (evidence items only) into golden + corpus form."""
    corpus = [{"id": d["documentId"], "text": (guides_dir / d["file"]).read_text(encoding="utf-8")}
              for d in guides_manifest["documents"]]
    golden = []
    for it in eval_items:
        if not it["expected"]:
            continue
        intake = it["intake"]
        question = "\n".join(p for p in (intake["caseType"], intake["coreStatement"], intake.get("desiredNextStep")) if p)
        golden.append({"question": question, "source": it["expected"][0], "type": it["type"], "split": it["split"]})
    return golden, corpus
