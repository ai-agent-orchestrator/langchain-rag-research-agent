"""Runtime settings (N7): one frozen, validated object for timeouts, worker limits and the evidence gate.

Pure core module: it validates and merges plain mappings. Reading files and os.environ lives in
rag/settings_loader.py, because core may not import os/json.

Defaults are copied from the code that uses them today (see docs/N7_REPORT_2026-11-10.md):
GuidancePipeline(retrieval_timeout=30.0, generation_timeout=30.0, k=3) and
BoundedWorker(concurrent=1, waiters=4, admission_timeout=1.0).

tau_abs / tau_gap / rule_version / index_version / retrieval_mode have NO default on purpose:
tau values must be calibrated for one embedding model, retrieval mode and index version
(compare split only), and stored with that rule version. There is no shared default like 0.8.
"""
from __future__ import annotations

MATURITY = "incubating"

from dataclasses import MISSING, dataclass, fields
from typing import Any, Mapping

TAU_NOTE = ("tau values must come from calibration for this embedding model, retrieval mode and "
            "index version (compare split only); there is no shared default")
MODES = ("lex", "vector")
_REQUIRED = object()


class SettingsError(ValueError):
    pass


def _finite(value: float) -> bool:
    return value == value and value not in (float("inf"), float("-inf"))


@dataclass(frozen=True)
class RuntimeSettings:
    tau_abs: float
    tau_gap: float
    rule_version: str
    index_version: str
    retrieval_mode: str
    retrieval_timeout_s: float = 30.0
    generation_timeout_s: float = 30.0
    k: int = 3
    worker_slots: int = 1
    queue_limit: int = 4
    admission_timeout_s: float = 1.0

    def __post_init__(self):
        problems = []
        for name in ("retrieval_timeout_s", "generation_timeout_s", "admission_timeout_s"):
            value = getattr(self, name)
            if not _finite(value) or value <= 0:
                problems.append(f"{name} must be a positive finite number of seconds (got {value!r})")
        if self.k < 1:
            problems.append(f"k must be >= 1 (got {self.k!r})")
        if self.worker_slots < 1:
            problems.append(f"worker_slots must be >= 1 (got {self.worker_slots!r})")
        if self.queue_limit < 0:
            problems.append(f"queue_limit must be >= 0 (got {self.queue_limit!r})")
        if not _finite(self.tau_abs) or not 0.0 <= self.tau_abs <= 1.0:
            problems.append(f"tau_abs must be within 0..1 (got {self.tau_abs!r}); {TAU_NOTE}")
        if not _finite(self.tau_gap) or not 0.0 <= self.tau_gap <= 1.0:
            problems.append(f"tau_gap must be within 0..1 (got {self.tau_gap!r}); {TAU_NOTE}")
        for name in ("rule_version", "index_version"):
            if not getattr(self, name).strip():
                problems.append(f"{name} must not be empty")
        if self.retrieval_mode not in MODES:
            problems.append(f"retrieval_mode must be one of {MODES} (got {self.retrieval_mode!r})")
        if problems:
            raise SettingsError("; ".join(problems))


_TYPES = {"float": float, "int": int, "str": str}   # annotations are strings under `from __future__`
FIELD_TYPES: dict[str, type] = {f.name: _TYPES[f.type] for f in fields(RuntimeSettings)}
DEFAULTS: dict[str, Any] = {f.name: (_REQUIRED if f.default is MISSING else f.default)
                            for f in fields(RuntimeSettings)}


def _coerce(name: str, value: Any, source: str) -> Any:
    wanted = FIELD_TYPES[name]
    if isinstance(value, bool):                       # bool is an int subclass; never accept it as a number
        raise SettingsError(f"{source}: {name} must be {wanted.__name__}, not a boolean")
    try:
        if wanted is str:
            if not isinstance(value, str):
                raise TypeError
            return value.strip()
        if wanted is int:
            if isinstance(value, float) and not value.is_integer():
                raise TypeError
            return int(value.strip()) if isinstance(value, str) else int(value)
        return float(value.strip()) if isinstance(value, str) else float(value)
    except (TypeError, ValueError):
        raise SettingsError(f"{source}: {name} must be {wanted.__name__} (got {value!r})") from None


def check_keys(layer: Mapping[str, Any], source: str) -> None:
    unknown = sorted(set(layer) - set(FIELD_TYPES))
    if unknown:
        raise SettingsError(f"{source}: unknown setting(s) {unknown}; allowed {sorted(FIELD_TYPES)}")


def settings_from_layers(*layers: tuple[str, Mapping[str, Any]]) -> RuntimeSettings:
    """Merge (source_name, mapping) layers left to right; later layers win. Defaults come first."""
    merged: dict[str, Any] = {name: value for name, value in DEFAULTS.items() if value is not _REQUIRED}
    for source, layer in layers:
        check_keys(layer, source)
        for name, value in layer.items():
            merged[name] = _coerce(name, value, source)
    missing = sorted(name for name, value in DEFAULTS.items() if value is _REQUIRED and name not in merged)
    if missing:
        raise SettingsError(f"missing required setting(s) {missing}" +
                            ("; " + TAU_NOTE if {"tau_abs", "tau_gap"} & set(missing) else ""))
    return RuntimeSettings(**merged)


def env_layer(environ: Mapping[str, str], prefix: str = "RRA_") -> dict[str, str]:
    """Pick PREFIX_<FIELD> variables (e.g. RRA_TAU_ABS). Unknown PREFIX_ variables are an error."""
    layer = {}
    for key, value in environ.items():
        if key.startswith(prefix):
            layer[key[len(prefix):].lower()] = value
    check_keys(layer, "environment")
    return layer
