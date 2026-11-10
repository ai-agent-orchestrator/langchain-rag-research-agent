from hashlib import sha256
import json
from pathlib import Path

from scripts.suggest_cues import candidate_terms, main, suggest
from rag_research_agent.edge.rules import load_rules

ROOT = Path(__file__).resolve().parents[1]


def test_unique_missed_expression_and_no_rule_edits(tmp_path):
    path = tmp_path / "synthetic.json"
    data = {"name": "synthetic", "draft": "핵심은 금리 5%다. 초전도성은 개선됐다.",
            "must_keep": ["초전도성은 개선됐다."], "cliche": []}
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    files = [path, *(ROOT / "profiles").glob("*.json"), *(ROOT / "data/golden_rules").glob("*.json")]
    before = {p: sha256(p.read_bytes()).hexdigest() for p in files}
    result = suggest(path, profile="litigation")
    missed, = [row for row in result["rows"] if row["missed"]]
    assert "초전도성" in [v["cue"] for v in missed["add_candidates"]]
    assert missed["profile_label"] == "Unclassified" and missed["profile_suggestions"]
    assert any(row["remove_candidates"] for row in result["rows"] if row["false_high"])
    assert main(["--set", str(path), "--profile", "litigation", "--out", str(tmp_path / "out")]) == 0
    assert (tmp_path / "out/cue_suggestions.json").is_file()
    assert {p: sha256(p.read_bytes()).hexdigest() for p in files} == before


def test_existing_cues_excluded_and_other_keep_support():
    rules = load_rules(ROOT / "data/golden_rules/research_v1.json")
    known = rules.pillar_rules[0].cues[0]
    result = candidate_terms(f"{known} 초전도성은 나타났다", rules, ["초전도성 자료다."])
    assert all(row["cue"] != known for row in result)
    assert next(row for row in result if row["cue"] == "초전도성")["support"] == 1
