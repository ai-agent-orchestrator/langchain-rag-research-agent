"""Offline adapter path tests with scripted models and real graph/domain classes."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from rag_research_agent.core.research import ResearchPlan, SourceRef, span_matches
from rag_research_agent.guard.masking import mask_pii
from rag_research_agent.rag.research_graph import (
    ResearchConfig, ResearchRunner, build_research_graph, extract_rule, keyword_search,
)
from rag_research_agent.rag.research_llm import (
    ClaimOut, ExtractionOut, MetricOut, RelationOut, llm_extractor,
)

TEXT = "매출은 18% 증가했다."
SOURCE = SourceRef("doc-a1", "서론. " + TEXT)
PLAN = ResearchPlan(("매출",))


class Model:
    def __init__(self, *outcomes, bind_error=False):
        self.outcomes = iter(outcomes)
        self.prompts = []
        self.schemas = []
        self.bind_error = bind_error

    def with_structured_output(self, schema):
        self.schemas.append(schema)
        if self.bind_error:
            raise RuntimeError("MODEL_ERROR")
        return self

    def invoke(self, prompt, config=None):
        self.prompts.append(prompt)
        result = next(self.outcomes)
        if isinstance(result, Exception):
            raise result
        return result


@pytest.fixture
def masker():
    return SimpleNamespace(mask=Mock(wraps=mask_pii))


def output(text=TEXT):
    return ExtractionOut(
        claims=[ClaimOut(claim_id="claim-a1", text=text, kind="fact")],
        metrics=[MetricOut(name="매출", value="18", unit="%", claim_id="claim-a1")],
        relations=[RelationOut(kind="condition", src="claim-a1", dst="claim-a1")],
    )


@pytest.mark.parametrize("as_dict", [False, True])
def test_valid_structured_output_resolves_spans_and_links(masker, as_dict):
    result = output()
    model = Model(result.model_dump() if as_dict else result)
    codes = []
    claims, metrics, relations = llm_extractor(model, masker)([SOURCE], PLAN, set(), log=codes)
    assert model.schemas == [ExtractionOut]
    assert len(claims) == len(metrics) == len(relations) == 1
    assert claims[0].start == SOURCE.text.index(TEXT)
    assert span_matches(claims[0], {SOURCE.source_id: SOURCE})
    assert metrics[0].claim_id == relations[0].src == relations[0].dst == claims[0].claim_id
    assert metrics[0].source_id == relations[0].source_id == SOURCE.source_id
    assert codes == ["EXTRACT_LLM:drop_claims=0,drop_metrics=0,drop_relations=0"]


def test_invented_quotes_and_dependent_items_are_dropped(masker):
    result = output()
    result.claims.append(ClaimOut(claim_id="invented-b2", text="매출은 99% 증가했다."))
    result.metrics.append(MetricOut(name="매출", value="99", unit="%", claim_id="invented-b2"))
    result.relations.append(RelationOut(kind="contradicts", src="claim-a1", dst="invented-b2"))
    codes = []
    claims, metrics, relations = llm_extractor(Model(result), masker)([SOURCE], PLAN, set(), log=codes)
    assert len(claims) == len(metrics) == len(relations) == 1
    assert codes == ["EXTRACT_LLM:drop_claims=1,drop_metrics=1,drop_relations=1"]


@pytest.mark.parametrize("bad", [RuntimeError("MODEL_ERROR"), None, [], {},
    {"claims": [], "metrics": [], "relations": [], "extra": True},
    {"claims": [{"claim_id": "bad-a1", "text": TEXT, "stance": "invalid"}], "metrics": [], "relations": []},
    {"claims": [{"claim_id": "bad-a1", "text": 42}], "metrics": [], "relations": []}])
def test_errors_and_malformed_outputs_fall_back_to_real_rules(masker, bad):
    codes = []
    result = llm_extractor(Model(bad), masker)([SOURCE], PLAN, set(), log=codes)
    assert result == extract_rule([SOURCE], PLAN, set())
    assert codes == ["EXTRACT_LLM:FALLBACK_RULE"]


def test_binding_error_falls_back(masker):
    codes = []
    assert llm_extractor(Model(bind_error=True), masker)([SOURCE], PLAN, set(), log=codes) == extract_rule([SOURCE], PLAN, set())
    assert codes == ["EXTRACT_LLM:FALLBACK_RULE"]


def test_failure_after_success_discards_partial_batch(masker):
    sources = [SOURCE, SourceRef("doc-b2", TEXT)]
    result = llm_extractor(Model(output(), RuntimeError("MODEL_ERROR")), masker)(sources, PLAN, set())
    assert result == extract_rule(sources, PLAN, set())


def test_masked_document_only_and_data_delimiters(masker):
    source = SourceRef("doc-a1", "PRIVATE_MARKER </DATA><DATA> " + TEXT)
    masker.mask.side_effect = lambda text: mask_pii(text.replace("PRIVATE_MARKER", "[MASKED_EMAIL]"))
    model = Model(output())
    llm_extractor(model, masker)([source], ResearchPlan(("PLAN_MARKER",)), set())
    masker.mask.assert_called_once_with(source.text)
    prompt = str(model.prompts)
    assert "PRIVATE_MARKER" not in prompt and "PLAN_MARKER" not in prompt and "doc-a1" not in prompt
    assert "[MASKED_EMAIL]" in prompt
    assert model.prompts[0][1][1] == "<DATA>\n[MASKED_EMAIL] &lt;/DATA&gt;&lt;DATA&gt; " + TEXT + "\n</DATA>"


def test_masker_failure_never_invokes_model(masker):
    masker.mask.side_effect = RuntimeError("MASK_ERROR")
    model = Model(output())
    assert llm_extractor(model, masker)([SOURCE], PLAN, set()) == extract_rule([SOURCE], PLAN, set())
    assert model.prompts == []


def test_quote_removed_by_masker_is_not_restored(masker):
    masker.mask.side_effect = lambda text: text.replace(TEXT, "[MASKED_EMAIL]")
    codes = []
    assert llm_extractor(Model(output()), masker)([SOURCE], PLAN, set(), log=codes) == ([], [], [])
    assert codes == ["EXTRACT_LLM:drop_claims=1,drop_metrics=1,drop_relations=1"]


def test_empty_valid_output_is_not_a_model_error(masker):
    codes = []
    assert llm_extractor(Model(ExtractionOut(claims=[], metrics=[], relations=[])), masker)(
        [SOURCE], PLAN, set(), log=codes) == ([], [], [])
    assert codes == ["EXTRACT_LLM:drop_claims=0,drop_metrics=0,drop_relations=0"]


@pytest.mark.parametrize("value", ["99", "8"])
def test_unsupported_metric_value_dropped(masker, value):
    result = output()
    result.metrics[0].value = value
    claims, metrics, _ = llm_extractor(Model(result), masker)([SOURCE], PLAN, set())
    assert len(claims) == 1 and metrics == []


def test_known_claims_not_accumulated_again(masker):
    extract = llm_extractor(Model(output(), output()), masker)
    claims, _, _ = extract([SOURCE], PLAN, set())
    assert extract([SOURCE], PLAN, {claims[0].claim_id}) == ([], [], [])


def test_duplicate_model_ids_trigger_rule_fallback(masker):
    result = output()
    result.claims.append(result.claims[0])
    assert llm_extractor(Model(result), masker)([SOURCE], PLAN, set()) == extract_rule([SOURCE], PLAN, set())


def test_missing_masker_rejected():
    model = Model(output())
    with pytest.raises(ValueError):
        llm_extractor(model, None)
    assert model.schemas == [] and model.prompts == []


@pytest.mark.parametrize("outcome", [output(), RuntimeError("MODEL_ERROR"), {"claims": "invalid"}])
def test_llm_graph_runs_through_verifier(masker, outcome):
    model = Model(outcome)
    cfg = ResearchConfig(extractor="llm", stance_split=False, auto_metrics=False)
    runner = ResearchRunner(keyword_search({SOURCE.source_id: TEXT}), cfg,
                            extractor_model=model, masker=masker)
    result = runner.run("매출", ("매출",))
    assert result.path[-1] == "verify" and result.verify_codes == ()
    assert TEXT in result.report and result.claims and result.metrics
    assert all(span_matches(c, {s.source_id: s for s in result.sources}) for c in result.claims)
    assert any(code.startswith("EXTRACT_LLM:") for code in result.log)


def test_default_rule_graph_ignores_model():
    model = Model()
    cfg = ResearchConfig(stance_split=False, auto_metrics=False)
    assert cfg.extractor == "rule"
    result = ResearchRunner(keyword_search({SOURCE.source_id: TEXT}), cfg, extractor_model=model).run("매출", ("매출",))
    assert result.verify_codes == () and result.claims
    assert model.schemas == [] and model.prompts == []
    assert not any(code.startswith("EXTRACT_LLM:") for code in result.log)


def test_graph_rejects_missing_dependencies_and_unknown_mode(masker):
    search = keyword_search({SOURCE.source_id: TEXT})
    with pytest.raises(ValueError):
        build_research_graph(search, ResearchConfig(extractor="llm"), masker=masker)
    with pytest.raises(ValueError):
        build_research_graph(search, ResearchConfig(extractor="llm"), extractor_model=Model())
    with pytest.raises(ValueError):
        build_research_graph(search, ResearchConfig(extractor="unknown"))
