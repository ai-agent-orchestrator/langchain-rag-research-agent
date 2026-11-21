import pytest

from rag_research_agent.core.types import Segment
from rag_research_agent.edge.signals import (SIGNALS, FakeSurprisalScorer, SegmentSignals, collect, combine,
                                             rank01)


def segs(n):
    return [Segment(f"s{i}", "doc", i * 10, i * 10 + 5) for i in range(n)]


def test_rank01_ties_and_single():
    assert rank01([5.0]) == [0.5]
    assert rank01([1.0, 3.0, 2.0]) == [0.0, 1.0, 0.5]
    assert rank01([2.0, 2.0]) == [0.5, 0.5]


def test_collect_aligns_and_ranks():
    out = collect(segs(3), [0, 1, 0], [0.2, 0.9, 0.5], [3.0, 1.0, 2.0])
    assert [s.segment_id for s in out] == ["s0", "s1", "s2"]
    assert out[1].similarity == 1.0 and out[0].surprisal == 1.0


def test_collect_raw_values_kept_without_rank():
    out = collect(segs(2), [0.3, 0.1], [0.4, 0.2], [0.5, 0.6], as_rank=False)
    assert out[0] == SegmentSignals("s0", 0.3, 0.4, 0.5)


def test_collect_length_mismatch():
    with pytest.raises(ValueError):
        collect(segs(2), [0], [0, 1], [0, 1])


def test_combine_requires_explicit_weights():
    s = SegmentSignals("s0", edge=1.0, similarity=0.5, surprisal=0.0)
    with pytest.raises(ValueError):
        combine(s, {"edge": 1.0})
    with pytest.raises(ValueError):
        combine(s, {"edge": -1, "similarity": 1, "surprisal": 1})
    with pytest.raises(ValueError):
        combine(s, {k: 0 for k in SIGNALS})
    assert combine(s, {"edge": 1, "similarity": 1, "surprisal": 0}) == 0.75


def test_fake_surprisal_scorer():
    assert FakeSurprisalScorer().score(["a", "b"]) == [0.0, 0.0]
