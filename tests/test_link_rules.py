import pytest

from rag_research_agent.core.types import LinkType
from rag_research_agent.diet.dieter import ClassOrderDieter
from rag_research_agent.ingest.sentences import SentenceChunker
from rag_research_agent.ontology.link_rules import RuleLinkBuilder


@pytest.mark.parametrize("marker,reverse,kind", [
    *[(m, False, LinkType.CAUSES) for m in ("그 결과", "이에 따라", "따라서", "결국", "그래서")],
    *[(m, True, LinkType.CAUSES) for m in ("그 이유는", "원인은", "이는 비용 때문")],
    *[(m, True, LinkType.CONTRADICTS) for m in ("그러나 실제로는", "하지만 실제로는")],
])
def test_direction_and_type(marker, reverse, kind):
    text = f"비용이 늘었다. {marker} 수익이 줄었다."
    segments = SentenceChunker().split(text)
    link, = RuleLinkBuilder().with_text(text).build(segments)
    assert (link.src, link.dst) == (("s02", "s01") if reverse else ("s01", "s02"))
    assert link.type == kind and link.origin == "rule"


def test_unrelated_and_single_sentence_have_no_link():
    for text in ("비용이 늘었다. 날씨는 맑다.", "비용 때문에 수익이 줄었다."):
        assert RuleLinkBuilder(text).build(SentenceChunker().split(text)) == []


def test_diet_removes_or_protects_the_whole_pair():
    text = "비용이 늘었다. 그 결과 수익이 줄었다."
    segs = SentenceChunker().split(text)
    links = RuleLinkBuilder(text).build(segs)
    result = ClassOrderDieter(1).run(segs, text, {}, set(), links)
    assert result.kept == [] and len(result.removed) == 2
    result = ClassOrderDieter(1).run(segs, text, {}, {"s01"}, links)
    assert len(result.kept) == 2 and result.removed == []
