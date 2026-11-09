"""Golden rules are data: the scorer's behaviour must change when (and only when) the data file changes."""
import json
import sys
from pathlib import Path

import pytest

from rag_research_agent.core.types import Segment
from rag_research_agent.edge.rules import RulesError, load_rules, parse_rules
from rag_research_agent.edge.scorer import RuleEdgeScorer, RuleProtectedPicker, focus_brief

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "data/golden_rules/research_v1.json"
SET = ROOT / "data/golden_sets/macro_synthetic_v1.json"


def seg(text, sid="s1"):
    return Segment(sid, "t", 0, len(text))


def test_shipped_rules_have_150_common_rules_and_domain_packs():
    rules = load_rules(RULES)
    assert len(rules.causal_types) + len(rules.pillar_rules) + len(rules.cliche_rules) + len(rules.weight_rules) == 150
    assert {t.id for t in rules.causal_types if t.always_protect} == {19, 20, 25, 28}
    assert set(rules.packs) == {"macro", "geopolitics", "tech", "defense", "legal"}


def test_every_edit_is_a_new_version():
    raw = RULES.read_bytes()
    edited = raw.replace(b'"name": "research"', b'"name": "research-edit"')
    assert parse_rules(raw).rule_version != parse_rules(edited).rule_version


def test_bad_files_are_refused():
    with pytest.raises(RulesError):
        parse_rules(b"{not json")
    data = json.loads(RULES.read_bytes())
    del data["weights"]["concreteness"]
    with pytest.raises(RulesError):
        parse_rules(json.dumps(data).encode())


def test_causal_and_cliche_sentences_rank_apart():
    rules = load_rules(RULES)
    causal = "소비 둔화는 금리 때문으로 보였지만 실제로는 부담이 누적된 결과였다."
    cliche = "앞으로의 흐름에 귀추가 주목된다."
    s = RuleEdgeScorer(rules, causal)
    c = RuleEdgeScorer(rules, cliche)
    assert s.score_one(seg(causal)).total > c.score_one(seg(cliche)).total == 0.0
    assert 8 in s.explain_one(seg(causal)).causal_ids


def test_changing_a_weight_changes_the_score():
    raw = json.loads(RULES.read_bytes())
    text = "금리는 3.0%에서 3.5%로 0.5%p 올랐다."
    base = RuleEdgeScorer(parse_rules(json.dumps(raw).encode()), text).score_one(seg(text)).total
    raw["weights"]["concreteness"] = 0.0
    lower = RuleEdgeScorer(parse_rules(json.dumps(raw).encode()), text).score_one(seg(text)).total
    assert lower < base


def test_protected_picker_uses_always_protect_types():
    rules = load_rules(RULES)
    text = "두 지표는 함께 움직였지만 인과는 확인되지 않았다."
    scorer = RuleEdgeScorer(rules, text)
    picked = RuleProtectedPicker(scorer).pick([seg(text)], scorer.score([seg(text)]))
    assert [c.from_protected_path for c in picked] == [True]


def test_feedback_script_runs_on_the_synthetic_set():
    sys.path.insert(0, str(ROOT / "scripts"))
    import golden_edge_eval as ev
    run = ev.evaluate(RULES, SET, ["macro"])
    assert run["unknown_lines"] == []
    assert run["metrics"]["cliche_in_bottom"] == 1.0
    assert 0.0 <= run["metrics"]["keep_recall_at_k"] <= 1.0
    assert "지난 실행과 비교" in ev.render(run, run)


def test_cliche_wording_next_to_real_content_is_not_penalized():
    rules = load_rules(RULES)
    empty = "앞으로의 흐름에 귀추가 주목된다."
    loaded = "수출이 3개월 연속 감소한 점은 주목할 필요가 있다."
    e_empty = RuleEdgeScorer(rules, empty).score_one(seg(empty))
    s_loaded = RuleEdgeScorer(rules, loaded)
    assert e_empty.cliche_penalty == 1.0 and e_empty.total == 0.0
    assert s_loaded.explain_one(seg(loaded)).cliches and s_loaded.score_one(seg(loaded)).cliche_penalty == 0.0


def test_legal_pack_must_be_switched_on_and_unknown_packs_fail():
    rules = load_rules(RULES)
    text = "원고의 과실로 인해 손해가 발생했다는 점이 입증된다."
    assert RuleEdgeScorer(rules, text).explain_one(seg(text)).packs == ()
    assert RuleEdgeScorer(rules, text, ["legal"]).explain_one(seg(text)).packs
    with pytest.raises(ValueError):
        RuleEdgeScorer(rules, text, ["nope"])


def test_focus_keywords_boost_highlight_and_never_drop_silently():
    rules = load_rules(RULES)
    text = "금리가 올랐다. 날씨가 맑았다. 두 지표의 인과는 확인되지 않았다."
    parts = ["금리가 올랐다.", "날씨가 맑았다.", "두 지표의 인과는 확인되지 않았다."]
    segs = [Segment(i, "t", text.index(p), text.index(p) + len(p)) for i, p in zip("abc", parts)]
    plain = RuleEdgeScorer(rules, text)
    focused = RuleEdgeScorer(rules, text, focus={"금리": 1.0})
    assert focused.score_one(segs[0]).total > plain.score_one(segs[0]).total
    brief = focus_brief(focused, segs)
    assert brief["focus"][0][1] == "**금리**가 올랐다."
    assert [i for i, _ in brief["caveats"]] == ["c"] and brief["omitted"] == ["b"]
    with pytest.raises(ValueError):
        RuleEdgeScorer(rules, text, focus={k: 1.0 for k in "abcdef"})


def test_auto_focus_counts_meaningful_words_and_keeps_manual_first():
    from rag_research_agent.edge.focus import build_focus, frequent_terms
    text = "금리가 올랐다. 금리는 다시 올랐다. 가계부채가 늘었다. 가계부채 부담이 커졌다. 중요한 의미를 가진다."
    assert [t for t, _ in frequent_terms(text, 2)] == ["가계부채", "금리"]
    focus = build_focus(text, {"2025년": 2.0}, auto_min_count=2)
    assert list(focus) == ["2025년", "가계부채", "금리"]


def test_single_letter_party_name_does_not_match_particles():
    rules = load_rules(RULES)
    text = "을은 보증금 반환을 요구했다. 좋을 것이다."
    sc = RuleEdgeScorer(rules, text, focus={"을": 1.0})
    seg_all = Segment("a", "t", 0, len(text))
    assert focus_brief(sc, [seg_all])["focus"][0][1] == "**을**은 보증금 반환을 요구했다. 좋을 것이다."


def test_weight_rules_boost_score():
    rules = load_rules(RULES)
    plain = "수출이 늘었다."
    boosted = "수출이 사상 처음으로 급증했다."
    assert RuleEdgeScorer(rules, boosted).score_one(seg(boosted)).total > RuleEdgeScorer(rules, plain).score_one(seg(plain)).total
