"""Read-only, standard-library diagnostics for replaceable rules and profiles."""
from __future__ import annotations

MATURITY = "incubating"

from collections import defaultdict
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]
WEIGHTS = ("golden_phrase", "concreteness", "causal_reversal", "ontology_priority", "rarity", "cliche_penalty")


@dataclass(frozen=True)
class Issue:
    file: str
    severity: str
    location: str
    message: str


def check_file(path):
    path = Path(path)
    issues = []
    def emit(level, loc, message):
        issues.append(Issue(str(path), level, loc, message))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        emit("error", "$", f"JSON 읽기 실패: {exc}")
        return issues
    if not isinstance(data, dict):
        emit("error", "$", "JSON 객체가 필요합니다")
        return issues
    cues = defaultdict(list)
    ids = set()

    def number(value, loc, positive=False, bounded=False):
        if (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
                or value < 0 or (positive and value == 0) or (bounded and value > 1)):
            emit("error", loc, "가중치/노브는 허용 범위의 유한 숫자여야 합니다")

    def patterns(values, loc):
        if not isinstance(values, list):
            emit("error", loc, "패턴 목록이 필요합니다")
            return
        for i, pattern in enumerate(values):
            try:
                re.compile(pattern)
            except (re.error, TypeError) as exc:
                emit("error", f"{loc}[{i}]", f"정규식 컴파일 실패: {exc}")

    def items(values, loc, id_key="id", required_name=False):
        if not isinstance(values, list):
            emit("error", loc, "규칙/분류 목록이 필요합니다")
            return
        for i, item in enumerate(values):
            here = f"{loc}[{i}]"
            if not isinstance(item, dict):
                emit("error", here, "객체가 필요합니다")
                continue
            identifier = item.get(id_key)
            if not isinstance(identifier, (str, int)) or isinstance(identifier, bool) or identifier == "":
                emit("error", here, f"필수 항목 {id_key} 누락/형식 오류")
            elif identifier in ids:
                emit("error", here, f"중복 ID: {identifier}")
            ids.add(identifier if isinstance(identifier, (str, int)) else None)
            if required_name and not isinstance(item.get("name"), str):
                emit("error", here, "필수 항목 name 누락/형식 오류")
            raw_cues = item.get("cues", [])
            if not isinstance(raw_cues, list) or any(not isinstance(c, str) for c in raw_cues):
                emit("error", here + ".cues", "문자열 cue 목록이 필요합니다")
                raw_cues = []
            for cue in raw_cues:
                cues[cue].append((here, loc.startswith("cliche")))
                if len(cue.strip()) == 1:
                    emit("warning", here, f"한 글자 cue: {cue!r}")
            patterns(item.get("patterns", []), here + ".patterns")
            if not raw_cues and not item.get("patterns"):
                emit("warning", here, "cue/패턴 둘 다 없음 (규칙 로더에서는 거절될 수 있음)")
            if "weight" in item:
                number(item["weight"], here + ".weight", positive=True)

    if "causal_types" in data:
        weights = data.get("weights")
        if not isinstance(weights, dict):
            emit("error", "weights", "필수 항목 weights 객체 누락")
            weights = {}
        for key in WEIGHTS:
            if key not in weights:
                emit("error", "weights", f"필수 항목 {key} 누락")
        for key, value in weights.items():
            number(value, "weights." + key)
        patterns(data.get("number_patterns", []), "number_patterns")
        items(data["causal_types"], "causal_types", required_name=True)
        # The loader uses separate ID namespaces for causal types and other rules.
        ids.clear()
        for key in ("pillar_rules", "cliche_rules", "weight_rules"):
            items(data.get(key, []), key)
        packs = data.get("packs", {})
        if not isinstance(packs, dict):
            emit("error", "packs", "묶음 객체가 필요합니다")
        else:
            for key, pack in packs.items():
                if isinstance(pack, dict):
                    items(pack.get("rules", []), "packs." + key)
                elif not isinstance(pack, list) or any(not isinstance(c, str) for c in pack):
                    emit("error", "packs." + key, "묶음 규칙 또는 문자열 목록이 필요합니다")
    elif "ontology" in data:
        onto = data["ontology"]
        if not isinstance(onto, dict):
            emit("error", "ontology", "분류 객체가 필요합니다")
            return issues
        classes = onto.get("classes", [])
        items(classes, "ontology.classes", id_key="name")
        names = {c.get("name") for c in classes if isinstance(c, dict) and isinstance(c.get("name"), str)} | {"Unclassified"} if isinstance(classes, list) else {"Unclassified"}
        for key in ("diet_order", "never_remove"):
            values = onto.get(key, [])
            if not isinstance(values, list):
                emit("error", "ontology." + key, "분류 이름 목록이 필요합니다")
                continue
            for name in values:
                if not isinstance(name, str) or name not in names:
                    emit("error", "ontology." + key, f"정의 안 된 분류: {name}")
        diet = onto.get("diet_order", [])
        for name in sorted(names):
            if isinstance(diet, list) and name not in diet:
                emit("warning", "ontology.diet_order", f"분류 {name} 누락: 맨 뒤로 감")
        knobs = data.get("knobs", {})
        if not isinstance(knobs, dict):
            emit("error", "knobs", "노브 객체가 필요합니다")
        else:
            for key, value in knobs.items():
                if isinstance(value, str):
                    if value not in ("Low", "Mid", "High"):
                        emit("error", "knobs." + key, f"알 수 없는 노브 수준: {value}")
                else:
                    number(value, "knobs." + key, bounded=True)
        focus = data.get("focus", {})
        if not isinstance(focus, dict):
            emit("error", "focus", "집중 키워드 객체가 필요합니다")
        else:
            if len(focus) > 5:
                emit("error", "focus", "집중 키워드 최대 5개")
            for key, value in focus.items():
                number(value, "focus." + key, positive=True)
        rules_path = ROOT / "data/golden_rules/research_v1.json" if data.get("rules", "default") == "default" else path.parent / str(data["rules"])
        try:
            known_packs = json.loads(rules_path.read_text(encoding="utf-8")).get("packs", {})
            packs = data.get("packs", [])
            if not isinstance(packs, list):
                emit("error", "packs", "묶음 이름 목록이 필요합니다")
            else:
                for pack in packs:
                    if not isinstance(pack, str) or pack not in known_packs:
                        emit("error", "packs", f"없는 묶음 이름: {pack}")
        except (OSError, ValueError) as exc:
            emit("error", "rules", f"규칙 파일 읽기 실패: {exc}")
    else:
        emit("error", "$", "필수 항목 ontology 또는 causal_types가 필요합니다")
    for cue, occurrences in cues.items():
        distinct = list(dict.fromkeys(occurrences))
        if len(distinct) > 1:
            locations = ", ".join(loc for loc, _ in distinct)
            emit("warning", locations, f"cue 중복 {cue!r}; 분류는 첫 위치 우선, 규칙 점수는 모두 적용")
            if any(c for _, c in distinct) and any(not c for _, c in distinct):
                emit("warning", locations, f"클리셰와 다른 규칙에 동시 cue: {cue!r}")
    return issues


def main(paths=()):
    paths = list(paths) or sorted((ROOT / "profiles").glob("*.json")) + [ROOT / "data/golden_rules/research_v1.json"]
    issues = [issue for path in paths for issue in check_file(path)]
    print("| 파일 | 종류 | 위치 | 메시지 |\n| --- | --- | --- | --- |")
    for issue in issues:
        print("| " + " | ".join(str(v).replace("|", "\\|").replace("\n", " ") for v in (issue.file, issue.severity, issue.location, issue.message)) + " |")
    errors = sum(i.severity == "error" for i in issues)
    print(f"{len(paths)} files: {errors} errors, {len(issues) - errors} warnings")
    return 1 if errors else 0
