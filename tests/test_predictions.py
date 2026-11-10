from datetime import datetime, timezone
import pytest

from rag_research_agent.rag.predictions import PredictionLog
from scripts.predictions import main


def test_add_resolve_summary_and_append_only(tmp_path):
    path = tmp_path / "predictions.jsonl"
    log = PredictionLog(path, clock=lambda: datetime(2026, 11, 10, tzinfo=timezone.utc))
    first = log.add("합성 예측", "macro", ["s01"], "synthetic/brief.md", "2026-11-09", 0.6, ["cost"])
    second = log.add("다른 예측", "research", [], "synthetic/brief.md", "2026-11-08", tags=["cost"])
    assert log.summary()["overdue"] == 2 and len(log.list(True)) == 2
    before = path.read_bytes()
    log.resolve(first, "hit", "합성 결과")
    assert path.read_bytes().startswith(before) and len(path.read_text(encoding="utf-8").splitlines()) == 3
    summary = log.summary()
    assert summary["profiles"]["macro"]["hit_rate"] == 1
    assert summary["tags"]["cost"]["overdue"] == 1
    log.resolve(first, "partial", "정정")
    assert log.summary()["hit_rate"] == 0.5 and len(log.list(True)) == 1
    log.resolve(second, "void", "평가 불가")
    assert log.summary()["void"] == 1 and log.summary()["overdue"] == 0


def test_invalid_results_dates_and_confidence_do_not_append(tmp_path):
    path = tmp_path / "predictions.jsonl"
    log = PredictionLog(path)
    with pytest.raises(ValueError):
        log.resolve("missing", "win")
    with pytest.raises(ValueError):
        log.add("synthetic", "macro", [], "brief.md", "invalid")
    with pytest.raises(ValueError):
        log.add("synthetic", "macro", [], "brief.md", "2027-01-01", confidence=2)
    assert not path.exists()


def test_cli_add_and_list(tmp_path, capsys):
    path = str(tmp_path / "log.jsonl")
    assert main(["--path", path, "add", "--statement", "합성 예측", "--profile", "macro", "--brief-path", "synthetic", "--due", "2027-01-01"]) == 0
    assert main(["--path", path, "list", "--open-only"]) == 0
    assert "합성 예측" in capsys.readouterr().out
