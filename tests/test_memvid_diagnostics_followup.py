"""New diagnostic tests only; SDK calls are injected and no production retry is exercised."""
import importlib.util
import json
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location("diagnose_followup", Path(__file__).parents[1] / "scripts/diagnose_memvid_writes.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_delay_is_between_create_and_put_and_no_inspection_on_success(tmp_path, monkeypatch):
    events = []
    class Writer:
        def put_many(self, requests, **kwargs):
            assert len(requests) == 8
            events.append("put")
        def seal(self):
            events.append("seal")
        def close(self):
            events.append("close")
    class SDK:
        def use(self, *args, **kwargs):
            events.append("open")
            return Writer()
    monkeypatch.setattr(module.time, "sleep", lambda seconds: events.append(seconds))
    inspections = []
    result = module.trial(SDK(), tmp_path / "x.mv2", count=8, wait_ms=100, inspector=lambda path: inspections.append(path))
    assert events == ["open", .1, "put", "seal", "close"]
    assert result["success"] and not inspections
    assert all(t["elapsed_ms"] >= 0 for t in result["timings"])


def test_close_only_failure_counts_and_is_inspected(tmp_path):
    class Writer:
        def put_many(self, *args, **kwargs): pass
        def seal(self): pass
        def close(self): raise OSError(5, "close denied")
    class SDK:
        def use(self, *args, **kwargs): return Writer()
    paths = []
    def inspect(path):
        paths.append(path)
        return {"status": "ok", "processes": [], "complete_handle_inventory": False}
    result = module.trial(SDK(), tmp_path / "x.mv2", inspector=inspect)
    assert not result["success"] and result["first_error"]["stage"] == "close"
    assert len(paths) == 1 and "occupancy_after_close" in result


def test_wilson_denominator_excludes_unestablished_condition_and_fixed_schema(tmp_path):
    base = {"condition": "workspace-w0-closed", "condition_established": True, "success": True,
            "elapsed_ms": 10., "operation_elapsed_ms": 8., "first_error": None}
    rows = [dict(base) for _ in range(30)]
    rows.append({**base, "condition_established": False, "success": False})
    result = module.write_reports(tmp_path, {"count": 24}, rows, [], {"finished": True})
    success = result["summary"][0]["success"]
    assert success["count"] == success["n"] == 30
    assert success["wilson95"][0] == pytest.approx(.8864866)
    assert result["summary"][0]["condition_not_established"] == 1
    assert result["schema"] == "rra-memvid-write-diagnostics/2"
    assert json.loads((tmp_path / "diagnosis.json").read_text())["protocol_sha256"] == result["protocol_sha256"]
