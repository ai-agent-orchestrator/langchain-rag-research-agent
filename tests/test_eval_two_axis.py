"""Two-axis evaluation (rank vs gate decision), frozen-rule enforcement, golden-set checks."""
import json
import math
from pathlib import Path

import pytest

from memvid_guardrail.embed.providers import FakeEmbedder
from memvid_guardrail.observe import golden
from memvid_guardrail.observe.evaluate import (FrozenRuleViolation, confirm, freeze_rule, outcome,
                                               two_axis_report)

DATA = Path(__file__).resolve().parents[1] / "data"


def row(id_, expected, topk, top1, gap, split="compare", type_="paraphrase"):
    return {"id": id_, "split": split, "type": type_, "expected": expected,
            "vector": {"topk": topk, "top1": top1, "gap": gap}}


RULE = {"tau_abs": 0.5, "tau_gap": 0.05}


def test_found_but_refused_is_reported_separately_from_ranking():
    # The Q22 case: the right document is first, but its gap is below the frozen threshold.
    r = row("Q22", ["D1"], ["D1", "D2", "D3"], 0.82, 0.01, split="confirm")
    rep = two_axis_report([r], "vector", RULE)
    assert rep["ranking"]["hit_at_1"] == "1/1" and rep["decision"]["found_refused"] == 1
    assert rep["attention"] == ["Q22"] and rep["rows"][0]["first_hit_rank"] == 1


def test_every_outcome_is_named():
    cases = {
        "found_accepted": row("a", ["D1"], ["D1"], 0.9, 0.2),
        "found_refused": row("b", ["D1"], ["D1"], 0.4, 0.2),
        "wrong_accepted": row("c", ["D1"], ["D2", "D1"], 0.9, 0.2),
        "wrong_refused": row("d", ["D1"], ["D2"], 0.3, 0.0),
        "no_evidence_accepted": row("e", [], ["D2"], 0.9, 0.2),
        "no_evidence_refused": row("f", [], ["D2"], 0.2, 0.0),
    }
    for name, r in cases.items():
        assert outcome(r, "vector", RULE) == name
    rep = two_axis_report(list(cases.values()), "vector", RULE)
    assert rep["ranking"] == {"hit_at_1": "2/4", "hit_at_3": "3/4", "mrr": round((1 + 1 + 0.5 + 0) / 4, 4)}
    assert set(rep["attention"]) == {"b", "c", "e"}


def test_rule_is_frozen_on_compare_and_confirm_refuses_reuse():
    compare = [row("c1", ["D1"], ["D1"], 0.9, 0.3), row("c2", [], ["D2"], 0.4, 0.1),
               row("c3", ["D2"], ["D2"], 0.7, 0.2)]
    rule = freeze_rule(compare, "vector", "v1")
    assert rule["calibrated_on"] == ["c1", "c2", "c3"] and rule["version"] == "v1"
    with pytest.raises(FrozenRuleViolation):
        freeze_rule([row("k1", ["D1"], ["D1"], 0.9, 0.3, split="confirm")], "vector", "v1")
    with pytest.raises(FrozenRuleViolation):
        confirm(compare, rule)  # tuning rows are not confirmation rows
    with pytest.raises(FrozenRuleViolation):
        confirm([row("k1", ["D1"], ["D1"], 0.9, 0.3, split="confirm")], RULE)  # not frozen
    rep = confirm([row("k1", ["D1"], ["D1"], 0.9, 0.3, split="confirm")], rule)
    assert rep["rule"]["version"] == "v1" and rep["decision"]["found_accepted"] == 1


def test_repo_golden_files_load_and_reach_the_no_evidence_share():
    articles = json.loads((DATA / "articles.json").read_text(encoding="utf-8"))
    items = golden.load([DATA / "golden_set.json", DATA / "golden_no_evidence.json"],
                        [a["id"] for a in articles], min_no_evidence=0.3)
    assert len(items) == 29 and sum(not golden.expected_ids(i) for i in items) == 9
    split = golden.assign_splits(items)
    for part in ("compare", "confirm"):
        chosen = [i for i in split if i["split"] == part]
        assert any(golden.expected_ids(i) for i in chosen) and any(not golden.expected_ids(i) for i in chosen)


def test_golden_checks_catch_common_mistakes(tmp_path):
    def write(items):
        path = tmp_path / "g.json"
        path.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
        return [path]
    with pytest.raises(golden.GoldenSetError):
        golden.load(write([{"question": "q", "source": "제99조", "type": "paraphrase"}]), ["제1조"])
    with pytest.raises(golden.GoldenSetError):
        golden.load(write([{"question": "q", "source": "제1조", "type": "paraphrase"}] * 2), ["제1조"])
    with pytest.raises(golden.GoldenSetError):
        golden.load(write([{"question": "q", "source": None, "type": "paraphrase"}]), ["제1조"])
    with pytest.raises(golden.GoldenSetError):
        golden.load(write([{"question": "q", "source": "제1조", "type": "paraphrase"}]), ["제1조"],
                    min_no_evidence=0.3)


def test_end_to_end_with_the_fake_embedder_on_repo_data():
    """Fake (character n-gram) embedder: a keyword-level baseline, not a semantic result."""
    articles = json.loads((DATA / "articles.json").read_text(encoding="utf-8"))
    items = golden.assign_splits(golden.load([DATA / "golden_set.json", DATA / "golden_no_evidence.json"],
                                             [a["id"] for a in articles]))
    emb = FakeEmbedder(dimension=256)
    doc_vecs = emb.encode_documents([a["text"] for a in articles])

    def rank(question):
        q = emb.encode_query(question)
        scores = [(a["id"], sum(x * y for x, y in zip(q, v))) for a, v in zip(articles, doc_vecs)]
        return sorted(scores, key=lambda s: s[1], reverse=True)
    rows = golden.to_rows(items, rank, "vector")
    rule = freeze_rule([r for r in rows if r["split"] == "compare"], "vector", "fake-v1")
    rep = confirm([r for r in rows if r["split"] == "confirm"], rule)
    total = sum(rep["decision"].values())
    assert total == len([r for r in rows if r["split"] == "confirm"])
    assert all(math.isfinite(p["top1"]) for p in rep["rows"])
