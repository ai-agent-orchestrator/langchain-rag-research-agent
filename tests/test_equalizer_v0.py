"""Equalizer v0 parts: each is tested alone, then wired through build_brief with swappable parts."""
from rag_research_agent.compose.extractive import ExtractiveComposer, NumberIdOutputChecker
from rag_research_agent.core.types import Brief, CausalLink, Knobs, LinkType, Segment, Status
from rag_research_agent.diet.dieter import ClassOrderDieter
from rag_research_agent.guard.protocols import FakeInputPolicy
from rag_research_agent.ingest.sentences import SentenceChunker
from rag_research_agent.knobs.mapper import LinearKnobMapper, blend, load_config
from rag_research_agent.rag.brief import DEFAULT_CONFIG, Parts, build_brief
from rag_research_agent.edge.scorer import RuleEdgeScorer

DRAFT = ("금리는 3.0%에서 3.5%로 올랐다. 앞으로의 흐름에 귀추가 주목된다. "
         "소비 둔화는 금리 때문으로 보였지만 실제로는 가계부채 부담이 누적된 결과였다. "
         "두 지표는 함께 움직였지만 인과는 확인되지 않았다.")


def test_mapper_is_monotonic_and_switches_extract_only_at_half():
    m = LinearKnobMapper()
    lo, hi = m.map(Knobs(0.0, 0.4)), m.map(Knobs(1.0, 0.5))
    assert lo.threshold < hi.threshold and lo.top_k > hi.top_k
    assert not lo.extract_only and hi.extract_only and hi.protected_path
    assert blend(1.0, 0.0, 0.25) == 0.75


def test_filters_load_with_design_aliases_and_litigation_refuses_external():
    cfg = load_config(DEFAULT_CONFIG)
    names = {p.name for p in cfg.presets.values()}
    assert {"research", "litigation", "politics", "macro", "tech", "defense", "counseling"} <= names
    assert cfg.presets["litigation_evidence"] is cfg.presets["litigation"]       # design name still works
    assert not cfg.presets["litigation"].external_allowed and cfg.presets["litigation"].packs == ("legal",)


def segs(text):
    return SentenceChunker().split(text)


def test_dieter_removes_lowest_first_never_truncates_and_reports_overflow():
    ss = segs(DRAFT)
    scores = {s.segment_id: i / 10 for i, s in enumerate(ss)}
    res = ClassOrderDieter(budget=len(DRAFT) - 30).run(ss, DRAFT, scores, protected=set())
    assert res.removed[0][0] == ss[0].segment_id and res.status is Status.OK
    assert all(DRAFT[k.start:k.end] in DRAFT for k in res.kept)
    over = ClassOrderDieter(budget=5).run(ss, DRAFT, scores, protected={s.segment_id for s in ss})
    assert over.status is Status.BUDGET_PROTECTED_OVERFLOW and over.removed == []


def test_dieter_removes_linked_pairs_together():
    ss = segs(DRAFT)
    link = [CausalLink(ss[0].segment_id, ss[2].segment_id, LinkType.CAUSES)]
    scores = {s.segment_id: 0.5 for s in ss}
    scores[ss[0].segment_id] = 0.0
    res = ClassOrderDieter(budget=len(DRAFT) - 10).run(ss, DRAFT, scores, set(), link)
    removed = {x for x, _ in res.removed}
    assert {ss[0].segment_id, ss[2].segment_id} <= removed


def test_composer_is_extractive_and_checker_rejects_new_numbers_and_ids():
    ss = segs(DRAFT)
    b = ExtractiveComposer().compose(ss[:1], DRAFT)
    assert "[s01] 금리는 3.0%에서 3.5%로 올랐다." in b.final_prompt_input
    chk = NumberIdOutputChecker()
    assert chk.check(b, DRAFT) is Status.OK
    assert chk.check(Brief("[s01] 금리가 9.9% 올랐다", Status.OK, ("s01",)), DRAFT) is Status.OUTPUT_REJECTED
    assert chk.check(Brief("[s99] 금리는 3.0%", Status.OK, ("s01",)), DRAFT) is Status.OUTPUT_REJECTED


def test_build_brief_blocks_and_requests_more_without_generation():
    b, t = build_brief(DRAFT + " [BLOCK]")
    assert b.status is Status.BLOCKED and b.final_prompt_input == ""
    b, t = build_brief(DRAFT, task="반도체 수출", knobs=Knobs(0.9, 0.2))
    assert b.status is Status.REQUEST_MORE and b.final_prompt_input == ""


def test_knobs_are_independent_protected_survive_high_similarity():
    counts, protected = [], []
    for s in (0.0, 0.5, 1.0):
        b, t = build_brief(DRAFT, task="금리 가계부채", knobs=Knobs(s, 0.8), budget=10_000)
        counts.append(sum(r["chosen"] and not r["protected"] for r in t.rows))
        protected.append({r["id"] for r in t.rows if r["protected"]})
    assert counts == sorted(counts, reverse=True)
    assert protected[0] == protected[1] == protected[2] != set()


def test_parts_can_be_swapped():
    calls = []

    def scorer_factory(*a, **k):
        calls.append("custom")
        return RuleEdgeScorer(*a, **k)

    class AllowAll(FakeInputPolicy):
        def check(self, text):
            from rag_research_agent.guard.protocols import PolicyDecision
            return PolicyDecision(True)

    b, _ = build_brief(DRAFT + " [BLOCK]", parts=Parts(scorer_factory=scorer_factory, input_policy=AllowAll()))
    assert calls == ["custom"] and b.status is Status.OK


def test_board_runs_filters_on_golden_sets(tmp_path):
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts"))
    import filter_board as fb
    rows = fb.run_board(sorted((root / "data/golden_sets").glob("*.json")), ["research", "litigation"], False, 300, None)
    assert {r["config"] for r in rows} == {"research", "litigation"}
    assert all(0.0 <= r["keep_hit"] <= 1.0 for r in rows)
    assert fb.main(["--profiles", "litigation", "--runs", str(tmp_path)]) == 0
    assert (tmp_path / "board.html").read_text(encoding="utf-8").startswith("<!doctype html>")
