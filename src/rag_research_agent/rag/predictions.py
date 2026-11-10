"""Append-only prediction journal. Records human forecasts; never generates predictions."""
from __future__ import annotations

MATURITY = "incubating"

from collections import Counter, defaultdict
from datetime import datetime, time, timezone
import json
import math
from pathlib import Path
from uuid import uuid4

OUTCOMES = {"hit", "miss", "partial", "void"}


def _instant(value, end_of_day=False):
    if isinstance(value, datetime):
        result = value
    else:
        result = datetime.fromisoformat(str(value))
        if len(str(value)) == 10:
            result = datetime.combine(result.date(), time.max if end_of_day else time.min, timezone.utc)
    if result.tzinfo is None:
        raise ValueError("날짜·시각에는 시간대가 필요합니다 (예: +09:00)")
    return result.astimezone(timezone.utc)


class PredictionLog:
    def __init__(self, path=".runs/predictions.jsonl", clock=None):
        self.path = Path(path)
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _append(self, event):
        root = Path(__file__).resolve().parents[3]
        if any(self.path.resolve().is_relative_to(root / folder) for folder in ("data", "profiles")):
            raise ValueError("기록은 data/profiles 밖의 .runs에 저장해 주세요")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n")

    def list(self, open_only=False):
        latest = {}
        if not self.path.exists():
            return []
        for n, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
                if event["op"] == "add":
                    if event["id"] in latest:
                        raise ValueError("duplicate add ID")
                    latest[event["id"]] = {k: v for k, v in event.items() if k != "op"}
                elif event["op"] == "resolve" and event["id"] in latest and event["outcome"] in OUTCOMES:
                    latest[event["id"]].update({k: v for k, v in event.items() if k not in ("op", "id")})
                else:
                    raise ValueError("invalid event")
            except (ValueError, KeyError, TypeError) as exc:
                raise ValueError(f"기록 {n}행을 읽을 수 없습니다: {exc}") from exc
        return [row for row in latest.values() if not open_only or not row.get("outcome")]

    def add(self, statement, profile, evidence_ids, brief_path, due, confidence=None, tags=()):
        if not isinstance(statement, str) or not statement.strip() or not isinstance(profile, str) or not profile.strip():
            raise ValueError("예측 문장과 프로필을 입력해 주세요")
        if isinstance(evidence_ids, str) or any(not isinstance(x, str) for x in evidence_ids):
            raise ValueError("evidence_ids는 문자열 목록이어야 합니다")
        if isinstance(tags, str) or any(not isinstance(x, str) for x in tags):
            raise ValueError("tags는 문자열 목록이어야 합니다")
        if confidence is not None and (isinstance(confidence, bool) or not isinstance(confidence, (int, float))
                                       or not math.isfinite(confidence) or not 0 <= confidence <= 1):
            raise ValueError("confidence는 0..1이어야 합니다")
        self.list()  # Do not append onto a corrupt journal.
        identifier = uuid4().hex
        self._append({"op": "add", "id": identifier, "statement": statement, "profile": profile,
                      "evidence_ids": list(evidence_ids), "brief_path": str(brief_path),
                      "due": _instant(due, end_of_day=True).isoformat(), "confidence": confidence,
                      "tags": sorted(set(tags)), "created_at": _instant(self.clock()).isoformat()})
        return identifier

    def resolve(self, id, outcome, note="", resolved_at=None):
        if outcome not in OUTCOMES:
            raise ValueError("outcome은 hit|miss|partial|void 중 하나여야 합니다")
        if id not in {row["id"] for row in self.list()}:
            raise ValueError("없는 예측 ID입니다")
        if not isinstance(note, str):
            raise ValueError("note는 문자열이어야 합니다")
        self._append({"op": "resolve", "id": id, "outcome": outcome, "note": note,
                      "resolved_at": _instant(resolved_at or self.clock()).isoformat()})

    def summary(self):
        now = _instant(self.clock())
        rows = self.list()
        def metrics(items):
            counts = Counter(item.get("outcome") for item in items)
            denominator = sum(counts[k] for k in ("hit", "miss", "partial"))
            return {"total": len(items), "open": counts[None],
                    "hit": counts["hit"], "miss": counts["miss"], "partial": counts["partial"], "void": counts["void"],
                    "hit_rate": (counts["hit"] + 0.5 * counts["partial"]) / denominator if denominator else None,
                    "overdue": sum(not item.get("outcome") and _instant(item["due"]) < now for item in items)}
        profiles, tags = defaultdict(list), defaultdict(list)
        for row in rows:
            profiles[row["profile"]].append(row)
            for tag in row["tags"]:
                tags[tag].append(row)
        return {**metrics(rows), "profiles": {k: metrics(v) for k, v in sorted(profiles.items())},
                "tags": {k: metrics(v) for k, v in sorted(tags.items())}}
