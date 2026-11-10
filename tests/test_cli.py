"""End-to-end CLI tests with synthetic text and no external network."""
import json
import socket
from hashlib import sha256

import pytest

from rag_research_agent.rag.cli import main
from rag_research_agent.rag.profile import PROFILES_DIR


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*a, **kw):
        raise AssertionError("test attempted a network connection")
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)


def test_brief_file_writes_settings_trace_and_original(tmp_path, capsys):
    source = tmp_path / "synthetic.txt"
    source.write_text("핵심은 계약서다. 다만 손해액은 비용에 한정된다. 귀추가 주목된다.", encoding="utf-8")
    out = tmp_path / "runs"
    assert main(["brief", "--profile", "litigation", "--file", str(source), "--budget", "30",
                 "--focus", "손해액:2", "--auto-focus", "2", "--out", str(out)]) == 0
    folder, = out.iterdir()
    assert (folder / "input.txt").read_text(encoding="utf-8") == source.read_text(encoding="utf-8")
    trace = json.loads((folder / "trace.json").read_text(encoding="utf-8"))
    assert trace["profile_hash"] == sha256((PROFILES_DIR / "litigation.json").read_bytes()).hexdigest()
    assert trace["rule_version"] and trace["rows"]
    assert all({"id", "label", "edge", "protected", "reason", "explanation"} <= row.keys() for row in trace["rows"])
    assert trace["settings"]["focus"]["손해액"] == 2
    markdown = (folder / "brief.md").read_text(encoding="utf-8")
    assert all(title in markdown for title in ("설정", "상태", "남긴 문장", "생략 번호와 사유", "감량 기록"))
    assert capsys.readouterr().out.strip().endswith(str(folder.resolve()))


def test_network_default_off_returns_input_error(tmp_path, capsys):
    assert main(["brief", "--profile", "litigation", "--url", "https://example.invalid/test",
                 "--out", str(tmp_path / "runs")]) == 2
    assert "--allow-network" in capsys.readouterr().err
    assert not (tmp_path / "runs").exists()


def test_multiple_files_have_index_and_individual_traces(tmp_path):
    paths = [tmp_path / "one.md", tmp_path / "two.txt"]
    for path in paths:
        path.write_text("핵심은 비용이다. 다만 범위는 한정된다.", encoding="utf-8")
    out = tmp_path / "runs"
    assert main(["brief", "--profile", "litigation", "--file", str(paths[0]), "--file", str(paths[1]),
                 "--out", str(out)]) == 0
    root, = out.iterdir()
    assert (root / "index.md").is_file()
    assert len(list(root.glob("*/trace.json"))) == 2


def test_multiple_fake_urls(tmp_path, monkeypatch):
    from rag_research_agent.ingest import sources
    calls = []
    def fetcher(url):
        calls.append(url)
        return 200, "text/plain", "핵심은 계약서다.".encode()
    monkeypatch.setattr(sources, "_fetch", fetcher)
    assert main(["brief", "--profile", "litigation", "--url", "https://example.invalid/one",
                 "https://example.invalid/two", "--allow-network", "--out", str(tmp_path / "runs")]) == 0
    assert len(calls) == 2


def test_blocked_input_returns_three_and_records_status(tmp_path):
    assert main(["brief", "--profile", "litigation", "--text", "[BLOCK] 합성 차단 입력",
                 "--out", str(tmp_path)]) == 3
    trace, = tmp_path.glob("*/trace.json")
    assert json.loads(trace.read_text(encoding="utf-8"))["status"] == "BLOCKED"


def test_profiles_and_board(tmp_path, capsys):
    assert main(["profiles"]) == 0
    assert "litigation\t" in capsys.readouterr().out
    assert main(["board", "--profiles", "litigation", "--out", str(tmp_path)]) == 0
    assert (tmp_path / "board.html").read_text(encoding="utf-8").startswith("<!doctype html>")


def test_score_uses_existing_evaluator(tmp_path, monkeypatch, capsys):
    gset = tmp_path / "synthetic.json"
    gset.write_text(json.dumps({"name": "synthetic", "draft": "핵심은 비용이다.", "must_keep": ["핵심은 비용이다."]}), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert main(["score", "--set", str(gset), "--packs", "macro", "--focus", "비용:2"]) == 0
    assert "Edge eval: synthetic" in capsys.readouterr().out
    assert (tmp_path / ".runs/last_report.md").is_file()


@pytest.mark.parametrize("arguments", [[], ["brief"], ["brief", "--profile", "litigation", "--text", "합성", "--budget", "0"],
                                        ["brief", "--profile", "litigation", "--text", "합성", "--focus", "비용:nan"],
                                        ["brief", "--profile", "missing", "--text", "합성"]])
def test_input_errors_return_two(arguments):
    assert main(arguments) == 2
