"""Offline integration coverage of the real runner, grid writer and board functions."""
from dataclasses import asdict
import json
import re
import shutil
import subprocess

import pytest

from scripts import research_grid
from scripts.research_board import render
from scripts.research_eval import ResearchConfig, aggregate


@pytest.fixture(scope="module")
def saved_grid(tmp_path_factory):
    out = tmp_path_factory.mktemp("grid")
    dataset = json.loads(research_grid.CASES.read_text(encoding="utf-8"))
    # Poison rows cannot be evaluated: they deliberately omit docs and gold.
    dataset["cases"] += [{"id": "excluded-confirm", "split": "confirm"},
                         {"id": "excluded-injection", "split": "compare", "type": "injection"}]
    cases_path = out / "cases.json"
    cases_path.write_text(json.dumps(dataset), encoding="utf-8")
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(research_grid, "OUT", out)
        patch.setattr(research_grid, "CASES", cases_path)
        research_grid.main()
    return out, json.loads((out / "grid.json").read_text(encoding="utf-8"))


def test_combinations_and_defaults_match_real_config():
    knobs = research_grid.load_knobs()
    combos = research_grid.combinations(knobs)
    assert len(combos) == 54
    assert len({json.dumps(c, sort_keys=True) for c in combos}) == 54
    defaults = asdict(ResearchConfig())
    assert {k: v["default"] for k, v in knobs.items()} == {k: defaults[k] for k in knobs}
    for k, spec in knobs.items():
        assert spec["name"] and spec["description"] and spec["tradeoff"]
        assert spec["default"] in spec["values"]
        assert {type(c[k]) for c in combos} == {type(defaults[k])}


def test_grid_file_real_runner_compare_only_and_scores(saved_grid):
    out, grid = saved_grid
    data = json.loads(research_grid.CASES.read_text(encoding="utf-8"))
    compare = {c["id"] for c in data["cases"] if c["split"] == "compare"}
    assert grid["schema_version"] == 1
    assert grid["split"] == "compare"
    assert grid["evaluation"] == "synthetic_rule_path_test"
    assert grid["tokens"] == "estimated_chars_per_2"
    assert grid["dataset"] == data["version"]
    assert len(grid["entries"]) == 54
    for entry, selection in zip(grid["entries"], research_grid.combinations(grid["knobs"])):
        assert entry["knobs"] == selection
        assert entry["config"] == asdict(ResearchConfig(**selection))
        assert {c["case"] for c in entry["cases"]} == compare
        assert entry["summary"] == aggregate(entry["cases"])
        assert entry["summary"]["tokens_mean"] > 0
        for row in entry["cases"]:
            assert row["path_len"] > 0 and row["log"]
            if selection["max_rewrites"] == 0:
                assert row["rewrites"] == 0
            if selection["max_gap_rounds"] == 0:
                assert row["gap_searches"] == 0
        for key in ("metric_coverage", "causal_retention", "constraint_retention", "balance"):
            rate = entry["summary"][key]
            assert rate["n"] >= rate["ok"] >= 0
            if rate["n"]:
                assert len(rate["ci"]) == 2
                lo, hi = rate["ci"]
                assert 0 <= lo <= hi <= 1
                assert lo - 1e-12 <= rate["rate"] <= hi + 1e-12
            else:
                assert rate["ci"] is None
    assert (out / "board.html").exists()
    assert not (out / "runs.jsonl").exists()  # grid never appends experiment history


def test_confirm_only_dataset_rejected():
    with pytest.raises(ValueError, match="compare"):
        research_grid.build_grid({"version": "empty", "cases": [{"split": "confirm"}]})


def test_board_without_grid_or_history_and_safe_payloads():
    html = render([], grid={})
    assert "const GRID = {};" in html and "const RUNS = [];" in html
    assert "격자 결과 없음" in html
    assert 'id="knobControls"' in html and 'id="knobConfig"' in html
    payload = {"entries": [], "note": "</ScRiPt>__RUNS____GRID__"}
    html = render([], grid=payload)
    embedded = re.search(r"const GRID = (.*);", html).group(1)
    assert json.loads(embedded.replace("<\\/", "</")) == payload
    assert html.count("</script>") == 1 and "</ScRiPt>" not in html


def test_board_autoloads_grid(saved_grid):
    out, grid = saved_grid
    # Redirect just the renderer's location to an isolated project tree.
    root = out / "project"
    path = root / ".runs" / "research_eval" / "grid.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(grid), encoding="utf-8")
    import scripts.research_board as board
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(board, "__file__", str(root / "scripts" / "research_board.py"))
        html = board.render([])
    embedded = re.search(r"const GRID = (.*);", html).group(1)
    assert json.loads(embedded.replace("<\\/", "</")) == grid


def test_actual_javascript_selection_and_differences(saved_grid, tmp_path):
    _, grid = saved_grid
    node = shutil.which("node")
    assert node, "Node.js is required for board JavaScript checks"
    html = render([], grid=grid)
    script = html.split("<script>", 1)[1].split("</script>", 1)[0]
    full = tmp_path / "board.cjs"
    full.write_text(script, encoding="utf-8")
    subprocess.run([node, "--check", str(full)], capture_output=True, check=True)
    helpers = "\n".join(re.search(rf"const {name} = .*", html).group(0) for name in ("pct", "ci"))
    functions = html[html.index("function gridEntry("):html.index("function knobs(")]
    program = helpers + "\n" + functions + "\nconst grid = " + json.dumps(grid) + ";\n" + """
const assert=require('node:assert/strict');
for(const entry of grid.entries){
  assert.deepEqual(gridEntry(grid,entry.knobs),entry);
  const view=gridResult(grid,entry.knobs);
  assert.deepEqual(view.config,entry.config);
  const delta=(entry.summary.tokens_mean-gridEntry(grid,grid.defaults).summary.tokens_mean);
  assert.ok(view.html.includes((delta>=0?'+':'')+delta.toFixed(2)));
  assert.ok(view.html.includes(entry.summary.n_cases+'개'));
}
assert.ok(gridResult(grid,grid.defaults).html.includes('+0.00p'));
assert.ok(gridResult(grid,{k:99}).html.includes('미검증'));
assert.equal(gridEntry(grid,{...grid.defaults,use_checklist:'true'}),undefined);
console.log('54 selections and default/missing/type checks passed');
"""
    full.write_text(program, encoding="utf-8")
    subprocess.run([node, str(full)], capture_output=True, check=True)
