"""Golden rules are data: the scorer's behaviour must change when (and only when) the data file changes."""
import json
import sys
from pathlib import Path

import pytest

from rag_research_agent.core.types import Segment
from rag_research_agent.edge.rules import RulesError, load_rules, parse_rules
from rag_research_agent.edge.scorer import RuleEdgeScorer, RuleProtectedPicker

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "data/golden_rules/research_v1.json"
SET = ROOT / "data/golden_sets/macro_synthetic_v1.json"


def seg(text, sid="s1"):
    return Segment(sid, "t", 0, len(text))


def test_shipped_rules_load_with_thirty_causal_types():
    rules = load_rules(RULES)
    assert len(rules.causal_types) == 30
    assert {t.id for t in rules.causal_types if t.always_protect} == {19, 20, 25, 28}


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
