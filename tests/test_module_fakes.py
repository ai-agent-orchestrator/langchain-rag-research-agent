"""One wiring test per module, using only fakes: proves each interface works without its real backend."""
from rag_research_agent.compose.protocols import FakeComposer, FakeOutputChecker
from rag_research_agent.core.types import Brief, Candidate, Knobs, Segment, Status
from rag_research_agent.diet.protocols import FakeDieter, FakeTokenBudget
from rag_research_agent.edge.protocols import FakeEdgeScorer, FakeProtectedPicker
from rag_research_agent.guard.protocols import FakeInputPolicy, FakeMasker
from rag_research_agent.ingest.protocols import FakeChunker
from rag_research_agent.knobs.protocols import FakeKnobMapper
from rag_research_agent.observe.protocols import FakeEvaluator, FakeTracer
from rag_research_agent.ontology.protocols import FakeLabeler, FakeLinkBuilder
from rag_research_agent.retrieve.protocols import FakeReranker, FakeRetriever
from rag_research_agent.store.protocols import FakeVectorStore

TEXT = "First point.\n\nSecond point."


def segments():
    return FakeChunker().split(TEXT, "doc")


def test_core_types_validate():
    assert Knobs(0.0, 1.0).edge_weight == 1.0
    for bad in (dict(similarity=-0.1), dict(edge_weight=1.1)):
        try:
            Knobs(**bad)
        except ValueError:
            continue
        raise AssertionError(bad)
    assert Status.BLOCKED.value == "BLOCKED"


def test_ingest_keeps_original_offsets():
    segs = segments()
    assert [TEXT[s.start:s.end] for s in segs] == ["First point.", "Second point."]


def test_guard_fakes():
    assert FakeMasker().mask("a") == "a"
    assert not FakeInputPolicy().check("x [BLOCK]").allowed and FakeInputPolicy().check("x").allowed


def test_ontology_fakes_never_drop_segments():
    segs = segments()
    assert FakeLabeler().label(segs) == segs and FakeLinkBuilder().build(segs) == []


def test_edge_fakes_one_score_per_segment():
    segs = segments()
    scores = FakeEdgeScorer().score(segs)
    assert [s.segment_id for s in scores] == [s.segment_id for s in segs]
    assert FakeProtectedPicker().pick(segs, scores) == []


def test_knobs_fake_maps_shield_to_extract_only():
    assert FakeKnobMapper().map(Knobs(0.5, 0.5)).extract_only and not FakeKnobMapper().map(Knobs(0.5, 0.4)).extract_only


def test_diet_fake_never_truncates():
    segs = segments()
    assert FakeDieter().reduce(segs, 0) == segs and FakeTokenBudget(1).check(segs).within is False


def test_compose_extractive_and_checked():
    brief = FakeComposer().compose(segments(), TEXT)
    assert brief.status is Status.OK and brief.final_prompt_input in TEXT.replace("\n\n", "\n") + TEXT
    assert FakeOutputChecker().check(Brief("invented 42", Status.OK), TEXT) is Status.OUTPUT_REJECTED


def test_retrieve_store_observe_fakes():
    assert FakeRetriever().retrieve("q", Knobs()) == [] and FakeVectorStore().search_lex("q") == []
    ranked = FakeReranker().rerank("q", [Candidate("a", 0.1), Candidate("b", 0.9)])
    assert [c.segment_id for c in ranked] == ["b", "a"]
    tracer = FakeTracer(); tracer.record("e", {})
    assert tracer.events == [("e", {})] and FakeEvaluator().evaluate([{}]) == {"rows": 1}
