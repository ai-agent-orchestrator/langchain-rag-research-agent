"""Synthetic legal pack contract and R18 -> R21 integration, entirely offline."""
from collections import Counter
from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import re

import pytest

from rag_research_agent.guard.legal_filter import LegalFilter
from scripts import domain_eval as de


ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "evals/domains/legal"
CASES, METRICS = de.load_pack("legal")
IDS = [case["id"] for case in CASES]
SAFETY_FIELDS = {
    "UNSUPPORTED_STATUTE": "unsupported_statutes",
    "REPEALED_CITED": "repealed_statutes",
    "TIMELINE_MIXED": "timeline_errors",
}


def verified_output(case):
    """Adapt real Issue counts to R21 list lengths; never trust stored safety lists.

    Lists contain diagnostic codes, one item per counted issue, not statute text.
    No gold fields participate in verification.
    """
    domain = LegalFilter()
    decision = domain.check_input(case["question"])
    assert decision.allowed and decision.branch == case["branch"]
    answer = case["output"]["answer"]
    verdict = domain.verify(answer, tuple(case["docs"].values()), decision.branch)
    output = {"answer": answer, **{key: [] for key in SAFETY_FIELDS.values()}}
    for issue in verdict.issues:
        assert issue.code in SAFETY_FIELDS, issue.code
        output[SAFETY_FIELDS[issue.code]].extend([issue.code] * issue.count)
    return output


def test_pack_loads_through_r21_and_has_requested_distribution():
    data = json.loads((PACK / "cases.json").read_text(encoding="utf-8"))
    assert data["schema_version"] == 1 and data["synthetic"] is True
    assert len(CASES) == len(set(IDS)) == 8
    assert Counter(c["branch"] for c in CASES) == {"criminal": 3, "civil": 3, "family": 2}
    assert all(c["split"] == "compare" for c in CASES)
    assert de.validate_metrics(METRICS) == METRICS
    assert len(METRICS) == 4
    assert [m["name"] for m in METRICS if not m["safety"]] == ["required_statute_coverage"]
    assert {m["field"] for m in METRICS if m["safety"]} == set(SAFETY_FIELDS.values())


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_case_schema_and_gold_evidence_consistency(case):
    assert re.fullmatch(r"legal-[a-z]+-[a-z]\d+", case["id"])
    assert isinstance(case["question"], str) and "가상" in case["question"]
    docs, gold = case["docs"], case["gold"]
    assert isinstance(docs, dict) and len(docs) >= 3
    assert all(re.fullmatch(r"doc-[a-z]\d+", key) for key in docs)
    assert all(isinstance(text, str) and text.strip() for text in docs.values())
    source = "\n".join(docs.values())
    statutes = set(re.findall(r"제\d+조", source))
    required = gold["required_statutes"]
    forbidden = gold["forbidden_citations"]
    assert len(required) == len(set(required)) == 2
    assert set(required) <= statutes
    assert forbidden["unsupported"] and forbidden["repealed"]
    assert not set(forbidden["unsupported"]) & statutes
    assert set(forbidden["repealed"]) <= statutes
    assert not set(required) & set(forbidden["repealed"])
    repealed_docs = [text for text in docs.values() if "[폐지]" in text]
    assert 1 <= len(repealed_docs) <= 2
    assert set(re.findall(r"제\d+조", "\n".join(repealed_docs))) == set(forbidden["repealed"])
    for text in docs.values():
        if re.search(r"제\d+조", text):
            assert re.search(r"가상 .+ 제\d+조\([^)]+\)", text)
    for citation in required + forbidden["unsupported"] + forbidden["repealed"]:
        assert re.fullmatch(r"제\d+조", citation) and int(citation[1:-1]) >= 900
    timeline = gold["timeline"]
    dates = [event["date"] for event in timeline]
    assert len(dates) >= 2 and len(set(dates)) == len(dates)
    assert [date.fromisoformat(d) for d in dates] == sorted(date.fromisoformat(d) for d in dates)
    assert [source.index(d) for d in dates] == sorted(source.index(d) for d in dates)
    for event in timeline:
        assert event["date"] in docs[event["source_id"]] and event["event"]
        assert event["date"] in gold["answer"] and event["event"] in gold["answer"]
    assert all(citation in gold["answer"] for citation in required)
    assert not any(citation in gold["answer"] for values in forbidden.values() for citation in values)
    assert case["output"]["answer"] == gold["answer"]
    # The reference output's safety fields must agree with actual R18 verification.
    assert verified_output(case) == case["output"]


def test_reference_and_real_filter_outputs_agree_through_r21():
    reference = de.evaluate(CASES, METRICS)
    result = de.evaluate(CASES, METRICS, verified_output)
    assert result == reference
    assert result["n_cases"] == 8
    quality = result["quality_metrics"]["required_statute_coverage"]
    assert (quality["ok"], quality["n"]) == (16, 16)
    assert quality["wilson95"][0] < 1
    for stats in result["safety_metrics"].values():
        assert (stats["errors"], stats["n"], stats["count"]) == (0, 8, 0)
        assert stats["wilson95_upper"] > 0


@pytest.mark.parametrize("case", CASES, ids=IDS)
@pytest.mark.parametrize("fault", ["unsupported", "repealed", "timeline", "missing_required"])
def test_corrupted_answers_exercise_real_filter_and_metrics(case, fault):
    changed = deepcopy(case)
    gold = changed["gold"]
    if fault in {"unsupported", "repealed"}:
        changed["output"]["answer"] += " " + gold["forbidden_citations"][fault][0]
    elif fault == "timeline":
        changed["output"]["answer"] = " ".join(gold["required_statutes"]) + " " + " 이후 ".join(
            f"{event['date']} {event['event']}" for event in reversed(gold["timeline"]))
    else:
        changed["output"]["answer"] = changed["output"]["answer"].replace(gold["required_statutes"][0], "")
    # Stored zero lists are intentionally stale: the real verifier recomputes them.
    result = de.evaluate([changed], METRICS, verified_output)
    quality = result["quality_metrics"]["required_statute_coverage"]
    assert (quality["ok"], quality["n"]) == (1 if fault == "missing_required" else 2, 2)
    for name, stats in result["safety_metrics"].items():
        expected = int(name == {
            "unsupported": "unsupported_statute_count",
            "repealed": "repealed_statute_count",
            "timeline": "timeline_error_count",
        }.get(fault))
        assert (stats["errors"], stats["n"], stats["count"]) == (expected, 1, expected)


def test_arbitrary_unknown_citations_and_duplicate_counting():
    cases = deepcopy(CASES)
    # These citations are not the enumerated forbidden examples in gold.
    cases[0]["output"]["answer"] += " 제998조 제999조 제998조"
    result = de.evaluate(cases, METRICS, verified_output)
    stats = result["safety_metrics"]["unsupported_statute_count"]
    assert (stats["errors"], stats["n"], stats["count"]) == (1, 8, 2)
    assert stats["wilson95"][0] < stats["rate"] < stats["wilson95"][1]


def test_runner_writes_only_metrics_under_runs(tmp_path, monkeypatch):
    # All generated artifacts stay in .runs, including pytest's --basetemp.
    monkeypatch.setattr(de, "OUT", tmp_path / ".runs/domain_eval")
    result = de.run("legal", evaluator=verified_output)
    target = de.OUT / "legal/runs.jsonl"
    stored = json.loads(target.read_text(encoding="utf-8"))
    assert stored == result
    assert stored["domain"] == "legal" and stored["evaluation"] == "injected_evaluator"
    assert stored["n_cases"] == 8 and stored["split"] == "compare"
    assert all(set(row) == {"case", "metrics"} for row in stored["cases"])
    assert CASES[0]["question"] not in target.read_text(encoding="utf-8")


def test_pack_has_no_personal_identifier_shapes():
    text = (PACK / "cases.json").read_text(encoding="utf-8")
    assert not re.search(r"\d{10,}", text)
    assert not re.search(r"0\d{1,3}[- ]\d{3,4}[- ]\d{4}", text)
    assert not re.search(r"[\w.+-]+@[\w.-]+", text)
    assert not re.search(r"\d{6}-\d{7}", text)
