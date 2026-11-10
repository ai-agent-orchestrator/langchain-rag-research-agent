"""Suggest rule/profile cue edits for human review; never edit source rules or profiles."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from scripts import golden_edge_eval
from rag_research_agent.edge.focus import normalize, STOPWORDS
from rag_research_agent.edge.rules import load_rules
from rag_research_agent.rag.profile import load_profile


def _rule_items(rules):
    return [*rules.causal_types, *rules.pillar_rules, *rules.cliche_rules,
            *rules.weight_rules, *(item for pack in rules.packs.values() for item in pack)]


def candidate_terms(text, rules, other_kept=()):
    items = _rule_items(rules)
    cues = [cue.strip() for item in items for cue in item.cues if cue.strip()]
    patterns = [pattern for item in items for pattern in getattr(item, "patterns", ())]
    terms = set()
    for token in re.findall(r"[가-힣A-Za-z]{2,}", text):
        term = normalize(token)
        if not 2 <= len(term) <= 6 or term in STOPWORDS:
            continue
        if any(term in cue or cue in term for cue in cues) or any(p.search(term) for p in patterns):
            continue
        terms.add(term)
    return [{"cue": term, "support": sum(term in sent for sent in other_kept)}
            for term in sorted(terms, key=lambda t: (-sum(t in sent for sent in other_kept), -len(t), t))]


def suggest(set_path, packs=(), profile=None, rules_path=None):
    rules_path = Path(rules_path or ROOT / "data/golden_rules/research_v1.json")
    run = golden_edge_eval.evaluate(rules_path, Path(set_path), list(packs))
    rules = load_rules(rules_path)
    gset = json.loads(Path(set_path).read_text(encoding="utf-8"))
    selected_profile = load_profile(profile) if profile else None
    boosting = [*rules.causal_types, *rules.pillar_rules, *rules.weight_rules,
                *(item for name in packs for item in rules.packs.get(name, ()))]
    rows = []
    for row in run["rows"]:
        missed, false_high = row["id"] in run["misses"], row["id"] in run["false_highs"]
        if not missed and not false_high:
            continue
        additions = candidate_terms(row["text"], rules, [s for s in gset.get("must_keep", []) if s != row["text"]]) if missed else []
        removals = []
        if false_high:
            for item in boosting:
                for cue in item.cues:
                    if cue and cue in row["text"]:
                        removals.append({"rule_id": str(item.id), "cue": cue})
                for pattern in getattr(item, "patterns", ()):
                    match = pattern.search(row["text"])
                    if match:
                        removals.append({"rule_id": str(item.id), "pattern": pattern.pattern, "matched": match[0]})
        classification = selected_profile.labeler.label_text(row["text"]) if selected_profile else None
        profile_suggestions = []
        if missed and selected_profile and classification == "Unclassified":
            for item in selected_profile.labeler.classes[:3]:
                profile_suggestions.append({"class": item.name, "cues": [a["cue"] for a in additions[:3]],
                                            "note": "이 분류 의미에 맞는지 검토 후 추가하면 매칭됨; 앞 분류가 우선"})
        rows.append({"id": row["id"], "text": row["text"], "reason": row["why"],
                     "missed": missed, "false_high": false_high, "add_candidates": additions,
                     "remove_candidates": removals, "profile_label": classification,
                     "profile_suggestions": profile_suggestions})
    return {"set": run["set"], "rule_version": run["rule_version"], "profile": profile,
            "rows": rows, "note": "후보만 제시. 규칙/프로필 자동 수정 없음. 분류 후보는 의미 검토 필요."}


def to_markdown(result):
    lines = [f"# 신호 표현 후보: {result['set']}", "", result["note"], "",
             "| 문장 | 현재 이유 | 추가 후보 | 뺄 후보 | 프로필 |", "| --- | --- | --- | --- | --- |"]
    for row in result["rows"]:
        values = [row["text"], row["reason"], ", ".join(f"{v['cue']} (다른 보존문장 {v['support']})" for v in row["add_candidates"]),
                  json.dumps(row["remove_candidates"], ensure_ascii=False),
                  str(row["profile_label"] or "-") + " " + json.dumps(row["profile_suggestions"], ensure_ascii=False)]
        lines.append("| " + " | ".join(v.replace("|", "\\|").replace("\n", " ") for v in values) + " |")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--set", required=True)
    ap.add_argument("--packs", nargs="*", default=[])
    ap.add_argument("--profile")
    ap.add_argument("--out", default=".runs")
    args = ap.parse_args(argv)
    try:
        out = Path(args.out).resolve()
        if any(out.is_relative_to(ROOT / folder) for folder in ("data", "profiles")):
            raise ValueError("추천 결과는 .runs에 저장해 주세요")
        result = suggest(args.set, args.packs, args.profile)
        report = to_markdown(result)
        out.mkdir(parents=True, exist_ok=True)
        (out / "cue_suggestions.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "cue_suggestions.md").write_text(report, encoding="utf-8")
        print(report)
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f"입력 오류: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
