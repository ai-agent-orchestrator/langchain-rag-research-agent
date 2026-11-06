import json
from pathlib import Path

import pytest

from memvid_guardrail.embed.providers import FakeEmbedder
from memvid_guardrail.lab.golden import compare, evaluate_model, from_legal_intake, load_json, to_markdown, validate

pytestmark = pytest.mark.lab
FIX = Path(__file__).resolve().parent / "fixtures"
GOLDEN = load_json(FIX / "golden_example" / "golden_set.json")
CORPUS = load_json(FIX / "golden_example" / "articles.json")


class Oracle:
    """Puts each gold source first: proves the counting, not a model."""
    model_id, revision, dimension, normalization = "oracle", "v1", 5, "l2"

    def encode_documents(self, texts):
        return [[1.0 if i == j else 0.0 for j in range(5)] for i in range(len(texts))]

    def encode_query(self, text):
        source = next(g["source"] for g in GOLDEN if g["question"] == text)
        i = [c["id"] for c in CORPUS].index(source)
        return [1.0 if j == i else 0.0 for j in range(5)]


def test_validation_catches_bad_sets():
    with pytest.raises(ValueError):
        validate([{"question": "q", "source": "제9조"}], CORPUS)
    with pytest.raises(ValueError):
        validate(GOLDEN, CORPUS + CORPUS[:1])


def test_counts_top1_top3_and_mrr():
    r = evaluate_model(Oracle(), GOLDEN, CORPUS)
    assert r["top1"] == "8/8" and r["top3"] == "8/8" and r["mrr"] == 1.0


def test_compare_lists_disagreements_and_renders_table():
    report = compare({"oracle": Oracle(), "fake": FakeEmbedder()}, GOLDEN, CORPUS)
    md = to_markdown(report)
    assert "1위 정답" in md and "3위 안 정답" in md and "| oracle |" in md
    assert all(d["ranks"]["oracle"] == 1 for d in report["disagreements"])


def test_legal_intake_conversion_uses_evidence_items_only():
    root = FIX / "synthetic_guides"
    manifest = json.loads((root / "guides.json").read_text(encoding="utf-8"))
    golden, corpus = from_legal_intake(load_json(root / "eval" / "intakes.json"), root, manifest)
    assert len(corpus) == 10 and len(golden) == 20
    validate(golden, corpus)


def test_repository_golden_set_shape():
    root = Path(__file__).resolve().parents[1] / "data"
    golden, corpus = load_json(root / "golden_set.json"), load_json(root / "articles.json")
    validate(golden, corpus)
    assert len(golden) == 20 and len(corpus) == 10
    from collections import Counter
    assert set(Counter(g["source"] for g in golden).values()) == {2}   # two questions per article
    assert {g["type"] for g in golden} == {"paraphrase", "legal_term"}
