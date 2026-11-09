"""Feedback loop for golden rules: score a draft, compare with your golden set, compare with the last run.

    python scripts/golden_edge_eval.py --set data/golden_sets/macro_synthetic_v1.json --packs macro

Loop: read the report -> edit data/golden_rules/*.json (rules) OR data/golden_sets/*.json (your picks)
-> run again. Every run is appended to .runs/edge_eval_history.jsonl and compared with the previous run
of the same golden set, so you can see whether an edit helped. Change one file at a time.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rag_research_agent.core.types import Segment  # noqa: E402
from rag_research_agent.edge.rules import load_rules  # noqa: E402
from rag_research_agent.edge.scorer import RuleEdgeScorer  # noqa: E402

SENT_END = re.compile(r"(?<=[.!?。])\s+|\n+")


def split_sentences(text: str) -> list[Segment]:
    segs, start = [], 0
    for m in list(SENT_END.finditer(text)) + [None]:
        end = m.start() if m else len(text)
        piece = text[start:end]
        if piece.strip():
            lead = len(piece) - len(piece.lstrip())
            segs.append(Segment(f"s{len(segs) + 1:02d}", "draft", start + lead, start + len(piece.rstrip())))
        if m:
            start = m.end()
    return segs


def evaluate(rules_path: Path, set_path: Path, packs: list[str]) -> dict:
    rules = load_rules(rules_path)
    gset_raw = set_path.read_bytes()
    gset = json.loads(gset_raw.decode("utf-8"))
    text = gset["draft"]
    segs = split_sentences(text)
    sent = {s.segment_id: text[s.start:s.end] for s in segs}
    scorer = RuleEdgeScorer(rules, text, packs)
    scores = {e.segment_id: e for e in scorer.score(segs)}
    expl = {s.segment_id: scorer.explain_one(s) for s in segs}
    order = sorted(segs, key=lambda s: (-scores[s.segment_id].total, s.start))
    rank = {s.segment_id: i + 1 for i, s in enumerate(order)}

    keep = [k.strip() for k in gset.get("must_keep", [])]
    cliche = [c.strip() for c in gset.get("cliche", [])]
    unknown = [x for x in keep + cliche if x not in sent.values()]
    keep_ids = [i for i, t in sent.items() if t in keep]
    cliche_ids = [i for i, t in sent.items() if t in cliche]
    k = len(keep_ids)
    top_k = {s.segment_id for s in order[:k]}
    bottom = {s.segment_id for s in order[-len(cliche_ids):]} if cliche_ids else set()
    protected = [i for i in sent if expl[i].protected]

    rows = []
    for s in order:
        i, e = s.segment_id, expl[s.segment_id]
        label = "KEEP" if i in keep_ids else "CLICHE" if i in cliche_ids else ""
        why = []
        if e.causal_ids: why.append("인과" + ",".join(map(str, e.causal_ids)))
        if e.pillars: why.append("/".join(e.pillars))
        if e.packs: why.append("pack:" + "/".join(e.packs))
        if e.numbers: why.append(f"수치{e.numbers}")
        if e.cliches: why.append("클리셰:" + "/".join(e.cliches))
        if e.protected: why.append("항상보호")
        rows.append({"rank": rank[i], "id": i, "score": scores[i].total, "label": label,
                     "why": " ".join(why) or "-", "text": sent[i]})
    metrics = {
        "keep_recall_at_k": round(len(top_k & set(keep_ids)) / k, 3) if k else None,
        "cliche_in_bottom": round(len(bottom & set(cliche_ids)) / len(cliche_ids), 3) if cliche_ids else None,
        "keep_mean_rank": round(sum(rank[i] for i in keep_ids) / k, 2) if k else None,
        "protected": len(protected),
        "segments": len(segs),
    }
    return {
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "set": gset.get("name", set_path.stem),
        "rules_file": str(rules_path.relative_to(ROOT)) if rules_path.is_relative_to(ROOT) else str(rules_path),
        "rule_version": rules.rule_version,
        "golden_version": hashlib.sha256(gset_raw).hexdigest()[:12],
        "packs": packs,
        "metrics": metrics,
        "misses": [r["id"] for r in rows if r["label"] == "KEEP" and r["id"] not in top_k],
        "false_highs": [r["id"] for r in rows if r["id"] in top_k and r["label"] != "KEEP"],
        "unknown_lines": unknown,
        "rows": rows,
    }


def previous_run(history: Path, set_name: str) -> dict | None:
    if not history.exists():
        return None
    last = None
    for line in history.read_text(encoding="utf-8").splitlines():
        if line.strip():
            run = json.loads(line)
            if run.get("set") == set_name:
                last = run
    return last


def render(run: dict, prev: dict | None) -> str:
    m = run["metrics"]
    out = [f"# Edge eval: {run['set']}", "",
           f"rules `{run['rules_file']}` v`{run['rule_version']}` · golden v`{run['golden_version']}` · packs {run['packs'] or '-'}", "",
           "| 지표 | 값 | 뜻 |", "| --- | --- | --- |",
           f"| keep_recall_at_k | {m['keep_recall_at_k']} | 보존할 문장이 상위 k(=보존 개수) 안에 든 비율. 1.0이 목표 |",
           f"| cliche_in_bottom | {m['cliche_in_bottom']} | 클리셰가 하위권에 깔린 비율. 1.0이 목표 |",
           f"| keep_mean_rank | {m['keep_mean_rank']} | 보존할 문장의 평균 순위. 낮을수록 좋음 |",
           f"| protected | {m['protected']} | 항상 보호 규칙에 걸린 문장 수 |", ""]
    if prev:
        pm = prev["metrics"]
        changed = []
        if prev["rule_version"] != run["rule_version"]: changed.append("rules")
        if prev["golden_version"] != run["golden_version"]: changed.append("golden set")
        if prev.get("packs") != run["packs"]: changed.append("packs")
        out += [f"## 지난 실행과 비교 ({prev['time']})", "",
                f"바뀐 것: {', '.join(changed) or '없음'}" + ("  ⚠ 두 가지 이상을 한 번에 바꿨어요. 무엇 때문인지 구분이 어려워요." if len(changed) > 1 else ""), ""]
        for key in ("keep_recall_at_k", "cliche_in_bottom", "keep_mean_rank"):
            a, b = pm.get(key), m.get(key)
            if a is not None and b is not None:
                better = (b > a) if key != "keep_mean_rank" else (b < a)
                tag = "좋아짐" if better else ("같음" if a == b else "나빠짐")
                out.append(f"- {key}: {a} → {b} ({tag})")
        out.append("")
    if run["unknown_lines"]:
        out += ["## 골든셋 문장이 초안에서 안 보여요 (원문과 똑같이 복사해 주세요)", ""]
        out += [f"- {u}" for u in run["unknown_lines"]] + [""]
    out += ["## 순위", "", "| 순위 | 점수 | 표시 | 이유 | 문장 |", "| --- | --- | --- | --- | --- |"]
    for r in run["rows"]:
        flag = r["label"] + (" ✗놓침" if r["id"] in run["misses"] else "") + (" ▲과대" if r["id"] in run["false_highs"] else "")
        out.append(f"| {r['rank']} | {r['score']} | {flag.strip()} | {r['why']} | {r['text']} |")
    out += ["", "✗놓침 = 보존할 문장인데 상위 k 밖 · ▲과대 = 보존 목록에 없는데 상위 k 안. 다음 한 수: 놓친 문장의 표현을 규칙 cues에 추가하거나, 그 문장이 정말 보존할 문장인지 골든셋을 다시 보세요."]
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rules", default=str(ROOT / "data/golden_rules/research_v1.json"))
    ap.add_argument("--set", required=True)
    ap.add_argument("--packs", nargs="*", default=[])
    ap.add_argument("--runs", default=str(ROOT / ".runs"))
    ap.add_argument("--no-history", action="store_true")
    a = ap.parse_args(argv)
    runs = Path(a.runs)
    run = evaluate(Path(a.rules).resolve(), Path(a.set).resolve(), a.packs)
    history = runs / "edge_eval_history.jsonl"
    prev = previous_run(history, run["set"])
    report = render(run, prev)
    print(report)
    if not a.no_history:
        runs.mkdir(parents=True, exist_ok=True)
        with history.open("a", encoding="utf-8") as f:
            f.write(json.dumps({k: v for k, v in run.items() if k != "rows"}, ensure_ascii=False) + "\n")
        (runs / "last_report.md").write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
