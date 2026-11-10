import json
from pathlib import Path

import pytest
from scripts.board_diff import compare, main, render, history_series

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("name", ["macro_synthetic_v1", "legal_synthetic_v1"])
def test_comparison_and_identical_filters(name):
    path = ROOT / f"data/golden_sets/{name}.json"
    same = compare(path, "litigation", "litigation", 100)
    assert same["differences"] == 0
    different = compare(path, "litigation", "research", 100)
    assert different["rows"]
    flags = [row["different"] for row in different["rows"]]
    assert flags == sorted(flags, reverse=True)
    page, md = render(different, {})
    assert "overflow-x:auto" in page and "A 분류" in md


def test_history_missing_and_present(tmp_path):
    missing = tmp_path / "missing.jsonl"
    assert main(["--history", str(missing), "--out", str(tmp_path)]) == 0
    assert "기록이 없습니다" in (tmp_path / "board_diff.html").read_text(encoding="utf-8")
    history = tmp_path / "history.jsonl"
    history.write_text("\n".join(json.dumps({"rows": [{"set": "synthetic", "config": "research", "keep_hit": v, "cliche_left": 1}]}) for v in (0.2, 0.8)), encoding="utf-8")
    assert main(["--history", str(history), "--out", str(tmp_path)]) == 0
    assert "<svg" in (tmp_path / "board_diff.html").read_text(encoding="utf-8")
    assert history_series(history)["synthetic / research"]["keep_hit"] == [0.2, 0.8]
