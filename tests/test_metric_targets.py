"""Offline path tests through real RunEvent, target loader and target checks."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from rag_research_agent.core.run_events import RunEvent
from rag_research_agent.rag.metric_targets import check_targets, load_targets


def event(**changes):
    values = dict(
        run_id="run-a1", domain="research", track="deep", config="graph_full",
        dataset="synthetic", sha="abc1234", path=("grade", "verify"),
        end_type="END", loops={"rewrite": 0, "gap": 0, "verify": 0},
        calls={"slm": 0, "flagship": 0}, tokens={"in": 0, "out": 0},
        cost_krw=1, ttft_ms=0, total_ms=100,
        grade={"docs_in": 10, "docs_kept": 5, "relevance_drop_rate": .5},
        guard=(), nodes=(), estimated=True,
    )
    values.update(changes)
    return RunEvent(**values)


@pytest.mark.parametrize("value,exceeds", [(1.4, False), (1.5, False), (1.6, True)])
def test_cost_upper_bound(value, exceeds):
    warnings = check_targets([event(cost_krw=value)], {"research": {"cost_krw": {"max": 1.5}}})
    assert len(warnings) == int(exceeds)
    if exceeds:
        assert warnings == [{"run_id": "run-a1", "domain": "research", "estimated": True,
                             "metric": "cost_krw", "value": value, "bound": "max", "limit": 1.5}]


@pytest.mark.parametrize("value,exceeds", [(5999, False), (6000, False), (6001, True)])
def test_total_latency_upper_bound(value, exceeds):
    warnings = check_targets([event(total_ms=value)], {"research": {"total_ms": {"max": 6000}}})
    assert len(warnings) == int(exceeds)
    assert all(w["metric"] == "total_ms" for w in warnings)


@pytest.mark.parametrize("kept,bound", [(9, "min"), (8, None), (5, None), (2, None), (1, "max")])
def test_drop_range_and_wilson(kept, bound):
    rate = (10 - kept) / 10
    warnings = check_targets(
        [event(grade={"docs_in": 10, "docs_kept": kept, "relevance_drop_rate": rate})],
        {"research": {"grade": {"relevance_drop_rate": {"min": .2, "max": .8}}}},
    )
    assert len(warnings) == int(bound is not None)
    if bound:
        warning = warnings[0]
        assert warning["metric"] == "grade.relevance_drop_rate"
        assert warning["bound"] == bound
        assert (warning["count"], warning["total"], warning["rate"]) == (10 - kept, 10, rate)
        assert warning["wilson95"] == pytest.approx(
            [.01787621, .40415003] if kept == 9 else [.59584997, .98212379])


@pytest.mark.parametrize("count", [0, 2])
def test_zero_guard_target_counts_occurrences_without_copying_text(count):
    issue = {"gate": "grounded", "code": "UNSUPPORTED_NUMBER", "reason": "masked", "span": ""}
    warnings = check_targets([event(guard=(issue,) * count)], {"research": {"guard": {"max": 0}}})
    assert len(warnings) == int(count > 0)
    if warnings:
        assert warnings[0]["value"] == count
        assert "reason" not in warnings[0] and "span" not in warnings[0]


def test_domain_targets_do_not_fall_back_or_average_runs():
    events = [event(cost_krw=2), event(run_id="run-b2", domain="legal", cost_krw=2),
              event(run_id="run-c3", domain="unknown", cost_krw=20),
              event(run_id="run-d4", cost_krw=0)]
    warnings = check_targets(iter(events), {"research": {"cost_krw": {"max": 1.5}},
                                            "legal": {"cost_krw": {"max": 2}}})
    assert [w["run_id"] for w in warnings] == ["run-a1"]


@pytest.mark.parametrize("row", [{}, {"grade": {}}, {"cost_krw": {}},
                                  {"grade": {"relevance_drop_rate": {}}}])
def test_missing_metrics_and_bounds_are_silent(row, recwarn):
    assert check_targets([event()], {"research": row}) == []
    assert not recwarn


def test_missing_file_and_empty_targets(tmp_path, recwarn):
    path = tmp_path / "absent.json"
    assert load_targets(path) == {}
    assert check_targets([event()], path) == []
    assert check_targets([event()], {}) == []
    assert check_targets([], {"research": {"guard": {"max": 0}}}) == []
    assert not path.exists() and not recwarn


def test_json_file_roundtrip_and_real_event_mapping(tmp_path):
    path = tmp_path / "targets.json"
    targets = {"research": {"cost_krw": {"max": .5}}}
    path.write_text(json.dumps(targets), encoding="utf-8")
    record = json.loads(event().to_json(dumps=json.dumps))
    before = deepcopy(record)
    assert load_targets(path) == targets
    assert check_targets([record], path) == check_targets([event()], targets)
    assert record == before and load_targets(path) == targets


def test_shipped_file_has_four_domains_and_zero_guard_targets():
    path = Path(__file__).resolve().parents[1] / "evals/metric_targets.json"
    targets = load_targets(path)
    assert set(targets) == {"research", "legal", "medical", "life"}
    for domain, row in targets.items():
        assert row["guard"] == {"max": 0}
        assert row["cost_krw"]["max"] > 0 and row["total_ms"]["max"] > 0
        assert 0 <= row["grade"]["relevance_drop_rate"]["min"] <= row["grade"]["relevance_drop_rate"]["max"] <= 1
        assert check_targets([event(domain=domain, cost_krw=row["cost_krw"]["max"] + 1)], path)


def test_injection_and_empty_grade_skip_only_quality():
    issue = {"gate": "filter", "code": "GAP:sales", "reason": "", "span": ""}
    targets = {"research": {"cost_krw": {"max": 0}, "guard": {"max": 0},
                             "grade": {"relevance_drop_rate": {"min": .8}}}}
    warnings = check_targets([event(guard=(issue,))], targets, injection_run_ids=["run-a1"])
    assert [w["metric"] for w in warnings] == ["cost_krw", "guard"]
    empty = event(grade={"docs_in": 0, "docs_kept": 0, "relevance_drop_rate": 0})
    assert [w["metric"] for w in check_targets([empty], targets)] == ["cost_krw"]


def test_estimated_and_measured_events_retain_identity():
    warnings = check_targets([event(), event(run_id="run-b2", estimated=False)],
                             {"research": {"cost_krw": {"max": 0}}})
    assert [(w["run_id"], w["estimated"]) for w in warnings] == [("run-a1", True), ("run-b2", False)]


@pytest.mark.parametrize("targets", [[], {"research": []}, {"research": {"grade": []}},
    {"research": {"cost_krw": {"max": -1}}}, {"research": {"total_ms": {"max": True}}},
    {"research": {"cost_krw": {"max": float("nan")}}},
    {"research": {"cost_krw": {"max": float("inf")}}},
    {"research": {"cost_krw": {"min": 2, "max": 1}}},
    {"research": {"grade": {"relevance_drop_rate": {"max": 2}}}},
    {"research": {"guard": {"max": .5}}}])
def test_invalid_targets_are_rejected(targets):
    with pytest.raises(ValueError):
        check_targets([event()], targets)


def test_malformed_file_is_not_treated_as_missing(tmp_path):
    path = tmp_path / "invalid.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        load_targets(path)


def test_duplicate_or_invalid_events_and_inconsistent_grade_are_rejected():
    targets = {"research": {"grade": {"relevance_drop_rate": {"max": .8}}}}
    with pytest.raises(ValueError, match="duplicate"):
        check_targets([event(), event()], targets)
    invalid = json.loads(event().to_json(dumps=json.dumps))
    invalid["total_ms"] = -1
    with pytest.raises(ValueError):
        check_targets([invalid], targets)
    with pytest.raises(ValueError, match="match document counts"):
        check_targets([event(grade={"docs_in": 10, "docs_kept": 5, "relevance_drop_rate": .1})], targets)


@pytest.mark.parametrize("kept,reported", [
    (8, .2 - 1e-13), (8, .2 + 1e-13),
    (2, .8 - 1e-13), (2, .8 + 1e-13),
])
def test_drop_boundary_uses_document_counts_despite_reported_rounding(kept, reported):
    targets = {"research": {"grade": {"relevance_drop_rate": {"min": .2, "max": .8}}}}
    measured = event(grade={"docs_in": 10, "docs_kept": kept,
                           "relevance_drop_rate": reported})
    assert check_targets([measured], targets) == []


def test_drop_warning_value_matches_count_ratio_despite_reported_rounding():
    targets = {"research": {"grade": {"relevance_drop_rate": {"max": .8}}}}
    measured = event(grade={"docs_in": 10, "docs_kept": 1,
                           "relevance_drop_rate": .9 + 1e-13})
    warning, = check_targets([measured], targets)
    assert warning["value"] == warning["rate"] == warning["count"] / warning["total"]
    assert warning["bound"] == "max"
