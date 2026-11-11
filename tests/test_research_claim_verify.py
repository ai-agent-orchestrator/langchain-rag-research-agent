"""Offline path tests through real report data, verifier and extractive writer."""
from dataclasses import replace

import pytest

from rag_research_agent.core.research import Claim, Draft, ReportSentence, ResearchPlan, SourceRef
from rag_research_agent.guard.research_filter import verify_report
from rag_research_agent.rag.research_graph import ResearchConfig, extract_rule, write_rule


PLAN = ResearchPlan(())


def claim(text, name="claim-a1", source="doc-a1", kind="fact"):
    return Claim(name, source, 0, len(text), text, kind=kind)


def verify(text, claims, ids=None, *, enabled=True):
    ids = tuple(c.claim_id for c in claims) if ids is None else ids
    return verify_report(Draft((ReportSentence(text, ids),)), PLAN, claims, [],
                         expect_balance=False, check_claim_alignment=enabled)


@pytest.mark.parametrize("text", ["매출은 28% 증가했다.", "매출은 8% 증가했다."])
def test_number_replacement_is_retryable_misquote(text):
    codes = verify(text, [claim("매출은 18% 증가했다.")])
    assert "MISQUOTED" in codes


def test_default_preserves_existing_global_number_check():
    claims = [claim("매출은 18% 증가했다."), claim("비용은 28% 감소했다.", "claim-b1", "doc-b1")]
    assert verify("매출은 28% 증가했다.", claims, ("claim-a1",), enabled=False) == ()
    assert "MISQUOTED" in verify("매출은 28% 증가했다.", claims, ("claim-a1",))


@pytest.mark.parametrize("ids", [("claim-a1",), ("claim-a1", "claim-b1")])
def test_other_source_cannot_lend_its_number(ids):
    claims = [claim("매출은 18% 증가했다."), claim("비용은 28% 감소했다.", "claim-b1", "doc-b1")]
    codes = verify("매출은 28% 증가했다.", claims, ids)
    assert "MISQUOTED" in codes
    assert "UNSUPPORTED_NUMBER" not in codes  # present globally, attributed incorrectly


def test_two_claim_values_swapped_in_one_report_sentence():
    claims = [claim("매출은 18% 증가했다."), claim("비용은 28% 감소했다.", "claim-b1", "doc-b1")]
    assert "MISQUOTED" in verify("매출은 28% 증가했다.; 비용은 18% 감소했다.", claims)
    assert verify("매출은 18% 증가했다.; 비용은 28% 감소했다.", claims) == ()


@pytest.mark.parametrize("original,reversed_text", [
    ("금리 인상 때문에 거래량 감소가 발생했다.", "거래량 감소 때문에 금리 인상이 발생했다."),
    ("Warming causes drought.", "Drought causes warming."),
    ("Drought occurs because warming intensifies.", "Warming intensifies because drought occurs."),
])
def test_causal_direction_reversal(original, reversed_text):
    claims = [claim(original, kind="causal")]
    assert "OVERREACH" in verify(reversed_text, claims)
    assert verify(original, claims) == ()


def test_high_share_of_new_content_words_is_overreach():
    claims = [claim("매출은 18% 증가했다.")]
    assert "OVERREACH" in verify("매출은 세계시장 독점과 경쟁업체 소멸을 영구적으로 보장한다.", claims)


def test_uncited_claim_words_do_not_ground_sentence():
    claims = [claim("매출은 18% 증가했다."), claim("자동화는 생산성과 효율성을 개선한다.", "claim-b1", "doc-b1")]
    assert "OVERREACH" in verify(claims[1].text, claims, ("claim-a1",))


def test_citation_markers_are_not_numeric_evidence():
    assert "MISQUOTED" in verify("매출은 28% 증가했다. [28]", [claim("매출은 18% 증가했다.")])


def test_formatted_numbers_and_decimal_exact_extracts():
    text = "매출은 1,250원이며 성장률은 3.2%다."
    assert verify(text, [claim(text)]) == ()
    assert verify("매출은 1250원이며 성장률은 3.2%다.", [claim(text)]) == ()


def test_notes_and_unknown_citations_keep_existing_contract():
    c = claim("매출은 18% 증가했다.")
    draft = Draft((ReportSentence(c.text, (c.claim_id,)), ReportSentence("임의 수치 77", note=True)))
    assert verify_report(draft, PLAN, [c], [], check_claim_alignment=True) == ()
    assert verify(c.text, [c], ("missing-a1",)) == ("UNCITED",)
    assert verify_report(Draft(), PLAN, [c], [], check_claim_alignment=True) == ("EMPTY_REPORT",)


@pytest.mark.parametrize("feedback", [(), ("MISQUOTED",), ("OVERREACH",)])
def test_real_extractive_writer_passes_alignment(feedback):
    source = SourceRef("doc-a1", "금리 인상 때문에 거래량이 18% 감소했다. 다만 신축 단지는 제외된다.")
    plan = ResearchPlan(("거래량",))
    claims, metrics, _ = extract_rule([source], plan, set())
    assert claims and metrics
    draft = write_rule(plan, claims, feedback, ResearchConfig(), no_con=True)
    assert verify_report(draft, plan, claims, metrics, check_claim_alignment=True) == ()


@pytest.mark.parametrize("failure", ["MISQUOTED", "OVERREACH"])
def test_alignment_codes_follow_real_graph_rewrite_route(monkeypatch, failure):
    from rag_research_agent.rag import research_graph

    real_write = research_graph.write_rule
    calls = []

    def write_with_one_corruption(*args, **kwargs):
        draft = real_write(*args, **kwargs)
        calls.append(draft)
        if len(calls) == 1:
            sentence = draft.sentences[0]
            text = (sentence.text.replace("18", "28") if failure == "MISQUOTED"
                    else "매출은 세계시장 독점과 경쟁업체 소멸을 영구적으로 보장한다.")
            return Draft((replace(sentence, text=text), *draft.sentences[1:]))
        return draft

    def enabled_verify(*args, **kwargs):
        return verify_report(*args, **kwargs, check_claim_alignment=True)

    monkeypatch.setattr(research_graph, "write_rule", write_with_one_corruption)
    monkeypatch.setattr(research_graph, "verify_report", enabled_verify)
    result = research_graph.ResearchRunner(
        research_graph.keyword_search({"doc-a1": "매출은 18% 증가했다."}),
        ResearchConfig(stance_split=False, auto_metrics=False),
    ).run("매출 분석")
    assert any(failure in line for line in result.log)
    assert result.path.count("rewrite") == 1
    assert len(calls) == 2 and result.verify_codes == ()
