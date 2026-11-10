"""Diagnostic harness preserves first failure without retrying a poisoned writer."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("diagnose", Path(__file__).parents[1] / "scripts/diagnose_memvid_writes.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_first_error_preserved_and_writer_closed(tmp_path):
    class Writer:
        calls = 0
        closed = False

        def put_many(self, *args, **kwargs):
            self.calls += 1
            raise OSError(5, "synthetic IO failure")

        def close(self):
            self.closed = True
            raise RuntimeError("secondary close failure")

    writer = Writer()

    class SDK:
        def use(self, *args, **kwargs):
            return writer

    result = module.trial(SDK(), tmp_path / "new.mv2")
    assert result["first_error"]["stage"] == "put:0"
    assert result["first_error"]["errno"] == 5
    assert "secondary" in result["close_error"]
    assert writer.calls == 1 and writer.closed
