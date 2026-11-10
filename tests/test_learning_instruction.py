import pytest
from rag_research_agent.observe.experiments import QueryInstruction, score_summary


class Recorder:
    model_id = "e5"

    def encode_documents(self, texts):
        self.last = texts
        return [[1]]

    def encode_query(self, text):
        self.last = ["default:" + text]
        return [1]


def test_query_prefix_ablation_and_bge_control():
    base = Recorder()
    for option, expected in [("default", "default:q"), ("none", "q"), ("custom:retrieve", "Instruct: retrieve\nQuery: q")]:
        QueryInstruction(base, option).encode_query("q")
        assert base.last == [expected]
    base.model_id = "BAAI/bge-m3"
    QueryInstruction(base, "custom:retrieve").encode_query("q")
    assert base.last == ["q"]
    with pytest.raises(ValueError):
        QueryInstruction(base, "custom:")


def test_multi_source_recall_and_negative_margin_separate_fake_column():
    rows = [{"expected": ["a", "b"], "correct_score": .8, "recall_at_3": .5, "reciprocal_rank": .5, "vector": {"top1": .8}},
            {"expected": [], "vector": {"top1": .3}}]
    result = score_summary(rows, True)
    assert result["real_model"] is None
    assert result["path_test"]["recall_at_3"] == .5
    assert result["path_test"]["correct_no_evidence_margin"] == pytest.approx(.5)
