"""Standalone offline evaluation through the real verifier and R42 graders."""
import json
from uuid import uuid4

import pytest

from scripts import groundedness_eval as ev
from rag_research_agent.rag.graders import FakeLLMGrader, GroundedGrade, RuleGrader


def case(name="case-a1", expected="pass", fault="none", text="매출은 18% 증가했다.", ids=None):
    return {"id": name, "expected": expected, "fault_type": fault,
            "evidence": [{"id": "claim-a1", "text": "매출은 18% 증가했다."}],
            "answer": [{"text": text, "claim_ids": ["claim-a1"] if ids is None else ids}]}


def grade(ok):
    return GroundedGrade(grounded=ok, reason="offline decision", unsupported=[] if ok else ["claim-a1"])


def test_fake_metrics_and_type_aggregation():
    cases = [case(), case("case-b1"),
             case("case-c1", "block", "causal_assertion"),
             case("case-d1", "block", "causal_assertion")]
    result = ev.evaluate(cases, FakeLLMGrader(grounded=[grade(True), grade(False), grade(False), grade(True)]))
    metrics = result["metrics"]
    for rate in (metrics["detection"], metrics["overblocking"], metrics["by_fault_type"]["causal_assertion"]):
        assert rate["count"] == 1 and rate["n"] == 2 and rate["rate"] == 0.5
        assert rate["wilson95"] == pytest.approx([0.09453120573423074, 0.9054687942657693])
    assert [r["end_type"] for r in result["rows"]] == ["END", "give_up", "give_up", "END"]


def test_rule_grader_and_real_verifier_detect_number_and_uncited():
    cases = [case(), case("bad-a1", "block", "altered_number", "매출은 28% 증가했다."),
             case("bad-b1", "block", "uncited", ids=[])]
    result = ev.evaluate(cases, RuleGrader())
    assert result["metrics"]["detection"]["count"] == 2
    assert result["metrics"]["overblocking"]["count"] == 0
    assert "UNSUPPORTED_NUMBER" in result["rows"][1]["codes"]
    assert "MISQUOTED" in result["rows"][1]["codes"]
    assert "UNCITED" in result["rows"][2]["codes"]


def test_verifier_cannot_be_overridden_by_fake_approval():
    result = ev.evaluate([case("bad-a1", "block", "uncited", ids=[])],
                         FakeLLMGrader(grounded=[grade(True)]))
    assert result["rows"][0]["blocked"]
    assert result["metrics"]["by_fault_type"]["uncited"]["count"] == 1


def test_real_balance_check_uses_evidence_stance():
    item = case("balance-a1", "block", "one_sided")
    item["evidence"][0]["stance"] = "pro"
    item["evidence"].append({"id": "claim-b1", "text": "비용은 12% 증가했다.", "stance": "con"})
    row = ev.evaluate([item], FakeLLMGrader(grounded=[grade(True)]))["rows"][0]
    assert "ONE_SIDED" in row["codes"]


def test_empty_set_has_undefined_rates_and_intervals():
    result = ev.evaluate([], FakeLLMGrader())
    assert result["rows"] == []
    for metric in [result["metrics"]["detection"], result["metrics"]["overblocking"],
                   *result["metrics"]["by_fault_type"].values()]:
        assert metric == {"count": 0, "n": 0, "rate": None, "wilson95": None}


def test_fake_exhaustion_propagates():
    with pytest.raises(StopIteration):
        ev.evaluate([case()], FakeLLMGrader())


@pytest.mark.parametrize("field,value", [("expected", "yes"), ("fault_type", "unknown"),
                                         ("answer", []), ("evidence", "text")])
def test_invalid_dataset_rejected(field, value):
    item = case()
    item[field] = value
    with pytest.raises(ValueError):
        ev.evaluate([item], FakeLLMGrader())


def test_duplicate_case_ids_rejected():
    with pytest.raises(ValueError, match="unique"):
        ev.validate_cases([case(), case()])


def test_gold_labels_do_not_control_judgment():
    normal = case()
    faulty = case("case-b1", "block", "causal_assertion")
    rows = ev.evaluate([normal, faulty], RuleGrader())["rows"]
    assert rows[0]["blocked"] == rows[1]["blocked"] == False
    assert rows[0]["grade"] == rows[1]["grade"]


def test_shipped_dataset_counts_and_real_execution():
    cases = ev.validate_cases(json.loads(ev.CASES.read_text(encoding="utf-8")))
    assert len(cases) == 40
    assert sum(c["expected"] == "pass" for c in cases) == 15
    assert sum(c["expected"] == "block" for c in cases) == 25
    assert {kind: sum(c["fault_type"] == kind for c in cases) for kind in ev.FAULTS} == {
        "none": 15, "invented_number": 5, "altered_number": 5,
        "invented_statute": 4, "causal_assertion": 4, "one_sided": 4, "uncited": 3}
    assert len(ev.evaluate(cases, RuleGrader())["rows"]) == 40


def test_cli_appends_and_separates_fake_path_test(monkeypatch):
    # All test result artifacts remain under .runs, including this fixture.
    folder = ev.ROOT / ".runs/groundedness" / ("test-" + str(uuid4()))
    folder.mkdir(parents=True)
    input_path, output_path = folder / "cases.json", folder / "runs.jsonl"
    input_path.write_text(json.dumps([case()], ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(ev, "OUT", output_path)
    ev.main(["--cases", str(input_path), "--grader", "fake"])
    ev.main(["--cases", str(input_path), "--grader", "rule"])
    records = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
    assert [r["evaluation_kind"] for r in records] == ["fake_path_test", "rule_synthetic"]
    assert len({r["run_id"] for r in records}) == 2
    assert all(r["model_calls"] == 0 and not r["graph_executed"] for r in records)
    assert records[0]["cases_sha256"] == records[1]["cases_sha256"]
    assert records[0]["rows"][0]["grade"]["reason"] == "FIXED_APPROVAL_PATH_TEST"
