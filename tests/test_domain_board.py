"""Synthetic records exercise the real R21 evaluator and board, entirely offline."""
from html.parser import HTMLParser
import json

import pytest

from scripts import domain_board as board
from scripts import domain_eval as evaluator


class Document(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.section = None
        self.sections = {}
        self.tags = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        if tag == "section":
            self.section = dict(attrs)["id"]
            self.sections[self.section] = ""

    def handle_endtag(self, tag):
        if tag == "section":
            self.section = None

    def handle_data(self, data):
        if self.section:
            self.sections[self.section] += data


@pytest.fixture
def histories(tmp_path, monkeypatch):
    packs = tmp_path / "packs"
    out = tmp_path / ".runs/domain_eval"
    monkeypatch.setattr(evaluator, "OUT", out)
    definitions = {}
    for name, quality, safety in [("alpha", "evidence_custom", "unsafe_custom"),
                                  ("beta", "coverage_other", "leak_other")]:
        metrics = [
            {"name": quality, "kind": "contains", "field": "answer",
             "safety": False, "values": ["supported"]},
            {"name": safety, "kind": "forbidden", "field": "answer",
             "safety": True, "values": ["unsafe"]},
        ]
        cases = [{"id": "doc-a1", "output": {"answer": "supported"}},
                 {"id": "doc-b2", "type": "injection", "output": {"answer": "unsafe unsafe"}}]
        folder = packs / name
        folder.mkdir(parents=True)
        (folder / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
        (folder / "cases.json").write_text(json.dumps(cases), encoding="utf-8")
        evaluator.run(name, packs)
        definitions[name] = metrics
    return out, packs, definitions


def test_two_domains_use_pack_columns_and_safety_first(histories):
    out, packs, _ = histories
    html = board.render(board.load_domains(out, packs))
    doc = Document(html)
    assert list(doc.sections) == ["safety", "quality", "tokens", "history"]
    for name in ("unsafe_custom", "leak_other"):
        assert name in doc.sections["safety"]
        assert name not in doc.sections["quality"]
    for name in ("evidence_custom", "coverage_other"):
        assert name in doc.sections["quality"]
        assert name not in doc.sections["safety"]
    assert "위반 1/2" in doc.sections["safety"]
    assert "Wilson 상한" in doc.sections["safety"]
    assert "1/1" in doc.sections["quality"]  # injection excluded by real evaluator
    assert "Wilson 95%" in doc.sections["quality"]
    assert "미검증" in doc.sections["tokens"]
    assert "provided_outputs" in doc.sections["history"]


def test_data_is_escaped_in_every_context(histories):
    out, packs, _ = histories
    data = board.load_domains(out, packs)
    attack = '</script><img src=x onerror="alert(1)">&\''
    domain = data.pop("alpha")
    domain["metrics"][0]["name"] = attack
    domain["metrics"][1]["name"] = attack + "safety"
    domain["runs"][0].update(at=attack, split=attack, evaluation=attack, tokens_mean=attack)
    html = board.render({attack: domain})
    doc = Document(html)
    assert "img" not in doc.tags
    assert doc.tags.count("script") == 1
    assert attack in doc.sections["safety"]
    assert attack in doc.sections["quality"]
    assert attack in doc.sections["tokens"]
    assert attack in doc.sections["history"]
    assert "&lt;/script&gt;" in html and "&quot;" in html and "&#x27;" in html


def test_zero_violations_have_nonzero_upper_and_empty_is_unverified():
    metrics = [{"name": "check", "kind": "forbidden", "field": "answer",
                "safety": True, "values": ["unsafe"]}]
    run = evaluator.evaluate([{"id": "doc-a1", "output": {"answer": "safe"}}], metrics)
    html = board.render({"alpha": {"metrics": metrics, "runs": [run]}})
    safety = Document(html).sections["safety"]
    assert "위반 0/1" in safety and "Wilson 상한 79.3%" in safety
    assert "정의된 지표 없음" in Document(html).sections["quality"]
    assert board.statistic({"n": 0}, True) == "미검증 (n=0)"
    assert "실행 기록 없음" in board.render({})


def test_history_provenance_and_pack_order_are_preserved(histories):
    out, packs, _ = histories
    data = board.load_domains(out, packs, ["alpha"])
    domain = data["alpha"]
    second = dict(domain["runs"][0], split="confirm", evaluation="synthetic_rule_path_test")
    domain["runs"].append(second)
    domain["metrics"].insert(0, {"name": "new_metric", "kind": "contains", "field": "answer",
                                 "safety": False, "values": ["supported"]})
    html = board.render(data)
    quality = Document(html).sections["quality"]
    assert quality.index("new_metric") < quality.index("evidence_custom")
    assert "미검증 (표본 수 없음)" in quality
    assert "compare" in quality and "confirm" in quality
    assert "provided_outputs" in quality and "synthetic_rule_path_test" in quality
    assert "beta" not in html
    assert len(board.run_groups(domain["runs"])) == 2


def test_cli_writes_only_under_runs_and_keeps_histories(histories, tmp_path, monkeypatch):
    out, packs, _ = histories
    monkeypatch.setattr(board, "ROOT", tmp_path)
    history = out / "alpha/runs.jsonl"
    before = history.read_bytes()
    target = out / "board.html"
    args = ["--runs-root", str(out), "--packs", str(packs), "--domain", "alpha"]
    board.main([*args, "--output", str(target)])
    assert "unsafe_custom" in target.read_text(encoding="utf-8")
    assert history.read_bytes() == before
    for path in [tmp_path / "outside.html", out / "runs.jsonl"]:
        with pytest.raises(SystemExit) as exc:
            board.main([*args, "--output", str(path)])
        assert exc.value.code == 2
        assert not path.exists()


@pytest.mark.parametrize("domain", ["../escape", "a/b", "a\\b"])
def test_invalid_domain_rejected_before_history_read(domain, tmp_path):
    with pytest.raises(ValueError, match="simple folder name"):
        board.load_domains(tmp_path, tmp_path, [domain])


def test_schema_mismatch_and_malformed_json_fail(histories):
    out, packs, _ = histories
    history = out / "alpha/runs.jsonl"
    for value in [json.dumps({"domain": "beta", "schema_version": 1}), "{"]:
        history.write_text(value, encoding="utf-8")
        with pytest.raises(ValueError):
            board.load_domains(out, packs, ["alpha"])


def test_mobile_layout_and_theme_controls(histories):
    out, packs, _ = histories
    html = board.render(board.load_domains(out, packs))
    assert "prefers-color-scheme:dark" in html
    assert "data-theme=light" in html and "data-theme=dark" in html
    assert 'id="theme"' in html
    assert "@media(max-width:650px)" in html
    assert "display:block;width:100%" in html
    assert "table-layout:fixed" in html and "overflow-wrap:anywhere" in html
