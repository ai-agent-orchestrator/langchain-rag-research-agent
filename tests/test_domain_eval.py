"""Synthetic pack fixtures exercise the production evaluator and real research graph."""
import json

import pytest

from scripts import domain_eval as de


@pytest.fixture
def packs(tmp_path, monkeypatch):
    monkeypatch.setattr(de, "OUT", tmp_path / ".runs/domain_eval")
    def write(name, cases, metrics):
        folder = tmp_path / name
        folder.mkdir()
        (folder / "cases.json").write_text(json.dumps({"cases": cases}), encoding="utf-8")
        (folder / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
        return tmp_path
    return write


def metric(name="coverage", kind="contains", safety=False, **extra):
    return {"name": name, "kind": kind, "field": "answer", "safety": safety, **extra}


def test_research_shaped_pack_and_append(packs):
    root = packs("mini-research", [
        {"id": "doc-a1", "output": {"answer": "cost falls because reuse"},
         "gold": {"groups": [["cost", "falls"], ["because", "reuse"]]}},
        {"id": "doc-b2", "split": "confirm"},
    ], [metric(values_field="gold.groups")])
    first = de.run("mini-research", root)
    de.run("mini-research", root)
    assert first["quality_mean"] == 1
    assert first["quality_metrics"]["coverage"]["n"] == 2
    assert first["quality_metrics"]["coverage"]["wilson95"][0] < 1
    assert not first["safety_metrics"]
    lines = (de.OUT / "mini-research/runs.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2 and json.loads(lines[0]) == first


def test_safety_pack_separates_counts_and_injection(packs):
    root = packs("mini-safety", [
        {"id": "doc-a1", "output": {"answer": "supported unsafe unsafe", "citations": []}},
        {"id": "doc-b2", "type": "injection", "output": {"answer": "unsafe", "citations": []}},
        {"id": "doc-c3", "output": {"answer": "supported", "citations": []}},
    ], [metric(values=["supported"]), metric("prohibited", "forbidden", True, values=["unsafe"]),
        {"name": "citations", "kind": "count", "field": "citations", "safety": True, "expected": 0}])
    result = de.run("mini-safety", root)
    assert result["quality_mean"] == 1
    assert result["quality_metrics"]["coverage"]["n"] == 2
    safety = result["safety_metrics"]["prohibited"]
    assert (safety["errors"], safety["n"], safety["count"]) == (2, 3, 3)
    assert safety["rate"] == pytest.approx(2 / 3)
    assert safety["wilson95_upper"] > safety["rate"]
    zero = result["safety_metrics"]["citations"]
    assert zero["errors"] == 0 and zero["n"] == 3 and zero["wilson95_upper"] > 0


def test_count_quality_and_no_quality_for_safety_only():
    cases = [{"id": "doc-a1", "output": {"answer": ["claim-a", "claim-b"]}}]
    count = metric(kind="count", expected=2)
    assert de.evaluate(cases, [count])["quality_mean"] == 1
    count["safety"] = True
    assert de.evaluate(cases, [count])["quality_mean"] is None


def test_empty_pack_error(packs):
    root = packs("empty", [], [metric(values=["ok"])])
    with pytest.raises(ValueError, match="empty pack: empty"):
        de.run("empty", root)
    assert not de.OUT.exists()


def test_real_research_adapter():
    cases, metrics = de.load_pack("research")
    case = next(c for c in cases if c["split"] == "compare")
    output = de.research_output(case)
    assert isinstance(output["body"], str) and output["body"]
    assert isinstance(output["unsupported_numbers"], list)
    result = de.evaluate([case], metrics, de.research_output)
    assert result["n_cases"] == 1
    assert set(result["quality_metrics"]) == {
        "metric_coverage", "causal_retention", "constraint_retention", "balance"}
    assert "unsupported_numbers" in result["safety_metrics"]


@pytest.mark.parametrize("domain", ["../escape", "a/b", "a\\b", ".."])
def test_domain_path_rejected(domain):
    with pytest.raises(ValueError, match="simple folder name"):
        de.load_pack(domain)


@pytest.mark.parametrize("change", [
    {"kind": "python"}, {"safety": "false"}, {"values": [""]}, {"field": "absent"},
    {"kind": "count", "expected": -1}, {"values": None}, {"match": "eval"},
])
def test_invalid_metrics_rejected(change):
    spec = metric(values=["ok"])
    spec.update(change)
    with pytest.raises(ValueError):
        de.evaluate([{"id": "doc-a1", "output": {"answer": "ok"}}], [spec])


def test_empty_expectations_are_not_successes():
    result = de.evaluate([{"id": "doc-a1", "output": {"answer": "ok"}}], [metric(values=[])])
    assert result["quality_mean"] is None
    assert result["quality_metrics"]["coverage"]["n"] == 0


def test_missing_outputs_and_empty_split_rejected():
    with pytest.raises(ValueError, match="missing target field: output"):
        de.evaluate([{"id": "doc-a1"}], [metric(values=["ok"])])
    with pytest.raises(ValueError, match="empty pack for split"):
        de.evaluate([{"id": "doc-a1", "split": "confirm"}], [metric(values=["ok"])])


def test_injected_callable_and_cli_errors(packs):
    root = packs("provided", [{"id": "doc-a1", "input": "ok"}], [metric(values=["ok"])])
    assert de.run("provided", root, evaluator=lambda c: {"answer": c["input"]})["quality_mean"] == 1
    with pytest.raises(SystemExit) as error:
        de.main(["--domain", "../escape"])
    assert error.value.code == 2
    with pytest.raises(ValueError, match="compare only"):
        de.run("provided", root, split="confirm")
