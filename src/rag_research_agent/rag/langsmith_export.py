"""Synthetic-only local LangSmith exports; network use is an explicit owner action."""
from __future__ import annotations

MATURITY = "incubating"

import json
import math
from pathlib import Path
import re
from uuid import uuid4

from rag_research_agent.observe.golden_v2 import load, METRICS
from rag_research_agent.observe.tracing import ALLOWED_KEYS, allowlist, evaluation_client


class ExportError(ValueError):
    pass


def build_exports(set_path, results_path=None):
    raw = json.loads(Path(set_path).read_text(encoding="utf-8"))
    markers = " ".join(str(raw.get(key, "")) for key in ("name", "note")) if isinstance(raw, dict) else ""
    if not re.search(r"(?<![A-Za-z])SYNTHETIC(?![A-Za-z])", markers, re.I):
        raise ExportError("SYNTHETIC 표시가 있는 합성 골든셋만 내보낼 수 있습니다")
    dataset = load(set_path)
    examples = [{"inputs": {"question": item["question"]},
                 "outputs": {"answerable": item["answerable"], "relevant": [dict(e) for e in item["relevant"]]},
                 "metadata": {key: item[key] for key in ("type", "split", "id")}}
                for item in dataset["items"]]
    by_id = {item["id"]: item for item in dataset["items"]}
    experiments, seen = [], set()
    if results_path is not None:
        results = json.loads(Path(results_path).read_text(encoding="utf-8"))
        for row in results["rows"]:
            identifier = row["id"]
            if identifier not in by_id or identifier in seen:
                raise ExportError("평가 결과 ID가 합성 골든셋과 맞지 않거나 중복입니다")
            seen.add(identifier)
            metrics = {}
            for key in METRICS:
                if key not in row:
                    continue
                value = row[key]
                if value is not None and (not isinstance(value, (int, float)) or not math.isfinite(value)):
                    raise ExportError("평가 지표는 유한 숫자 또는 null이어야 합니다")
                metrics[key] = value
            experiments.append({"item_id": identifier, "metrics": metrics,
                                "metadata": {key: by_id[identifier][key] for key in ("type", "split")}})
    return {"examples": examples, "experiments": experiments}


def export_files(set_path, out=".runs/langsmith", results_path=None):
    exports = build_exports(set_path, results_path)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for filename, records in (("dataset.jsonl", exports["examples"]), ("experiment.jsonl", exports["experiments"])):
        (out / filename).write_text("".join(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n" for row in records), encoding="utf-8")
    return exports


def _safe(data):
    # allowlist itself redacts unknown values but retains their keys. Filter keys first.
    return allowlist({key: value for key, value in data.items() if key in ALLOWED_KEYS})


def upload(exports, *, api_key=None, client=None, client_factory=None):
    """Explicit upload boundary. Never pass question/quote text to the remote client."""
    if not api_key:
        raise ExportError("업로드하려면 LANGSMITH_API_KEY를 설정하세요. 기본 실행은 로컬 파일만 만듭니다")
    if client is None:
        client = (client_factory or evaluation_client)(api_key=api_key)
    dataset = client.create_dataset(dataset_name="rra-synthetic-evaluation-" + uuid4().hex[:8])
    records = []
    for row in exports["examples"]:
        metadata = row["metadata"]
        safe_meta = _safe({"item_id": metadata["id"], "type": metadata["type"], "split": metadata["split"]})
        records.append({"inputs": _safe({"item_id": metadata["id"]}),
                        "reference_outputs": _safe({"status": "FOUND" if row["outputs"]["answerable"] else "NOT_FOUND",
                                                     "document_ids": [r["source"] for r in row["outputs"]["relevant"]]}),
                        "metadata": safe_meta})
    if records:
        client.create_examples(dataset_id=dataset.id, examples=records)
    for row in exports["experiments"]:
        client.create_run(name="rra-local-evaluation", run_type="chain", project_name="rra-synthetic-evaluation",
                          inputs=_safe({"item_id": row["item_id"]}),
                          outputs=_safe({"hit": row["metrics"].get("hit"), "status": "EVALUATED"}),
                          extra={"metadata": _safe({"item_id": row["item_id"], **row["metadata"]})})
    if hasattr(client, "flush"):
        client.flush()
    return {"dataset_id": str(dataset.id), "examples": len(records), "runs": len(exports["experiments"])}
