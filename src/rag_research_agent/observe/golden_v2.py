"""Read-only graded retrieval evaluation with quote provenance and seeded intervals."""
from __future__ import annotations

MATURITY = "incubating"

import json
import math
from pathlib import Path
import random
import re
from statistics import mean
from rag_research_agent.observe.golden import assign_splits, expected_ids

ROOT = Path(__file__).resolve().parents[3]
TYPES = {"paraphrase", "legal_term", "multi_hop", "numeric_condition", "temporal", "negation", "comparison",
         "colloquial", "typo", "procedural", "evidence_scope", "off_topic", "hard_negative", "outdated_premise", "injection"}
METRICS = ("hit", "recall", "mrr", "ndcg", "false_accept", "false_refusal", "e2e_recall", "overlap", "policy_match")


def validate(items, corpus):
    by_id = {doc["id"]: doc["text"] for doc in corpus}
    if len(by_id) != len(corpus):
        raise ValueError("duplicate corpus ID")
    ids = set()
    for item in items:
        if not isinstance(item.get("id"), str) or not item["id"] or item["id"] in ids:
            raise ValueError("missing or duplicate question ID")
        ids.add(item["id"])
        if not isinstance(item.get("question"), str) or not item["question"].strip():
            raise ValueError("empty question")
        if item.get("type") not in TYPES or item.get("split") not in ("compare", "confirm"):
            raise ValueError("invalid type or split")
        relevant = item.get("relevant")
        if not isinstance(relevant, list) or type(item.get("answerable")) is not bool or item["answerable"] != bool(relevant):
            raise ValueError("answerable and relevant disagree")
        seen = set()
        for evidence in relevant:
            source, quote, grade = evidence.get("source"), evidence.get("quote", ""), evidence.get("grade")
            if source not in by_id or not isinstance(quote, str) or (quote and quote not in by_id[source]):
                raise ValueError("quote/source does not match corpus")
            if type(grade) is not int or grade not in (1, 2):
                raise ValueError("grade must be 1 or 2")
            if (source, quote) in seen:
                raise ValueError("duplicate relevance unit")
            seen.add((source, quote))
        if item["type"] == "injection" and item.get("expect_status") not in ("BLOCKED", "OK", "REQUEST_MORE"):
            raise ValueError("injection needs expect_status")
    return items


def load(path, corpus=None):
    path = Path(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    if corpus is None:
        name = raw.get("corpus", "data/articles.json") if isinstance(raw, dict) else "data/articles.json"
        relative = path.parent / name
        corpus = json.loads((relative if relative.exists() else ROOT / name).read_text(encoding="utf-8"))
    if isinstance(raw, list):
        items = [{"id": item.get("id", f"v1-{n:03d}"), "question": item["question"], "type": item["type"],
                  "split": item["split"], "answerable": bool(expected_ids(item)),
                  "relevant": [{"source": source, "grade": 2, "quote": ""} for source in expected_ids(item)]}
                 for n, item in enumerate(assign_splits(raw), 1)]
        name = path.stem
    elif isinstance(raw, dict) and raw.get("schema") == "golden-retrieval/2":
        items, name = raw["items"], raw.get("name", path.stem)
    else:
        raise ValueError("unknown golden schema")
    validate(items, corpus)
    return {"name": name, "items": items, "corpus": corpus}


def bootstrap_ci(values, seed=0, samples=1000):
    values = [v for v in values if v is not None]
    if not values:
        return None
    if samples < 1:
        raise ValueError("samples must be positive")
    rng = random.Random(seed)
    means = sorted(mean(rng.choices(values, k=len(values))) for _ in range(samples))
    return [means[int((samples - 1) * 0.025)], means[int((samples - 1) * 0.975)]]


def score_item(item, hits, accepted=False, k=3, kept_texts=None, policy_status=None):
    if k < 1:
        raise ValueError("k must be positive")
    if item["type"] == "injection":
        return {"id": item["id"], "type": item["type"], "split": item["split"],
                **dict.fromkeys(METRICS), "policy_status": policy_status or "정책 미연결",
                "policy_match": float(policy_status == item["expect_status"]) if policy_status else None}
    relevant, found, gained, gains, first = item["relevant"], set(), set(), [], None
    for rank, hit in enumerate(hits, 1):
        matches = {i for i, evidence in enumerate(relevant) if hit["source"] == evidence["source"]
                   and (not evidence.get("quote") or evidence["quote"] in hit["text"])}
        if matches and first is None:
            first = rank
        if rank <= k:
            found |= matches
            fresh = matches - gained
            gains.append(max((2 ** relevant[i]["grade"] - 1 for i in fresh), default=0))
            gained |= matches
    ideal = sorted([2 ** evidence["grade"] - 1 for evidence in relevant], reverse=True)[:k]
    dcg = sum(value / math.log2(rank + 1) for rank, value in enumerate(gains, 1))
    idcg = sum(value / math.log2(rank + 1) for rank, value in enumerate(ideal, 1))
    quote_units = [i for i, evidence in enumerate(relevant) if evidence.get("quote")]
    words = lambda text: set(re.findall(r"\w+", text.lower()))
    question_words = words(item["question"])
    quote_words = words(" ".join(e["quote"] for e in relevant if e.get("quote")))
    answerable = item["answerable"]
    return {"id": item["id"], "type": item["type"], "split": item["split"],
            "hit": float(bool(found)) if answerable else None,
            "recall": len(found) / len(relevant) if relevant else None,
            "mrr": 1 / first if first else 0.0 if answerable else None,
            "ndcg": dcg / idcg if idcg else None,
            "false_accept": float(accepted) if not answerable else None,
            "false_refusal": float(not accepted) if answerable else None,
            "e2e_recall": sum(i in found and any(relevant[i]["quote"] in text for text in kept_texts)
                              for i in quote_units) / len(quote_units) if quote_units and kept_texts is not None else None,
            "overlap": len(question_words & quote_words) / len(question_words) if question_words and quote_words else None,
            "policy_match": None}


def report(rows, seed=0, samples=1000):
    def aggregate(group):
        result = {"count": len(group)}
        for key in METRICS:
            values = [row[key] for row in group if row.get(key) is not None]
            result[key] = {"mean": mean(values) if values else None, "n": len(values),
                           "ci95": bootstrap_ci(values, seed, samples)}
        return result
    return {"overall": aggregate(rows),
            "by_type": {key: aggregate([r for r in rows if r["type"] == key]) for key in sorted({r["type"] for r in rows})},
            "by_split": {key: aggregate([r for r in rows if r["split"] == key]) for key in sorted({r["split"] for r in rows})},
            "rows": rows, "seed": seed, "bootstrap_samples": samples,
            "note": "합성 소규모 골든셋, 통계적 결론 아님. quote 없음은 문서 단위, 끝-끝은 quote 있는 문항만."}
