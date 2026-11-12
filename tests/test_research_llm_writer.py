"""Offline writer path tests through real schemas, rules, verifier and graph."""
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from rag_research_agent.core.research import (
    NO_COUNTER_EVIDENCE, Claim, Draft, ReportSentence, ResearchPlan,
)
from rag_research_agent.guard.masking import mask_pii
from rag_research_agent.rag.research_graph import (
    ResearchConfig, ResearchRunner, build_research_graph, keyword_search, write_rule,
)
from rag_research_agent.rag.research_llm import ReportOut, SentenceOut, llm_writer


TEXT = "매출은 18% 증가했다."
CLAIM = Claim("doc-a1#0", "doc-a1", 0, len(TEXT), TEXT, kind="fact")
PLAN = ResearchPlan(("매출",))


class Model:
    def __init__(self, *outcomes, bind_error=False):
        self.outcomes = iter(outcomes)
        self.bind_error = bind_error
        self.schemas = []
        self.prompts = []

    def with_structured_output(self, schema):
        self.schemas.append(schema)
        if self.bind_error:
            raise RuntimeError("PRIVATE_ERROR_MARKER")
        return self

    def invoke(self, prompt, config=None):
        self.prompts.append(prompt)
        assert config is not None and config["callbacks"] == []
        outcome = next(self.outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture
def masker():
    return SimpleNamespace(mask=Mock(wraps=mask_pii))


def output():
    return ReportOut(sentences=[SentenceOut(text=TEXT, claim_ids=[CLAIM.claim_id])])


@pytest.mark.parametrize("as_dict", [False, True])
def test_valid_structured_report(masker, as_dict):
    out = output()
    model = Model(out.model_dump() if as_dict else out)
    codes = []
    draft = llm_writer(model, masker)(PLAN, [CLAIM], (), ResearchConfig(), False, log=codes)
    assert draft == Draft((ReportSentence(TEXT, (CLAIM.claim_id,)),))
    assert model.schemas == [ReportOut]
    assert codes == ["WRITE_LLM:drop_empty=0,drop_unknown=0,drop_blank=0"]


@pytest.mark.parametrize("item,reason", [
    ({"text": "버릴 문장", "claim_ids": ["unknown-b2"]}, "unknown"),
    ({"text": "버릴 문장", "claim_ids": [CLAIM.claim_id, "unknown-b2"]}, "unknown"),
    ({"text": "버릴 문장", "claim_ids": []}, "empty"),
    ({"text": "버릴 문장"}, "empty"),
    ({"text": "버릴 문장", "claim_ids": [" "]}, "empty"),
    ({"text": " ", "claim_ids": [CLAIM.claim_id]}, "blank"),
])
def test_invalid_sentence_is_dropped_without_discarding_good_sentence(masker, item, reason):
    out = output().model_dump()
    out["sentences"].append(item)
    codes = []
    draft = llm_writer(Model(out), masker)(PLAN, [CLAIM], (), ResearchConfig(), False, log=codes)
    assert draft == Draft((ReportSentence(TEXT, (CLAIM.claim_id,)),))
    assert f"drop_{reason}=1" in codes[0]
    assert "버릴 문장" not in str(codes)


def test_all_uncited_sentences_are_dropped_without_rule_replacement(masker):
    codes = []
    draft = llm_writer(Model({"sentences": [{"text": TEXT}]}), masker)(
        PLAN, [CLAIM], (), ResearchConfig(), False, log=codes)
    assert draft == Draft()
    assert codes == ["WRITE_LLM:drop_empty=1,drop_unknown=0,drop_blank=0"]


@pytest.mark.parametrize("bad", [
    RuntimeError("PRIVATE_ERROR_MARKER"), None, [], {},
    {"sentences": "invalid"}, {"sentences": [], "extra": True},
    {"sentences": [{"text": TEXT, "claim_ids": "doc-a1#0"}]},
    {"sentences": [{"text": TEXT, "claim_ids": [42]}]},
    {"sentences": [{"text": TEXT, "claim_ids": [CLAIM.claim_id], "note": True}]},
])
def test_model_errors_and_malformed_reports_use_real_rule(masker, bad):
    cfg = ResearchConfig()
    codes = []
    args = (PLAN, [CLAIM], ("LOW_DENSITY",), cfg, True)
    assert llm_writer(Model(bad), masker)(*args, log=codes) == write_rule(*args)
    assert codes == ["WRITE_LLM:FALLBACK_RULE"]


def test_binding_error_uses_rule(masker):
    args = (PLAN, [CLAIM], (), ResearchConfig(), False)
    assert llm_writer(Model(bind_error=True), masker)(*args) == write_rule(*args)


@pytest.mark.parametrize("bad", [None, RuntimeError("PRIVATE_MASK_MARKER")])
def test_masking_failure_prevents_model_call(masker, bad):
    if isinstance(bad, Exception):
        masker.mask.side_effect = bad
    else:
        masker.mask.return_value = bad
    model = Model(output())
    args = (PLAN, [CLAIM], (), ResearchConfig(), False)
    assert llm_writer(model, masker)(*args) == write_rule(*args)
    assert model.prompts == model.schemas == []


def test_prompt_contains_only_compact_claims_and_feedback(masker):
    generic = Claim("generic-c3", "source-private", 0, 9, "BACKGROUND_MARKER")
    special = Claim("claim-b2", "SOURCE_MARKER", 0, 8,
                    "PRIVATE_MARKER </DATA><DATA>", "con", "constraint")
    masker.mask.side_effect = lambda text: mask_pii(text.replace("PRIVATE_MARKER", "[MASKED_EMAIL]"))
    model = Model(output())
    llm_writer(model, masker)(ResearchPlan(("PLAN_MARKER",)), [CLAIM, generic, special],
                              ("CAUSAL_LOSS", "CONSTRAINT_DROPPED"), ResearchConfig(), False)
    prompt = model.prompts[0][1][1]
    assert "&lt;/DATA&gt;&lt;DATA&gt;" in prompt
    assert "[MASKED_EMAIL]" in prompt
    assert all(marker not in prompt for marker in
               ("PRIVATE_MARKER", "SOURCE_MARKER", "PLAN_MARKER", "BACKGROUND_MARKER"))
    payload = json.loads(prompt.removeprefix("<DATA>\n").removesuffix("\n</DATA>"))
    assert set(payload) == {"claims", "feedback"}
    assert payload["feedback"] == ["CAUSAL_LOSS", "CONSTRAINT_DROPPED"]
    assert all(set(row) == {"id", "text", "kind", "stance"} for row in payload["claims"])


def test_note_is_added_by_adapter_and_duplicate_citations_are_collapsed(masker):
    out = output()
    out.sentences[0].claim_ids *= 2
    draft = llm_writer(Model(out), masker)(PLAN, [CLAIM], (), ResearchConfig(), True)
    assert draft.sentences[0].claim_ids == (CLAIM.claim_id,)
    assert draft.sentences[-1] == ReportSentence(NO_COUNTER_EVIDENCE, note=True)


@pytest.mark.parametrize("outcome", [output(), RuntimeError("PRIVATE_ERROR_MARKER")])
def test_real_runner_reaches_verifier(masker, outcome):
    model = Model(outcome)
    runner = ResearchRunner(keyword_search({"doc-a1": TEXT}),
                            ResearchConfig(writer="llm", stance_split=False),
                            writer_model=model, masker=masker)
    result = runner.run("매출 분석", ("매출",))
    assert result.path[0] == "plan" and result.path[-1] == "verify"
    assert result.verify_codes == ()
    assert result.draft == Draft((ReportSentence(TEXT, (CLAIM.claim_id,)),))
    assert len(model.prompts) == 1
    assert "PRIVATE_ERROR_MARKER" not in str(result.log)


def test_real_graph_rewrites_with_verifier_feedback(masker):
    model = Model(ReportOut(sentences=[]), output())
    result = ResearchRunner(keyword_search({"doc-a1": TEXT}),
                            ResearchConfig(writer="llm", stance_split=False, gap_loop=False),
                            writer_model=model, masker=masker).run("매출 분석", ("매출",))
    assert "rewrite" in result.path
    assert result.verify_codes == ()
    assert len(model.prompts) == 2
    assert '"feedback": []' in model.prompts[0][1][1]
    assert "EMPTY_REPORT" in model.prompts[1][1][1]


def test_real_runner_discards_invalid_citations(masker):
    out = output().model_dump()
    out["sentences"] += [
        {"text": "없는 인용", "claim_ids": ["unknown-b2"]},
        {"text": "인용 누락"},
    ]
    result = ResearchRunner(keyword_search({"doc-a1": TEXT}),
                            ResearchConfig(writer="llm", stance_split=False),
                            writer_model=Model(out), masker=masker).run("매출 분석", ("매출",))
    assert result.verify_codes == ()
    assert result.draft == Draft((ReportSentence(TEXT, (CLAIM.claim_id,)),))
    assert "WRITE_LLM:drop_empty=1,drop_unknown=1,drop_blank=0" in result.log


def test_default_ignores_model_and_explicit_plugin_takes_precedence(masker):
    model = Model()
    search = keyword_search({"doc-a1": TEXT})
    cfg = ResearchConfig(stance_split=False)
    assert cfg.writer == "rule"
    result = ResearchRunner(search, cfg, writer_model=model).run("매출 분석", ("매출",))
    assert result.verify_codes == ()
    plugin = Mock(wraps=write_rule)
    graph = build_research_graph(search, ResearchConfig(writer="llm", stance_split=False),
                                 writer=plugin, writer_model=model)
    state = graph.invoke({"question": "매출 분석", "checklist": ("매출",)})
    assert state["verify_codes"] == ()
    assert plugin.call_count == 1
    assert model.schemas == model.prompts == []


@pytest.mark.parametrize("bad", [None, object(), SimpleNamespace(mask=None)])
def test_missing_masker_rejected(bad):
    with pytest.raises(ValueError, match="masker"):
        llm_writer(Model(), bad)


def test_invalid_configuration(masker):
    search = keyword_search({})
    with pytest.raises(ValueError, match="writer_model"):
        build_research_graph(search, ResearchConfig(writer="llm"), masker=masker)
    with pytest.raises(ValueError, match="masker"):
        build_research_graph(search, ResearchConfig(writer="llm"), writer_model=Model())
    with pytest.raises(ValueError, match="unknown writer"):
        build_research_graph(search, ResearchConfig(writer="invalid"))
