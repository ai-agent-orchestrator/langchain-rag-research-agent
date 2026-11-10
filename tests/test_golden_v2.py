import copy
import json
import math
import pytest

from rag_research_agent.observe.golden_v2 import validate, score_item, report, bootstrap_ci, load
from scripts.eval_retrieval_v2 import evaluate
from test_compare_embedders import FakeIndexLibrary

CORPUS = [{"id": "one", "title": "one", "text": "핵심은 합성 비용이다."}, {"id": "two", "title": "two", "text": "합성 계약 자료다."}]
ITEM = {"id": "q1", "question": "합성 비용", "type": "multi_hop", "split": "compare", "answerable": True,
        "relevant": [{"source": "one", "grade": 2, "quote": "핵심은 합성 비용이다."}, {"source": "two", "grade": 1, "quote": "합성 계약 자료다."}]}


def test_grade_quote_split_and_duplicate_validation():
    assert validate([ITEM], CORPUS)
    for key, value in [("quote", "not in source"), ("grade", 3)]:
        bad = copy.deepcopy(ITEM)
        bad["relevant"][0][key] = value
        with pytest.raises(ValueError):
            validate([bad], CORPUS)
    with pytest.raises(ValueError, match="duplicate"):
        validate([ITEM, ITEM], CORPUS)
    bad = {**ITEM, "split": "wrong"}
    with pytest.raises(ValueError, match="split"):
        validate([bad], CORPUS)


def test_hand_computed_ranking_and_intervals():
    hits = [{"source": "two", "text": CORPUS[1]["text"]}, {"source": "one", "text": CORPUS[0]["text"]}]
    row = score_item(ITEM, hits, True, 2, [CORPUS[0]["text"]])
    assert row["hit"] == row["recall"] == row["mrr"] == 1
    expected = (1 + 3 / math.log2(3)) / (3 + 1 / math.log2(3))
    assert row["ndcg"] == pytest.approx(expected) and row["e2e_recall"] == 0.5
    assert bootstrap_ci([0, 1, 0.5], seed=7) == bootstrap_ci([0, 1, 0.5], seed=7)
    assert report([row])["by_type"]["multi_hop"]["count"] == 1
    quote_miss = score_item(ITEM, [{"source": "one", "text": "other chunk"}], False)
    assert quote_miss["hit"] == 0


def test_v1_conversion_and_fake_e2e_pipeline(tmp_path):
    legacy = tmp_path / "v1.json"
    legacy.write_text(json.dumps([{"question": "합성 비용", "source": "one", "type": "paraphrase"}]))
    assert load(legacy, CORPUS)["items"][0]["relevant"][0]["quote"] == ""
    path = tmp_path / "v2.json"
    injection = {"id": "attack", "question": "[BLOCK] 합성", "type": "injection", "split": "confirm", "answerable": False,
                 "relevant": [], "expect_status": "BLOCKED"}
    path.write_text(json.dumps({"name": "synthetic", "schema": "golden-retrieval/2", "items": [ITEM, injection]}))
    result = evaluate(path, e2e=True, out=tmp_path / "out", corpus=CORPUS, library_factory=FakeIndexLibrary, policy=None)
    assert result["overall"]["e2e_recall"]["n"] == 1
    assert result["rows"][1]["policy_status"] == "정책 미연결"
    assert (tmp_path / "out/report.html").is_file()
