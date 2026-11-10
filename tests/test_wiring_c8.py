import pytest

from rag_research_agent.core.contracts import Chunk
from rag_research_agent.core.types import Knobs
from rag_research_agent.rag.brief import Parts
from rag_research_agent.rag.library import Library
from rag_research_agent.rag.profile import Equalizer


def test_v1_causal_pair_survives_or_leaves_together():
    eq = Equalizer.from_profile("research")
    text = "비용이 늘었다. 그 결과 수익이 줄었다."
    for budget in (1, 1000):
        brief, trace = eq.brief(text, budget=budget, knobs=Knobs(0, 0), parts_preset="v1")
        assert set(brief.included_ids) in (set(), {"s01", "s02"})
    assert type(Parts().link_builder).__name__ == "FakeLinkBuilder"
    assert type(eq.parts("v1").link_builder).__name__ == "RuleLinkBuilder"
    with pytest.raises(ValueError):
        eq.parts("unknown")


def test_library_semantic_option_uses_embedder_without_store(tmp_path, monkeypatch):
    lib = Library(tmp_path)
    chunk = Chunk("SYNTH", "SYNTH:c01:v1", "v1", "synthetic", "title", "금리 비용이 늘었다. 날씨는 맑다.", 22, "v1", "m1", "p1")
    lib.chunks = [chunk]
    monkeypatch.setattr(lib, "search", lambda *a: [(chunk, 1.0, 1)])
    brief, trace, hits = lib.brief("금리", relevance="semantic", parts_preset="v1")
    assert hits and trace.rows and all(0 <= r["relevance"] <= 1 for r in trace.rows)
    with pytest.raises(ValueError):
        lib.brief("금리", relevance="unknown")
