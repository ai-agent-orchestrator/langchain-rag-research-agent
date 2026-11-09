"""Filter profiles: anyone can write one JSON file and use it; bad profiles fail loudly."""
import json

import pytest

from rag_research_agent import Equalizer, list_profiles, load_profile
from rag_research_agent.core.types import Status
from rag_research_agent.rag.profile import PROFILES_DIR, ProfileError


def test_all_shipped_profiles_and_the_template_load():
    names = list_profiles()
    assert {"research", "litigation", "politics", "macro", "tech", "defense", "counseling"} <= set(names)
    for n in names + ["_template"]:
        p = load_profile(PROFILES_DIR / f"{n}.json")
        assert p.labeler.classes and p.diet_order


def test_custom_profile_from_template_changes_labels_and_diet(tmp_path):
    d = json.loads((PROFILES_DIR / "_template.json").read_text(encoding="utf-8"))
    d["name"] = "mine"
    d["ontology"]["classes"].insert(0, {"name": "날씨", "cues": ["날씨"]})
    d["ontology"]["never_remove"].append("날씨")
    f = tmp_path / "mine.json"
    f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    brief, trace = Equalizer.from_profile(f).brief("날씨가 맑았다. 귀추가 주목된다. 핵심은 비용이다.", budget=12)
    labels = {r["id"]: r["label"] for r in trace.rows}
    assert labels["s01"] == "날씨" and labels["s03"] == "핵심"
    assert any(r["id"] == "s01" and r["kept"] for r in trace.rows)       # never_remove class survives the diet


def test_profile_naming_undefined_classes_is_refused(tmp_path):
    f = tmp_path / "bad.json"
    f.write_text(json.dumps({"ontology": {"classes": [], "diet_order": ["없는분류"]}}), encoding="utf-8")
    with pytest.raises(ProfileError):
        load_profile(f)


def test_counseling_keeps_risk_signals_under_tight_budget():
    text = "회사 일이 많다. 요즘 잠을 못 잔다. 가끔 자해 생각이 든다. 가족과 다퉜다."
    brief, trace = Equalizer.from_profile("counseling").brief(text, budget=10)
    kept = {r["text"] for r in trace.rows if r.get("kept")}
    assert "가끔 자해 생각이 든다." in kept
    assert brief.status in (Status.OK, Status.BUDGET_PROTECTED_OVERFLOW)


def test_litigation_profile_refuses_external_and_uses_legal_pack():
    p = load_profile("litigation")
    assert not p.preset.external_allowed and p.preset.packs == ("legal",)
