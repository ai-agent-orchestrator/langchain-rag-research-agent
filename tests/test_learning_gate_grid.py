import copy
import pytest
from rag_research_agent.observe.gate_grid import wilson, sweep
from scripts.sweep_retrieval_gates import write_report


def rows():
    return [{"id": "yes", "split": "compare", "expected": ["a"], "vector": {"top1": .8, "gap": .2}},
            {"id": "no", "split": "compare", "expected": [], "vector": {"top1": .4, "gap": .1}},
            {"id": "held", "split": "confirm", "expected": [], "vector": {"top1": .9, "gap": .3}}]


def test_zero_of_nine_is_not_guarantee_and_empty_is_unknown():
    assert wilson(0, 9)["wilson95"][1] == pytest.approx(.299145, abs=1e-5)
    assert wilson(0, 0)["rate"] is None
    assert wilson(9, 9)["wilson95"][0] < 1


def test_confirm_cannot_change_selection_and_injection_excluded(tmp_path):
    first = sweep(rows(), [.3, .6, .9], [0, .15])
    changed = copy.deepcopy(rows())
    changed[-1]["vector"]["top1"] = 0
    second = sweep(changed, [.3, .6, .9], [0, .15])
    assert first["selected"] == second["selected"]
    assert first["selected"]["tau_abs"] == .6
    assert first["confirm"]["false_accept"]["errors"] == 1
    assert second["confirm"]["false_accept"]["errors"] == 0
    result = write_report({"model": "fake", "evaluation_rows": rows()}, [.3, .6], [0], tmp_path)
    assert result["real_model"] is None
    assert "Wilson95" in (tmp_path / "gates.html").read_text(encoding="utf-8")
    with pytest.raises(ValueError):
        sweep(rows() + [rows()[0]], [.5], [0])
