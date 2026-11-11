"""Offline regression checks for the real board renderer and report formatter."""
import copy
import json
from pathlib import Path
import re
import shutil
import subprocess

from scripts.research_board import render


def record():
    rate = {"ok": 0, "n": 1, "rate": 0, "ci": [0, 0.79]}
    summary = {"quality": 0, "tokens_mean": 10, "loops_mean": 0,
               "verify_pass": 1, "n_cases": 1, "unsupported_numbers": 0,
               "no_con_noted": 1, "no_con_cases": 1,
               **{key: dict(rate) for key in ("metric_coverage", "causal_retention", "constraint_retention", "balance")}}
    return {"at": "2026-11-11", "split": "compare", "dataset": "synthetic",
            "configs": {"only": {"summary": summary, "cases": [{
                "case": "one", "report": "<b>report</b></script>",
                "tokens_in": 10, "tokens_out": 0, "gap_searches": 0,
                "rewrites": 0, "verify_codes": [], "log": [],
                "metric_hits": {"sales": False}, "causal": [False],
                "constraints": [True], "balance": [], "no_con_case": True,
                "gold": {"metrics": {"sales": "12"}, "causal": [["a", "b"]],
                         "constraints": ["condition"], "con": []}}]}}}


def embedded(html):
    return json.loads(re.search(r"const RUNS = (.*);", html).group(1).replace("<\\/", "</"))


def test_render_one_case_one_config_without_counter_evidence():
    runs = [record()]
    before = copy.deepcopy(runs)
    html = render(runs)
    assert embedded(html) == runs
    assert runs == before
    for element in ("compareCase", "compareLeft", "compareRight", "compareReports", "cards", "cases", "history"):
        assert f'id="{element}"' in html
    assert "보고서 비교" in html


def test_script_terminator_is_escaped_case_insensitively():
    run = record()
    run["note"] = '</ScRiPt><script>alert("x")</script>'
    html = render([run])
    assert html.count("</script>") == 1
    assert "</ScRiPt>" not in html
    assert embedded(html)[0]["note"] == run["note"]


def test_matching_dataset_enriches_legacy_records_only():
    dataset = json.loads((Path(__file__).resolve().parents[1] / "evals/research/cases.ko.json").read_text(encoding="utf-8"))
    run = record()
    row = run["configs"]["only"]["cases"][0]
    del row["gold"]
    row["case"] = dataset["cases"][0]["id"]
    assert "gold" not in embedded(render([run]))[0]["configs"]["only"]["cases"][0]
    run["dataset"] = dataset["version"]
    enriched = embedded(render([run]))[0]["configs"]["only"]["cases"][0]
    assert enriched["gold"] == dataset["cases"][0]["gold"]
    assert enriched["question"] == dataset["cases"][0]["question"]
    assert "gold" not in row


def test_real_javascript_report_panel(tmp_path):
    # Execute the actual pure formatter, without a substitute DOM or implementation.
    node = shutil.which("node")
    assert node, "Node.js is required to verify the board JavaScript"
    html = render([record()])
    full_script = tmp_path / "full-board.cjs"
    full_script.write_text(html.split("<script>", 1)[1].split("</script>", 1)[0], encoding="utf-8")
    subprocess.run([node, "--check", str(full_script)], capture_output=True, text=True, check=True)
    escape = re.search(r"const esc = .*", html).group(0)
    formatter = html[html.index("function reportPanel("):html.index("function comparison(")]
    row = record()["configs"]["only"]["cases"][0]
    script = tmp_path / "board.cjs"
    script.write_text(escape + "\n" + formatter + "\n" +
                      f"const row = {json.dumps(row)};\n" +
                      "const noCon = reportPanel(row, 'only'); row.gold.con = ['counter']; row.balance = [false];\n" +
                      "console.log(JSON.stringify([noCon, reportPanel(null, 'missing'), reportPanel(row, 'graph_full')]));", encoding="utf-8")
    result = subprocess.run([node, str(script)], capture_output=True, text=True, encoding="utf-8", check=True)
    panel, missing, counter = json.loads(result.stdout)
    assert 'class="bad">누락: 지표: sales 12' in panel
    assert 'class="bad">누락: 인과: a → b' in panel
    assert 'class="good">반영: 조건: condition' in panel
    assert "정답에 없음 (평가 제외)" in panel
    assert "&lt;b&gt;report&lt;/b&gt;&lt;/script&gt;" in panel
    assert "이 문항의 보고서 없음" in missing
    assert 'class="bad">누락: 반대 근거 (하나 이상): counter' in counter
