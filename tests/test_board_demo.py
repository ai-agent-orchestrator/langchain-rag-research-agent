"""Offline demo integration through real runners, filters, events and HTML."""
from dataclasses import replace
from html.parser import HTMLParser
import json

import pytest

from scripts import board_demo as demo
from scripts import metrics_board


class Markup(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.configs = []
        self.unsafe = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "tr" and "data-config" in attrs:
            self.configs.append(attrs["data-config"])
        if tag == "img" or "onerror" in attrs:
            self.unsafe.append(tag)


@pytest.fixture(scope="module")
def execution(tmp_path_factory):
    # Use original case packs, actual JsonlSink, and a separate .runs project.
    project = tmp_path_factory.mktemp("r57")
    original = demo.ROOT
    with pytest.MonkeyPatch.context() as patch:
        patch.chdir(project)
        patch.setattr(demo, "ROOT", project)
        output = demo.main(["--out", str(project / ".runs/board/index.html"),
                            "--cases", str(original / "evals/research/cases.ko.json"),
                            "--legal-cases", str(original / "evals/domains/legal/cases.json")])
    report = json.loads(next(output.parent.glob("index-*.json")).read_text(encoding="utf-8"))
    events = metrics_board.load_events(project / ".runs/events")
    return output, report, events


def test_demo_html_and_four_config_rows_per_domain_and_k(execution):
    output, report, events = execution
    html = output.read_text(encoding="utf-8")
    parsed = Markup(html)
    assert len(parsed.configs) == 16
    for name in demo.CONFIGS:
        assert parsed.configs.count(name) == 4
    assert {row["k"] for row in report["rows"]} == {1, 3}
    assert {e.domain for e in events} == {"research", "legal"}
    assert len(events) == len(report["rows"]) > 0
    assert {e.run_id for e in events} == {row["run_id"] for row in report["rows"]}
    assert all(e.nodes and e.path and e.estimated for e in events)
    assert any("verify" in e.path for e in events)
    assert all(e.config.endswith((";k=1", ";k=3")) for e in events)
    assert "Wilson 95%" in html and "합성 문항·규칙/가짜 모델 기준" in html
    assert "별도 R44" in html and "human" in html
    assert report["grounding"][demo.CONFIGS[3]]
    assert all(1 <= row["judge_score"] <= 5 for row in report["rows"])


def test_comparison_escapes_labels(execution):
    _, report, events = execution
    attack = '</script><img src=x onerror="alert(1)">'
    row = {**report["rows"][0], "config": attack, "domain": attack}
    html = metrics_board.render([replace(events[0], run_id=row["run_id"])],
                                comparison={"rows": [row]})
    assert attack not in html and "&lt;/script&gt;&lt;img" in html
    assert not Markup(html).unsafe


def test_empty_comparison_and_unknown_run(execution):
    html = metrics_board.render([], comparison={"rows": []})
    assert 'id="config-comparison"' in html and "미검증 (n=0)" in html
    assert not Markup(html).configs
    assert "nan" not in html.lower()
    with pytest.raises(ValueError, match="unknown run"):
        metrics_board.render([], comparison=execution[1])


def test_injection_excluded_from_comparison(execution):
    _, report, events = execution
    html = metrics_board.render(events, comparison=report,
                                injection_run_ids=[e.run_id for e in events])
    assert not Markup(html).configs


def test_reject_output_outside_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(demo, "ROOT", tmp_path / "project")
    with pytest.raises(ValueError, match="inside .runs"):
        demo.run_demo(out=tmp_path / "bad.html", cases=demo.research_eval.CASES,
                      legal_cases=tmp_path / "unused.json")


def test_empty_packs_create_html(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(demo, "ROOT", tmp_path)
    folder = tmp_path / ".runs"
    folder.mkdir()
    pack = folder / "empty.json"
    pack.write_text('{"cases": []}', encoding="utf-8")
    output = demo.main(["--cases", str(pack), "--legal-cases", str(pack),
                        "--out", str(folder / "empty.html")])
    assert str(output) in capsys.readouterr().out
    html = output.read_text(encoding="utf-8")
    assert "미검증 (n=0)" in html and not Markup(html).configs


@pytest.mark.parametrize("ks", [(), (0,), (1, 1)])
def test_invalid_k_rejected_before_execution(tmp_path, monkeypatch, ks):
    monkeypatch.setattr(demo, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="unique positive"):
        demo.run_demo(out=tmp_path / ".runs/index.html", cases=tmp_path / "unused.json",
                      legal_cases=tmp_path / "unused.json", ks=ks)
