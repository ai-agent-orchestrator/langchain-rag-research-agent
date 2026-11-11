"""Synthetic event path tests through the real RunEvent and audit function."""
from copy import deepcopy
import json

import pytest

from rag_research_agent.core.run_events import RunEvent
from rag_research_agent.rag.guard_audit import GoldEvidence, aggregate_guard_audit


def event(run_id="run-a1", domain="research", docs_in=4, docs_kept=3, guard=()):
    return RunEvent(
        run_id=run_id, domain=domain, track="deep", config="graph_full",
        dataset="synthetic", sha="abc1234", path=("grade", "verify"),
        end_type="END", loops={"rewrite": 0, "gap": 0, "verify": 0},
        calls={"slm": 0, "flagship": 0}, tokens={"in": 0, "out": 0},
        cost_krw=0, ttft_ms=0, total_ms=0,
        grade={"docs_in": docs_in, "docs_kept": docs_kept,
               "relevance_drop_rate": (docs_in - docs_kept) / docs_in if docs_in else 0},
        guard=guard, nodes=(), estimated=True,
    )


def issue(code, reason="누락", gate="grounded"):
    return {"gate": gate, "code": code, "reason": reason, "span": ""}


def test_document_weighted_rate_and_wilson():
    result = aggregate_guard_audit([event(docs_in=2, docs_kept=0),
                                   event("run-b2", docs_in=8, docs_kept=8)])
    row = result["research"]
    assert row["runs"] == row["quality_runs"] == 2
    assert row["grade"]["docs_in"] == 10
    assert row["grade"]["docs_kept"] == 8
    ratio = row["grade"]["relevance_drop_rate"]
    assert (ratio["count"], ratio["total"], ratio["rate"]) == (2, 10, .2)
    assert ratio["wilson95"] == pytest.approx([.0566821515, .5098375285])


def test_codes_and_reason_occurrences_are_preserved_across_gates():
    guards = (issue("UNSUPPORTED_NUMBER", "수치 불일치"),
              issue("GAP:sales", "매출 누락", "filter"),
              issue("GAP:sales", "매출 누락", "filter"),
              issue("GAP:cost", "비용 누락", "filter"))
    row = aggregate_guard_audit([event(guard=guards)])["research"]
    assert row["guard"] == {
        "UNSUPPORTED_NUMBER": {"count": 1, "reason": ["수치 불일치"]},
        "GAP:sales": {"count": 2, "reason": ["매출 누락", "매출 누락"]},
        "GAP:cost": {"count": 1, "reason": ["비용 누락"]},
    }


def test_gold_overblocking_uses_only_graded_auxiliary_evidence():
    labels = GoldEvidence(("doc-a1", "doc-b2", "doc-z9"),
                          ("doc-a1", "doc-b2", "doc-c3"), ("doc-b2", "doc-c3"))
    row = aggregate_guard_audit(
        [event(docs_in=3, docs_kept=2), event("run-b2", docs_in=9, docs_kept=0)],
        gold={"run-a1": labels})["research"]["overblocking"]
    assert row["gold_runs"] == 1
    assert (row["count"], row["total"], row["rate"]) == (1, 2, .5)
    assert row["wilson95"][0] < .5 < row["wilson95"][1]


def test_gold_signal_is_document_weighted_across_runs():
    gold = {
        "run-a1": GoldEvidence(("doc-a1",), ("doc-a1",), ()),
        "run-b2": GoldEvidence(("doc-b2", "doc-c3", "doc-d4"),
                               ("doc-b2", "doc-c3", "doc-d4"),
                               ("doc-b2", "doc-c3", "doc-d4")),
    }
    row = aggregate_guard_audit([event(docs_in=1, docs_kept=0),
                                event("run-b2", docs_in=3, docs_kept=3)], gold=gold)
    assert row["research"]["overblocking"]["rate"] == .25
    assert row["research"]["overblocking"]["total"] == 4


def test_empty_input():
    assert aggregate_guard_audit(iter(())) == {}


def test_mixed_domains_stay_separate():
    rows = aggregate_guard_audit([event(), event("run-b2", "legal", 2, 0,
                                              (issue("UNSUPPORTED_STATUTE"),))])
    assert set(rows) == {"research", "legal"}
    assert rows["research"]["grade"]["relevance_drop_rate"]["rate"] == .25
    assert rows["legal"]["grade"]["relevance_drop_rate"]["rate"] == 1
    assert rows["research"]["guard"] == {}
    assert rows["legal"]["guard"]["UNSUPPORTED_STATUTE"]["count"] == 1


def test_missing_gold_and_empty_grade_are_unmeasured():
    row = aggregate_guard_audit([event(docs_in=0, docs_kept=0)])["research"]
    empty = {"count": 0, "total": 0, "rate": None, "wilson95": None}
    assert row["grade"]["relevance_drop_rate"] == empty
    assert row["overblocking"] == {"gold_runs": 0, **empty}


def test_gold_with_no_auxiliary_candidates_is_unmeasured():
    labels = GoldEvidence(("doc-z9",), ("doc-a1",), ())
    row = aggregate_guard_audit([event(docs_in=1, docs_kept=0)],
                               gold={"run-a1": labels})["research"]["overblocking"]
    assert row["gold_runs"] == 1 and row["total"] == 0 and row["rate"] is None


def test_zero_observed_overblocking_is_not_a_guarantee():
    labels = GoldEvidence(("doc-a1",), ("doc-a1",), ("doc-a1",))
    row = aggregate_guard_audit([event(docs_in=1, docs_kept=1)],
                               gold={"run-a1": labels})["research"]["overblocking"]
    assert row["rate"] == 0 and row["wilson95"][1] > 0


def test_injection_is_excluded_from_both_quality_denominators():
    rows = aggregate_guard_audit(
        [event(), event("run-inj", docs_in=7, docs_kept=0,
                        guard=(issue("INJECTION", gate="filter"),))],
        gold={"run-inj": GoldEvidence(("doc-a1",), ("doc-a1",), ())},
        injection_run_ids=("run-inj",))
    row = rows["research"]
    assert row["runs"] == 2 and row["quality_runs"] == 1
    assert row["grade"]["docs_in"] == 4
    assert row["guard"]["INJECTION"]["count"] == 1
    assert row["overblocking"]["gold_runs"] == 0


def test_mapping_codec_generator_and_purity():
    payload = json.loads(event(guard=(issue("GAP:sales"),)).to_json(dumps=json.dumps))
    original = deepcopy(payload)
    rows = aggregate_guard_audit(iter([payload]))
    rows["research"]["guard"]["GAP:sales"]["reason"].append("別")
    assert payload == original
    assert aggregate_guard_audit([payload]) == aggregate_guard_audit([RunEvent(**payload)])


def test_duplicate_runs_are_rejected():
    with pytest.raises(ValueError, match="duplicate run_id"):
        aggregate_guard_audit([event(), event()])


@pytest.mark.parametrize("labels", [
    (("doc-a1", "doc-a1"), (), ()),
    ((), ("doc-a1",), ("doc-b2",)),
    (("",), (), ()),
])
def test_invalid_gold_is_rejected(labels):
    with pytest.raises(ValueError):
        GoldEvidence(*labels)


def test_gold_count_mismatch_is_rejected():
    with pytest.raises(ValueError, match="counts must match"):
        aggregate_guard_audit([event()], gold={"run-a1": GoldEvidence((), (), ())})


def test_invalid_event_is_validated_by_real_class():
    payload = json.loads(event().to_json(dumps=json.dumps))
    payload["grade"]["docs_kept"] = 5
    with pytest.raises(ValueError):
        aggregate_guard_audit([payload])
