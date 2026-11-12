"""Synthetic event path tests through real RunEvent, R37 and HTML renderer."""
from dataclasses import replace
from html.parser import HTMLParser
import json

import pytest

from rag_research_agent.core.run_events import NodeEvent, RunEvent
from rag_research_agent.rag.guard_audit import GoldEvidence
from scripts.metrics_board import ROOT, load_events, main, render


def event(run_id="run-a1", domain="research", **changes):
    original = RunEvent(
        run_id=run_id, domain=domain, track="deep", config="graph_full",
        dataset="synthetic", sha="abc1234", path=("retrieve", "grade", "rewrite"),
        end_type="END", loops={"rewrite": 1, "gap": 0, "verify": 0},
        calls={"slm": 2, "flagship": 1}, tokens={"in": 120, "out": 20},
        cost_krw=1.2, ttft_ms=40, total_ms=80,
        grade={"docs_in": 4, "docs_kept": 3, "relevance_drop_rate": .25},
        guard=({"gate": "grounded", "code": "UNSUPPORTED_NUMBER",
                "reason": "수치 불일치", "span": ""},),
        nodes=(NodeEvent("retrieve", 20, 0, 0, None, True),), estimated=True,
    )
    return replace(original, **changes)


class Markup(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.tags = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def test_two_domains_have_isolated_four_panels_and_tabs():
    html = render([event(), event("run-b2", "legal", track="fast", cost_krw=3)])
    tags = Markup(html).tags
    tabs = [a for t, a in tags if a.get("role") == "tab"]
    assert len(tabs) == 2
    assert [a["aria-selected"] for a in tabs] == ["true", "false"]
    bodies = [a for t, a in tags if a.get("role") == "tabpanel"]
    assert "hidden" not in bodies[0] and "hidden" in bodies[1]
    assert CounterPanels(tags) == {"trace": 2, "cost": 2, "guard": 2, "latency": 2}
    legal, research = html.split('id="domain-0"', 1)[1].split('id="domain-1"', 1)
    assert "3.0000" in legal and "1.2000" not in legal
    assert "1.2000" in research and "3.0000" not in research
    assert "SLM 호출 수: 2" in research and "입력 토큰: 120" in research
    assert "출력 토큰: 20" in research and "TTFT 평균 ms: 40.00" in research
    assert "25.0% (1/4; Wilson 95%" in research


def CounterPanels(tags):
    from collections import Counter
    return Counter(a["data-panel"] for _, a in tags if "data-panel" in a)


def test_empty_data_still_has_four_panels_and_no_nan():
    html = render(iter(()))
    assert CounterPanels(Markup(html).tags) == {"trace": 1, "cost": 1, "guard": 1, "latency": 1}
    assert "실행 기록 없음" in html and "미검증 (n=0)" in html
    assert "nan" not in html.lower() and "Infinity" not in html


def test_untrusted_fields_are_text_even_script_end_tags():
    attack = '</script><img src=x onerror="alert(1)">&\''
    e = event(domain=attack, path=(attack,),
              nodes=(NodeEvent(attack, 1, 0, 0, None, True),),
              guard=({"gate": "grounded", "code": attack, "reason": attack, "span": ""},))
    html = render([e])
    assert attack not in html and "&lt;/script&gt;&lt;img" in html
    assert not any(t == "img" or "onerror" in a for t, a in Markup(html).tags)
    assert sum(t == "script" for t, _ in Markup(html).tags) == 1


def test_estimated_cohorts_are_separate_and_latency_is_node_weighted():
    measured = event("run-b2", estimated=False,
                     nodes=(NodeEvent("generate", 30, 120, 20, "model-a", False),))
    html = render([event(), measured])
    assert "estimated=true" in html and "estimated=false" in html
    assert CounterPanels(Markup(html).tags)["cost"] == 2
    html = render([event(), event("run-c3", nodes=(NodeEvent("retrieve", 60, 0, 0, None, True),))])
    assert "retrieve: 40.00 ms" in html


def test_r37_gold_and_explicit_injection_exclusion():
    e = event()
    injection = event("run-inj", guard=({"gate": "filter", "code": "INJECTION",
                                        "reason": "차단", "span": ""},))
    labels = GoldEvidence(("doc-d4",), ("doc-a1", "doc-b2", "doc-c3", "doc-d4"),
                          ("doc-a1", "doc-b2", "doc-c3"))
    html = render([e, injection], gold={e.run_id: labels}, injection_run_ids=["run-inj"])
    assert "RelevanceGrade 탈락률: 25.0% (1/4; Wilson 95%" in html
    assert "과차단 의심: 100.0% (1/1; Wilson 95%" in html
    assert "INJECTION: 1회" in html and "품질 실행 수: 1" in html
    assert "과차단 의심: 미검증 (n=0)" in render([e])


def test_jsonl_loading_and_cli_write_real_events(tmp_path):
    folder = tmp_path / "batch-a"
    folder.mkdir()
    (folder / "events.jsonl").write_text(event().to_json(dumps=json.dumps) + "\n\n", encoding="utf-8")
    assert load_events(tmp_path) == [event()]
    output = ROOT / ".runs/r38/test-board.html"
    main(["--events", str(tmp_path), "--output", str(output)])
    assert "data-panel=\"guard\"" in output.read_text(encoding="utf-8")


@pytest.mark.parametrize("payload", ["{", "{}", "[]"])
def test_bad_records_fail_without_echoing_contents(tmp_path, payload):
    folder = tmp_path / "batch-a"
    folder.mkdir()
    (folder / "events.jsonl").write_text(payload, encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid run event"):
        load_events(tmp_path)


def test_duplicate_runs_rejected_in_renderer_and_loader(tmp_path):
    with pytest.raises(ValueError, match="duplicate run_id"):
        render([event(), event()])
    folder = tmp_path / "batch-a"
    folder.mkdir()
    (folder / "events.jsonl").write_text((event().to_json(dumps=json.dumps) + "\n") * 2, encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid run event"):
        load_events(tmp_path)


def test_cli_refuses_output_outside_runs(tmp_path, monkeypatch):
    # pytest's base temp may itself live in the real repository's .runs.
    # Give the CLI an isolated project root so this output is always outside it.
    monkeypatch.setattr("scripts.metrics_board.ROOT", tmp_path / "project")
    with pytest.raises(SystemExit):
        main(["--output", str(tmp_path / "board.html")])


def test_cli_rejection_when_pytest_temp_is_inside_runs(tmp_path, monkeypatch):
    # Reproduce the R35 command's layout: tmp_path was under ROOT/.runs.
    project = tmp_path / "repository"
    monkeypatch.setattr("scripts.metrics_board.ROOT", project)
    nested_temp = project / ".runs" / "pytest-temp" / "case-a"
    test_cli_refuses_output_outside_runs(nested_temp, monkeypatch)
    assert not (nested_temp / "board.html").exists()


def test_responsive_theme_and_self_contained_markup():
    html = render([event()])
    assert "prefers-color-scheme:dark" in html and 'id="theme"' in html
    assert "@media(max-width:640px)" in html and "minmax(0,1fr)" in html
    assert "overflow-wrap:anywhere" in html
    assert not any(t in {"script", "link", "img"} and ("src" in a or "href" in a)
                   for t, a in Markup(html).tags)


def test_node_sample_size_counts_repeated_calls_not_runs():
    repeated = event(nodes=(NodeEvent("retrieve", 10, 0, 0, None, True),
                            NodeEvent("retrieve", 30, 0, 0, None, True)))
    other = event("run-b2", nodes=(NodeEvent("retrieve", 80, 0, 0, None, True),
                                  NodeEvent("grade", 25, 0, 0, None, True)))
    html = render([repeated, other])
    assert "retrieve: 40.00 ms (호출당 평균) · n=3" in html
    assert "grade: 25.00 ms (호출당 평균) · n=1" in html
    assert "실행 표본 수: 2" in html


def test_explicit_themes_set_native_control_color_scheme():
    html = render([event()])
    assert ":root[data-theme=light]{color-scheme:light}" in html
    assert ":root[data-theme=dark]{color-scheme:dark;" in html


def test_real_schema_mapping_and_generator_injection_across_domains():
    research = json.loads(event().to_json(dumps=json.dumps))
    legal = event("run-b2", "legal")
    html = render(iter([research, legal]), injection_run_ids=iter(["run-a1", "run-b2"]))
    assert CounterPanels(Markup(html).tags)["guard"] == 2
    assert html.count("RelevanceGrade 탈락률: 미검증 (n=0)") == 2
    assert html.count("UNSUPPORTED_NUMBER: 1회") == 2
