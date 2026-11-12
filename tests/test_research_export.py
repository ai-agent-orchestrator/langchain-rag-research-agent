"""Offline exports using real research records and the rule-based runner."""
from dataclasses import replace
from html.parser import HTMLParser

import pytest

from rag_research_agent.core.research import Claim, Draft, ReportSentence, ResearchPlan, SourceRef
from rag_research_agent.rag.research_export import export_html, export_markdown
from rag_research_agent.rag.research_graph import ResearchConfig, ResearchResult, ResearchRunner, keyword_search


def result():
    source = SourceRef("doc-a1", "앞부분. 인용 구간. 뒷부분.")
    quote = "인용 구간."
    start = source.text.index(quote)
    claim = Claim("claim-a1", source.source_id, start, start + len(quote), quote)
    draft = Draft((ReportSentence("첫 문장.", (claim.claim_id,)),
                   ReportSentence("다음 문장.", (claim.claim_id, claim.claim_id)),
                   ReportSentence("안내 문장.", note=True)))
    return ResearchResult(draft.render(), draft, ResearchPlan(()), (claim,), (), (source,),
                          (), "", (), (("write", "model_in", 7), ("write", "model_out", 3)),
                          ("write", "verify"))


def test_markdown_reuses_footnotes_and_exports_exact_source_span():
    r = result()
    text = export_markdown(r)
    claim = r.claims[0]
    assert "첫 문장\\.[^1]" in text
    assert "다음 문장\\.[^1]" in text
    assert text.count("[^1]:") == 1 and "[^2]" not in text
    assert f"[{claim.start}:{claim.end}] — 인용 구간\\." in text
    assert "doc\\-a1" in text
    assert "앞부분" not in text and "뒷부분" not in text
    assert "안내 문장\\.[^" not in text


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.links, self.tags = [], [], []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.append(attrs["id"])
        if "href" in attrs:
            self.links.append(attrs["href"])


def test_html_links_resolve_to_unique_numbered_footnotes():
    parser = Links()
    parser.feed(export_html(result()))
    assert parser.ids == ["fn-1"]
    assert parser.links == ["#fn-1", "#fn-1"]


def test_first_use_order_controls_numbering():
    r = result()
    other = Claim("claim-b1", "doc-b1", 0, 3, "근거.")
    r = replace(r, sources=r.sources + (SourceRef("doc-b1", other.text),),
                claims=r.claims + (other,),
                draft=Draft((ReportSentence("둘.", (other.claim_id, r.claims[0].claim_id)),)))
    text = export_markdown(r)
    assert "둘\\.[^1][^2]" in text
    assert text.index("doc\\-b1") < text.index("doc\\-a1")


def test_untrusted_text_is_literal_in_both_formats():
    r = result()
    raw = '<script>alert("x")</script> & [link](javascript:bad)'
    claim = Claim("claim-x1", raw, 0, len(raw), raw)
    r = replace(r, draft=Draft((ReportSentence(raw, (claim.claim_id,)),)),
                sources=(SourceRef(raw, raw),), claims=(claim,),
                verify_codes=(raw,), path=(raw,), cost=((raw, raw, 2),), stopped=raw)
    html = export_html(r)
    parser = Links()
    parser.feed(html)
    assert "script" not in parser.tags and "img" not in parser.tags
    assert parser.links == ["#fn-1"]
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "&quot;x&quot;" in html and "&amp;" in html
    md = export_markdown(r)
    assert "<script>" not in md
    assert r"\[link\]\(javascript:bad\)" in md


@pytest.mark.parametrize("export", [export_markdown, export_html])
def test_review_and_appendix_show_failure_and_estimates(export):
    r = result()
    text = export(r)
    assert "검수 통과" in text and "추정 토큰: 10" in text
    assert "write → verify" in text
    assert ("model_in" in text if export is export_html else r"model\_in" in text)
    failed = export(replace(r, verify_codes=("GAP:매출",), stopped="TOKEN_LIMIT"))
    assert "검수 미통과 항목: GAP:매출" in failed
    assert "검수 통과" not in failed and "TOKEN" in failed
    assert "검수 미검증" in export(replace(r, path=(), draft=Draft()))
    assert "검수 미검증" in export(replace(r, interrupts=(object(),)))


@pytest.mark.parametrize("export", [export_markdown, export_html])
@pytest.mark.parametrize("broken", ["claim", "source", "span"])
def test_invalid_citations_fail_explicitly(export, broken):
    r = result()
    if broken == "claim":
        r = replace(r, claims=())
    elif broken == "source":
        r = replace(r, sources=())
    else:
        r = replace(r, claims=(replace(r.claims[0], text="지어낸 인용"),))
    with pytest.raises(ValueError, match="invalid citation"):
        export(r)


def test_exports_accept_real_rule_runner_results_without_mutation():
    runner = ResearchRunner(keyword_search({"doc-a1": "매출 7% 증가했다."}),
                            ResearchConfig(stance_split=False, rewrite_loop=False))
    r = runner.run("매출", ("매출",))
    before = repr(r)
    assert "[^1]" in export_markdown(r)
    assert 'href="#fn-1"' in export_html(r)
    assert repr(r) == before
