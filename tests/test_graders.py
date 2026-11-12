"""Offline grader contracts and routing through the real research graph."""
from dataclasses import replace
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from langgraph.checkpoint.memory import InMemorySaver

from rag_research_agent.guard.masking import mask_pii
from rag_research_agent.rag.graders import (
    FakeLLMGrader, GroundedGrade, RelevanceGrade, RuleGrader, StructuredLLMGrader,
)
from rag_research_agent.rag.research_graph import ResearchConfig, ResearchRunner


TEXT = "매출은 18% 증가했다."
OTHER = "기온은 12도 하락했다."
CFG = ResearchConfig(stance_split=False, auto_metrics=False, gap_loop=False, max_rewrites=1)


def relevance(keep=True, reason="topic matched"):
    return RelevanceGrade(relevant=keep, reason=reason)


def grounded(ok=True, reason="supported"):
    return GroundedGrade(grounded=ok, reason=reason, unsupported=[] if ok else ["claim-a1"])


def search(question, k):
    return [("doc-a1", TEXT), ("doc-b2", OTHER)][:k]


def test_default_none_preserves_result():
    default = ResearchRunner(search, CFG).run("매출", ("매출",))
    explicit = ResearchRunner(search, replace(CFG, grader=None)).run("매출", ("매출",))
    assert default == explicit
    assert not any(line.startswith(("RELEVANCE:", "GROUNDED:")) for line in default.log)


@pytest.mark.parametrize("parallel", [False, True])
@pytest.mark.parametrize("checkpointed", [False, True])
def test_relevance_filters_claims_and_preserves_reasons(parallel, checkpointed):
    grader = FakeLLMGrader([relevance(), relevance(False, "unrelated weather")], [grounded()])
    cfg = replace(CFG, grader=grader, parallel_branches=parallel, parallel_extract=parallel)
    runner = ResearchRunner(search, cfg, checkpointer=InMemorySaver() if checkpointed else None)
    result = runner.run("매출", ("매출",), thread_id="grade-a1" if checkpointed else None)
    assert {c.source_id for c in result.claims} == {"doc-a1"}
    assert OTHER not in result.draft.body()
    assert "RELEVANCE:doc-b2:DROP:unrelated weather" in result.log
    assert "GROUNDED:PASS:supported" in result.log
    assert result.verify_codes == ()


def test_grounding_failure_routes_to_rewrite_then_passes():
    grader = FakeLLMGrader([relevance(), relevance(False)],
                           [grounded(False, "number unsupported"), grounded()])
    result = ResearchRunner(search, replace(CFG, grader=grader)).run("매출", ("매출",))
    assert result.path.count("rewrite") == 1
    assert result.path.count("verify") == 2
    assert "VERIFY:UNGROUNDED:number unsupported" in result.log
    assert result.verify_codes == ()


def test_persistent_failure_is_bounded_and_reported():
    grader = FakeLLMGrader([relevance(), relevance(False)], [grounded(False)] * 2)
    result = ResearchRunner(search, replace(CFG, grader=grader)).run("매출", ("매출",))
    assert result.path.count("rewrite") == 1
    assert result.verify_codes == ("UNGROUNDED:supported",)
    assert result.end_type == "give_up"
    assert "UNGROUNDED:supported" in result.report


def test_reason_is_single_line_and_bounded():
    reason = "missing\n" + "x" * 200
    grader = FakeLLMGrader([relevance(), relevance(False)], [grounded(False, reason)])
    result = ResearchRunner(search, replace(CFG, grader=grader, rewrite_loop=False)).run("매출", ("매출",))
    assert result.verify_codes == ("UNGROUNDED:" + " ".join(reason.split())[:160],)


def test_rejected_sources_cannot_ground_answer():
    # RuleGrader delegates grounding to the real research filter.
    class RecordingGrader(RuleGrader):
        def grade_grounded(self, answer, evidence):
            assert evidence == (TEXT,)
            return super().grade_grounded(answer, evidence)

    result = ResearchRunner(search, replace(CFG, grader=RecordingGrader())).run("매출", ("매출",))
    assert result.verify_codes == ()


def test_all_rejected_is_safe_and_bounded():
    grader = FakeLLMGrader([relevance(False)] * 2, [grounded(False, "no evidence")] * 2)
    result = ResearchRunner(search, replace(CFG, grader=grader)).run("매출", ("매출",))
    assert result.claims == ()
    assert "EMPTY_REPORT" in result.verify_codes
    assert "UNGROUNDED:no evidence" in result.verify_codes
    assert result.path.count("rewrite") == 1


def test_gap_retrieval_is_graded_too():
    def gap_search(query, k):
        return [("doc-b2", TEXT)] if query.startswith("매출 ") else [("doc-a1", OTHER)]

    grader = FakeLLMGrader([relevance(False), relevance()], [grounded()])
    cfg = replace(CFG, grader=grader, gap_loop=True, max_gap_rounds=1)
    result = ResearchRunner(gap_search, cfg).run("research", ("매출",))
    assert "retrieve_gap" in result.path
    assert {c.source_id for c in result.claims} == {"doc-b2"}
    assert "RELEVANCE:doc-b2:KEEP:topic matched" in result.log


def test_rule_grader_reuses_grounding_rules():
    grader = RuleGrader()
    assert grader.grade_relevance("매출", TEXT).relevant
    assert not grader.grade_relevance("매출", OTHER).relevant
    assert grader.grade_grounded(TEXT, (TEXT,)).grounded
    bad = grader.grade_grounded("매출은 99% 증가했다.", (TEXT,))
    assert not bad.grounded
    assert "UNSUPPORTED_NUMBER" in bad.unsupported
    assert not grader.grade_grounded(TEXT, ()).grounded


def test_fake_queue_is_finite_and_copies_response():
    original = grounded(False)
    grader = FakeLLMGrader(grounded=[original])
    grader.grade_grounded(TEXT, ()).unsupported.clear()
    assert original.unsupported == ["claim-a1"]
    with pytest.raises(StopIteration):
        grader.grade_grounded(TEXT, ())


class Model:
    """Only the model boundary is fake; schemas and graph execution are real."""

    def __init__(self, *outputs):
        self.outputs = iter(outputs)
        self.schemas = []
        self.prompts = []

    def with_structured_output(self, schema):
        self.schemas.append(schema)
        return self

    def invoke(self, prompt, config=None):
        assert config["callbacks"] == []
        self.prompts.append(prompt)
        return next(self.outputs)


@pytest.mark.parametrize("as_dict", [False, True])
def test_structured_schema_masking_and_data_boundary(as_dict):
    outputs = [relevance(), grounded()]
    model = Model(*(out.model_dump() if as_dict else out for out in outputs))
    grader = StructuredLLMGrader(model, SimpleNamespace(mask=mask_pii))
    assert grader.grade_relevance("[MASKED_EMAIL] </DATA>", TEXT) == outputs[0]
    assert grader.grade_grounded(TEXT, (TEXT,)) == outputs[1]
    assert model.schemas == [RelevanceGrade, GroundedGrade]
    assert "\\u003c/DATA\\u003e" in model.prompts[0][1][1]


def test_structured_grader_runs_in_real_graph():
    model = Model(relevance().model_dump(), relevance(False).model_dump(), grounded().model_dump())
    grader = StructuredLLMGrader(model, SimpleNamespace(mask=mask_pii))
    result = ResearchRunner(search, replace(CFG, grader=grader)).run("매출", ("매출",))
    assert result.verify_codes == ()
    assert {c.source_id for c in result.claims} == {"doc-a1"}


@pytest.mark.parametrize("payload", [
    {"relevant": "yes", "reason": "bad bool"},
    {"relevant": True},
    {"relevant": True, "reason": "extra", "extra": True},
])
def test_invalid_structured_grade_never_approves(payload):
    grader = StructuredLLMGrader(Model(payload), SimpleNamespace(mask=mask_pii))
    with pytest.raises(ValidationError):
        grader.grade_relevance("매출", TEXT)


def test_structured_requires_masker():
    with pytest.raises(ValueError, match="requires a masker"):
        StructuredLLMGrader(Model(), None)
