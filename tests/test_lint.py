import json

import pytest

from rag_research_agent.rag.cli import main
from rag_research_agent.rag.lint import ROOT, WEIGHTS, check_file


def write(tmp_path, data):
    path = tmp_path / "synthetic.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_shipped_files_have_no_errors():
    paths = sorted((ROOT / "profiles").glob("*.json")) + [ROOT / "data/golden_rules/research_v1.json"]
    issues = [i for path in paths for i in check_file(path)]
    assert not [i for i in issues if i.severity == "error"]
    assert sum(i.severity == "warning" for i in issues) > 0


@pytest.mark.parametrize("data,fragment", [
    ({}, "필수 항목"),
    ({"ontology": {"classes": [{}]}}, "name"),
    ({"ontology": {"classes": [{"name": "A", "patterns": ["["]}]}}, "정규식"),
    ({"ontology": {"classes": [{"name": "A"}, {"name": "A"}]}}, "중복 ID"),
    ({"ontology": {"never_remove": ["missing"]}}, "정의 안 된"),
    ({"ontology": {}, "packs": ["missing"]}, "없는 묶음"),
    ({"ontology": {}, "focus": {str(n): 1 for n in range(6)}}, "최대 5"),
    ({"ontology": {}, "focus": {"bad": -1}}, "유한 숫자"),
    ({"ontology": {}, "focus": {"bad": "one"}}, "유한 숫자"),
    ({"ontology": {}, "knobs": {"similarity": "Ultra"}}, "노브 수준"),
    ({"causal_types": [], "weights": {}}, "필수 항목"),
])
def test_error_diagnostics(tmp_path, data, fragment):
    issues = check_file(write(tmp_path, data))
    assert any(i.severity == "error" and fragment in i.message for i in issues)


def test_json_syntax_and_cli_exit(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{broken", encoding="utf-8")
    assert main(["check", str(path)]) == 1
    assert main(["check", str(write(tmp_path, {"ontology": {}}))]) == 0


def test_all_warning_categories(tmp_path):
    data = {"causal_types": [], "weights": dict.fromkeys(WEIGHTS, 0),
            "pillar_rules": [{"id": "P1", "cues": ["겹침", "한"]}, {"id": "P2"}],
            "cliche_rules": [{"id": "X1", "cues": ["겹침"]}]}
    issues = check_file(write(tmp_path, data))
    messages = " ".join(i.message for i in issues if i.severity == "warning")
    assert all(word in messages for word in ("cue 중복", "한 글자", "동시 cue", "둘 다 없음", "첫 위치"))
    path = write(tmp_path, {"ontology": {"classes": [{"name": "A", "cues": ["가나다"]}]}})
    assert any("맨 뒤로" in i.message for i in check_file(path))
