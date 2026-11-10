"""N7: settings layering, validation and the hand-off to existing constructors."""
import dataclasses
import json

import pytest

from rag_research_agent.core.contracts import RetrievalMode
from rag_research_agent.core.settings import RuntimeSettings, SettingsError, env_layer, settings_from_layers
from rag_research_agent.rag.execution import BoundedWorker
from rag_research_agent.rag.settings_loader import load_settings, pipeline_kwargs, relevance_rule, worker_kwargs

REQUIRED = {"tau_abs": 0.42, "tau_gap": 0.05, "rule_version": "rule-v1", "index_version": "idx-v1",
            "retrieval_mode": "vector"}


def write(tmp_path, data):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_defaults_match_the_code_that_uses_them():
    s = settings_from_layers(("test", REQUIRED))
    assert (s.retrieval_timeout_s, s.generation_timeout_s, s.k) == (30.0, 30.0, 3)       # GuidancePipeline
    assert (s.worker_slots, s.queue_limit, s.admission_timeout_s) == (1, 4, 1.0)        # BoundedWorker


def test_precedence_defaults_then_file_then_environment(tmp_path):
    path = write(tmp_path, {**REQUIRED, "k": 5, "worker_slots": 2})
    s = load_settings(path, environ={"RRA_K": "7", "OTHER_K": "99"})
    assert s.k == 7                 # environment wins
    assert s.worker_slots == 2      # file beats default
    assert s.queue_limit == 4       # default stays


def test_environment_values_are_converted():
    s = load_settings(environ={"RRA_TAU_ABS": " 0.5 ", "RRA_TAU_GAP": "0", "RRA_RULE_VERSION": "r",
                               "RRA_INDEX_VERSION": "i", "RRA_RETRIEVAL_MODE": "lex",
                               "RRA_WORKER_SLOTS": "3", "RRA_RETRIEVAL_TIMEOUT_S": "12.5"})
    assert (s.tau_abs, s.worker_slots, s.retrieval_timeout_s, s.retrieval_mode) == (0.5, 3, 12.5, "lex")


def test_unknown_keys_are_rejected_in_file_and_environment(tmp_path):
    with pytest.raises(SettingsError, match="unknown setting"):
        load_settings(write(tmp_path, {**REQUIRED, "api_key": "x"}), environ={})
    with pytest.raises(SettingsError, match="unknown setting"):
        env_layer({"RRA_TAU": "0.3"})


def test_missing_tau_mentions_calibration():
    with pytest.raises(SettingsError) as err:
        settings_from_layers(("test", {k: v for k, v in REQUIRED.items() if k != "tau_abs"}))
    assert "tau_abs" in str(err.value) and "calibration" in str(err.value)


@pytest.mark.parametrize("override,needle", [
    ({"retrieval_timeout_s": 0}, "retrieval_timeout_s"),
    ({"generation_timeout_s": float("inf")}, "generation_timeout_s"),
    ({"worker_slots": 0}, "worker_slots"),
    ({"queue_limit": -1}, "queue_limit"),
    ({"k": 0}, "k must be"),
    ({"tau_abs": 1.2}, "tau_abs"),
    ({"tau_gap": float("nan")}, "tau_gap"),
    ({"rule_version": "  "}, "rule_version"),
    ({"retrieval_mode": "hybrid"}, "retrieval_mode"),
])
def test_range_errors_name_the_field(override, needle):
    with pytest.raises(SettingsError, match=needle):
        settings_from_layers(("test", {**REQUIRED, **override}))


@pytest.mark.parametrize("override", [{"k": "three"}, {"k": 2.5}, {"worker_slots": True}, {"rule_version": 3}])
def test_wrong_types_are_rejected(override):
    with pytest.raises(SettingsError):
        settings_from_layers(("test", {**REQUIRED, **override}))


def test_file_errors_are_settings_errors(tmp_path):
    with pytest.raises(SettingsError, match="not found"):
        load_settings(tmp_path / "missing.json", environ={})
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(SettingsError, match="not valid JSON"):
        load_settings(bad, environ={})
    with pytest.raises(SettingsError, match="JSON object"):
        load_settings(write(tmp_path, [1, 2]), environ={})


def test_settings_are_frozen():
    s = settings_from_layers(("test", REQUIRED))
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.k = 9


def test_hand_off_builds_real_rule_worker_and_pipeline_arguments():
    s = settings_from_layers(("test", {**REQUIRED, "worker_slots": 2, "queue_limit": 1}))
    rule = relevance_rule(s)
    assert (rule.mode, rule.tau_abs, rule.tau_gap, rule.version) == (RetrievalMode.VECTOR, 0.42, 0.05, "rule-v1")
    worker = BoundedWorker(**worker_kwargs(s))          # the real constructor accepts these names
    assert worker.max_waiters == 1
    assert pipeline_kwargs(s) == {"index_version": "idx-v1", "retrieval_timeout": 30.0,
                                  "generation_timeout": 30.0, "k": 3}


def test_korean_text_in_settings_file_round_trips(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(json.dumps({**REQUIRED, "rule_version": "보정-v1"}, ensure_ascii=False), encoding="utf-8")
    assert load_settings(path, environ={}).rule_version == "보정-v1"
