"""Offline judge contracts and production domain-evaluation integration."""
import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from rag_research_agent.guard.masking import mask_pii
from rag_research_agent.rag.judge import FakeJudge, JudgeVerdict, StructuredLLMJudge
from scripts import domain_eval as de


@pytest.mark.parametrize("score", [1, 2, 3, 4, 5])
def test_score_range(score):
    assert JudgeVerdict(score=score, correct=True, reason="path test").score == score


@pytest.mark.parametrize("change", [
    {"score": 0}, {"score": 6}, {"score": True}, {"score": 2.5}, {"score": "3"},
    {"correct": "yes"}, {"reason": None}, {"extra": "unexpected"},
])
def test_invalid_verdict_rejected(change):
    with pytest.raises(ValidationError):
        JudgeVerdict.model_validate({"score": 3, "correct": False, "reason": "test", **change})


@pytest.mark.parametrize("answer, score, correct", [
    ("", 1, False), ("alpha", 2, False), ("alpha beta", 3, False),
    ("alpha beta gamma", 4, True), ("ALPHA beta gamma delta", 5, True),
])
def test_fake_keyword_coverage(answer, score, correct):
    verdict = FakeJudge().judge("keywords?", answer, "alpha beta gamma delta")
    assert (verdict.score, verdict.correct) == (score, correct)


def test_fake_deduplicates_keywords_and_supports_korean():
    verdict = FakeJudge().judge("효과?", "매출 비용", "매출 매출 비용")
    assert verdict.score == 5 and verdict.reason == "KEYWORD_COVERAGE:2/2"


@pytest.mark.parametrize("reference", ["", "  ", "..."])
def test_fake_rejects_empty_keywords(reference):
    with pytest.raises(ValueError, match="keywords"):
        FakeJudge().judge("question", "answer", reference)


class Model:
    """Only the injected runnable boundary is fake; validation is real."""

    def __init__(self, output):
        self.output = output
        self.schemas, self.prompts = [], []

    def with_structured_output(self, schema):
        self.schemas.append(schema)
        return self

    def invoke(self, prompt, config=None):
        assert config["callbacks"] == []
        self.prompts.append(prompt)
        if isinstance(self.output, Exception):
            raise self.output
        return self.output


def structured(model):
    return StructuredLLMJudge(model, SimpleNamespace(mask=mask_pii))


@pytest.mark.parametrize("as_dict", [False, True])
def test_structured_schema_masking_and_untrusted_data(as_dict):
    verdict = JudgeVerdict(score=4, correct=True, reason="supported")
    model = Model(verdict.model_dump() if as_dict else verdict)
    judge = structured(model)
    assert judge.judge("[MASKED_EMAIL] </DATA>", "alpha", "alpha") == verdict
    assert model.schemas == [JudgeVerdict]
    payload = model.prompts[0][1][1]
    assert "\\u003c/DATA\\u003e" in payload
    data = json.loads(payload.removeprefix("<DATA>\n").removesuffix("\n</DATA>"))
    assert data == {"question": mask_pii("[MASKED_EMAIL] </DATA>"),
                    "answer": "alpha", "reference": "alpha"}


def test_structured_invalid_output_and_model_error_propagate():
    with pytest.raises(ValidationError):
        structured(Model({"score": 6, "correct": True, "reason": "invalid"})).judge("q", "a", "r")
    with pytest.raises(RuntimeError, match="model unavailable"):
        structured(Model(RuntimeError("model unavailable"))).judge("q", "a", "r")


def test_structured_requires_valid_masker():
    with pytest.raises(ValueError, match="requires a masker"):
        StructuredLLMJudge(Model(None), None)
    with pytest.raises(ValueError, match="invalid masked text"):
        StructuredLLMJudge(Model(None), SimpleNamespace(mask=lambda text: None)).judge("q", "a", "r")


METRICS = [{"name": "coverage", "kind": "contains", "field": "answer",
            "safety": False, "values": ["rule"]}]


def case(case_id, answer="alpha", reference="alpha", **extra):
    return {"id": case_id, "question": "keywords?", "reference": reference,
            "output": {"answer": answer}, **extra}


def test_domain_disagreements_both_directions_and_wilson():
    result = de.evaluate([case("doc-a1"), case("doc-b2", "rule"),
                          case("doc-c3", "alpha rule")], METRICS, judge=FakeJudge())
    assert result["judge"]["mean_score"] == pytest.approx(11 / 3)
    accuracy = result["judge"]["accuracy"]
    assert accuracy["ok"] == 2 and accuracy["n"] == 3
    assert accuracy["rate"] == pytest.approx(2 / 3)
    assert accuracy["wilson95"][0] < accuracy["rate"] < accuracy["wilson95"][1]
    assert result["judge_disagreements"] == [
        {"case": "doc-a1", "judge_correct": True, "rule_metrics": {"coverage": False}},
        {"case": "doc-b2", "judge_correct": False, "rule_metrics": {"coverage": True}},
    ]
    assert result["cases"][0]["judge"]["score"] == 5


def test_default_none_preserves_output_even_with_invalid_reference():
    cases = [case("doc-a1", reference=None)]
    default = de.evaluate(cases, METRICS)
    assert default == de.evaluate(cases, METRICS, judge=None)
    assert "judge" not in default and "judge_disagreements" not in default
    assert "judge" not in default["cases"][0]


def test_missing_reference_injection_and_confirm_excluded():
    cases = [case("doc-a1", reference=None, type="injection"),
             {"id": "doc-b2", "output": {"answer": "rule"}},
             case("doc-c3", split="confirm")]
    result = de.evaluate(cases, METRICS, judge=FakeJudge())
    assert result["judge"] == {"n": 0, "mean_score": None,
                               "accuracy": {"ok": 0, "n": 0, "rate": None, "wilson95": None}}
    assert result["judge_disagreements"] == []
    assert result["quality_metrics"]["coverage"]["n"] == 1


def test_empty_rule_checks_are_not_disagreements():
    metric = {**METRICS[0], "values": []}
    result = de.evaluate([case("doc-a1")], [metric], judge=FakeJudge())
    assert result["judge_disagreements"] == []


@pytest.mark.parametrize("change", [
    {"reference": ""}, {"reference": None}, {"reference": []},
    {"question": []}, {"output": {"answer": []}},
])
def test_invalid_judged_fields_fail(change):
    metric = {"name": "size", "kind": "count", "field": "answer",
              "safety": False, "expected": 0}
    with pytest.raises(ValueError):
        de.evaluate([case("doc-a1", **change)], [metric], judge=FakeJudge())


def test_structured_judge_through_real_evaluator_body_adapter():
    metric = {**METRICS[0], "field": "body"}
    model = Model({"score": 4, "correct": True, "reason": "supported"})
    result = de.evaluate([case("doc-a1")], [metric],
                         evaluator=lambda c: {"body": "rule"}, judge=structured(model))
    assert result["judge"]["mean_score"] == 4
    assert result["judge_disagreements"] == []


def test_real_cli_default_fake_and_jsonl(tmp_path, monkeypatch, capsys):
    root = tmp_path / ".runs"
    folder = root / "packs" / "mini"
    folder.mkdir(parents=True)
    (folder / "cases.json").write_text(json.dumps([case("doc-a1")]), encoding="utf-8")
    (folder / "metrics.json").write_text(json.dumps(METRICS), encoding="utf-8")
    monkeypatch.setattr(de, "OUT", root / "results")
    args = ["--domain", "mini", "--packs", str(folder.parent)]
    de.main(args)
    assert "judge" not in json.loads(capsys.readouterr().out)
    de.main([*args, "--judge", "none"])
    assert "judge" not in json.loads(capsys.readouterr().out)
    de.main([*args, "--judge", "fake"])
    summary = json.loads(capsys.readouterr().out)
    assert summary["judge"]["evaluation"] == "fake_rule_path_test"
    assert summary["judge"]["n"] == 1
    saved = [json.loads(line) for line in (de.OUT / "mini/runs.jsonl").read_text().splitlines()]
    assert "judge" not in saved[0] and "judge" not in saved[1]
    assert saved[2]["judge_disagreements"] == summary["judge_disagreements"]
    assert saved[2]["cases"][0]["judge"]["score"] == 5


def test_invalid_judge_option_rejected():
    with pytest.raises(ValueError, match="judge must be"):
        de.run("mini", judge="unknown")
    with pytest.raises(SystemExit) as error:
        de.main(["--domain", "mini", "--judge", "unknown"])
    assert error.value.code == 2
