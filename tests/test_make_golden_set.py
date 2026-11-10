import json
import pytest

from scripts.make_golden_set import ROOT, main, make_set
from scripts.golden_edge_eval import split_sentences


def test_marks_comments_and_multi_sentence_warning():
    with pytest.warns(UserWarning, match="여러 문장"):
        data = make_set("# 주석\n+ 핵심은 비용이다. 수익이 줄었다.\n- 귀추가 주목된다.\n날씨는 맑다.", "synthetic")
    assert data["must_keep"] == ["핵심은 비용이다.", "수익이 줄었다."]
    assert data["cliche"] == ["귀추가 주목된다."]
    assert "주석" not in data["draft"]
    values = {data["draft"][s.start:s.end] for s in split_sentences(data["draft"])}
    assert set(data["must_keep"] + data["cliche"]) <= values


def test_generate_and_check(tmp_path, capsys):
    source, out = tmp_path / "marked.txt", tmp_path / "golden.json"
    source.write_text("+ 핵심은 비용이다.\n- 귀추가 주목된다.", encoding="utf-8-sig")
    assert main([str(source), "--name", "synthetic", "--out", str(out), "--check"]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["name"] == "synthetic"
    assert "keep_recall_at_k" in capsys.readouterr().out


def test_forbidden_output_and_invalid_boundaries(tmp_path):
    source = tmp_path / "marked.txt"
    source.write_text("+ 합성 문장이다.", encoding="utf-8")
    assert main([str(source), "--name", "synthetic", "--out", str(ROOT / "data/forbidden.json")]) == 2
    assert not (ROOT / "data/forbidden.json").exists()
    with pytest.raises(ValueError, match="문장부호"):
        make_set("+ 문장부호 없음\n다음 문장.", "synthetic")
