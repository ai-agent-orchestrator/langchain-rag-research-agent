"""Exercise the real local recorder, strict schema and persisted representation."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from rag_research_agent.core.contracts import RetrievalStatus
from rag_research_agent.core.types import Status
from rag_research_agent.observe.metrics import LocalMetrics, summarize


def event(**changes):
    result = dict(stage="retrieve", latency_ms=10, status="OK", input_length=20,
                  output_length=40, slots_occupied=1)
    result.update(changes)
    return result


@pytest.fixture
def runs_dir():
    root = Path(".runs")
    root.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix="n8-test-", dir=root) as directory:
        yield Path(directory)


@pytest.mark.parametrize("key", ["query", "text", "document", "name", "exception", "metadata"])
def test_unknown_keys_rejected_before_memory_or_disk_write(runs_dir, key):
    path = runs_dir / "metrics.jsonl"
    recorder = LocalMetrics(path)
    with pytest.raises(ValueError) as caught:
        recorder.record(**event(**{key: "private source content"}))
    assert "private source content" not in str(caught.value)
    assert recorder.events == ()
    assert not path.exists()


@pytest.mark.parametrize("changes", [
    {"stage": "private source content"}, {"status": "private source content"},
    {"stage": []}, {"status": {}}, {"latency_ms": "private source content"},
    {"latency_ms": True}, {"latency_ms": -1}, {"latency_ms": float("nan")},
    {"latency_ms": float("inf")}, {"latency_ms": 10 ** 400},
    {"input_length": "private source content"}, {"output_length": -1},
    {"slots_occupied": 1.5}, {"input_length": True},
])
def test_values_cannot_carry_free_text_or_invalid_numbers(changes):
    recorder = LocalMetrics()
    with pytest.raises(ValueError) as caught:
        recorder.record(**event(**changes))
    assert "private source content" not in str(caught.value)
    assert recorder.events == ()


def test_required_keys_are_enforced():
    row = event()
    del row["input_length"]
    with pytest.raises(ValueError):
        LocalMetrics().record(**row)


def test_summary_matches_hand_calculated_interpolation_and_wilson():
    recorder = LocalMetrics()
    for latency, status in [(10, "OK"), (20, "EMPTY"), (30, "OK"), (40, "INFERENCE_TIMEOUT")]:
        recorder.record(**event(latency_ms=latency, status=status))
    result = recorder.summary()
    assert result["count"] == 4
    assert result["stages"]["retrieve"] == pytest.approx({"count": 4, "p50_ms": 25, "p95_ms": 38.5})
    assert result["statuses"] == {"EMPTY": 1, "INFERENCE_TIMEOUT": 1, "OK": 2}
    assert result["timeout"]["count"] == 1
    assert result["timeout"]["total"] == 4
    assert result["timeout"]["rate"] == .25
    assert result["timeout"]["wilson95"] == pytest.approx([.0455872608, .6993581574])


def test_stage_groups_singletons_and_existing_status_enums():
    recorder = LocalMetrics()
    for stage, status in [("retrieve", RetrievalStatus.EMPTY), ("grade", "BELOW_THRESHOLD"),
                          ("generate", "ANSWERED"), ("answer", Status.BLOCKED)]:
        recorder.record(**event(stage=stage, status=status, latency_ms=0,
                                input_length=0, output_length=0, slots_occupied=0))
    assert all(stats == {"count": 1, "p50_ms": 0, "p95_ms": 0}
               for stats in recorder.summary()["stages"].values())
    assert recorder.summary()["timeout"]["wilson95"][1] > 0


def test_empty_summary():
    assert LocalMetrics().summary() == {
        "count": 0,
        "stages": {stage: {"count": 0, "p50_ms": None, "p95_ms": None}
                   for stage in ("retrieve", "grade", "generate", "answer")},
        "statuses": {},
        "timeout": {"count": 0, "total": 0, "rate": None, "wilson95": None},
    }


def test_jsonl_round_trip_append_and_copy_isolation(runs_dir):
    path = runs_dir / "nested" / "metrics.jsonl"
    recorder = LocalMetrics(path)
    returned = recorder.record(**event())
    returned["status"] = "EMPTY"
    recorder.events[0]["status"] = "BLOCKED"
    recorder.record(**event(stage="generate", status="INFERENCE_TIMEOUT", latency_ms=50))
    loaded = LocalMetrics.from_jsonl(path)
    assert loaded.events == recorder.events
    assert loaded.summary() == recorder.summary()
    assert loaded.events[0]["status"] == "OK"
    assert [json.loads(line) for line in path.read_text().splitlines()] == list(recorder.events)
    # A new sink appends without silently loading old events.
    second = LocalMetrics(path)
    second.record(**event(status="UNAVAILABLE"))
    assert len(second.events) == 1
    assert len(LocalMetrics.from_jsonl(path).events) == 3
    assert len(path.read_text().splitlines()) == 3


@pytest.mark.parametrize("path", ["metrics.jsonl", ".runs", ".runs/../outside.jsonl"])
def test_files_must_stay_under_runs(path):
    with pytest.raises(ValueError):
        LocalMetrics(path)
    with pytest.raises(ValueError):
        LocalMetrics.from_jsonl(path)


@pytest.mark.parametrize("payload", [
    {**event(), "query": "private source content"}, event(status="private source content"),
    event(output_length="private source content"), [],
])
def test_jsonl_loading_and_standalone_summary_revalidate(runs_dir, payload):
    path = runs_dir / "invalid.jsonl"
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        LocalMetrics.from_jsonl(path)
    with pytest.raises(ValueError):
        summarize([payload])


def test_invalid_jsonl_is_rejected_without_source_in_error(runs_dir):
    path = runs_dir / "invalid.jsonl"
    path.write_text("private source content\n", encoding="utf-8")
    with pytest.raises(ValueError, match="^invalid metric JSONL$"):
        LocalMetrics.from_jsonl(path)
