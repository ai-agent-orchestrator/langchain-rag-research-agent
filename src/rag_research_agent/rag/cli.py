"""rra command line: public inputs to extractive briefs, boards and rule scores."""
from __future__ import annotations

MATURITY = "incubating"

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
from glob import glob
from hashlib import sha256
import json
import math
from pathlib import Path
import sys

from rag_research_agent.core.types import Status
from rag_research_agent.edge.focus import build_focus
from rag_research_agent.edge.scorer import RuleEdgeScorer
from rag_research_agent.ingest.sources import Document, SourceError, load_source
from rag_research_agent.rag.brief import ROOT
from rag_research_agent.rag.profile import Equalizer, PROFILES_DIR, list_profiles


def _parser():
    ap = argparse.ArgumentParser(prog="rra", description="프로필로 추출 브리프와 비교 보드를 만듭니다")
    sub = ap.add_subparsers(dest="command", required=True)
    brief = sub.add_parser("brief")
    brief.add_argument("--profile", required=True)
    inputs = brief.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--file", nargs="+", action="extend")
    inputs.add_argument("--url", nargs="+", action="extend")
    inputs.add_argument("--text")
    brief.add_argument("--task")
    brief.add_argument("--budget", type=int, default=600)
    brief.add_argument("--focus", nargs="*", default=None)
    brief.add_argument("--auto-focus", type=int)
    brief.add_argument("--allow-network", action="store_true")
    brief.add_argument("--out", default=".runs")
    board = sub.add_parser("board")
    board.add_argument("--profiles", nargs="+", default=None)
    board.add_argument("--sets", nargs="+", default=None)
    board.add_argument("--budget", type=int, default=300)
    board.add_argument("--out", default=".runs")
    score = sub.add_parser("score")
    score.add_argument("--set", required=True)
    score.add_argument("--packs", nargs="*", default=[])
    score.add_argument("--focus", nargs="*", default=[])
    sub.add_parser("profiles")
    return ap


def _focus(tokens):
    result = {}
    for token in tokens or ():
        keyword, sep, weight = token.partition(":")
        value = float(weight) if sep else 1.0
        if not keyword.strip() or not math.isfinite(value) or value <= 0:
            raise ValueError("집중 키워드와 양의 유한 가중치를 사용해 주세요")
        result[keyword] = value
    if len(result) > 5:
        raise ValueError("집중 키워드는 최대 5개입니다")
    return result


def _write_brief(folder, doc, eq, args, profile_hash):
    focus = dict(eq.profile.preset.focus) if args.focus is None else _focus(args.focus)
    focus = build_focus(doc.text, focus, args.auto_focus)
    brief, trace = eq.brief(doc.text, task=args.task, budget=args.budget, focus=focus)
    excluded = dict(brief.excluded)
    # Record matched rule IDs alongside the scores already used by build_brief.
    scorer = RuleEdgeScorer(eq.rules, doc.text, eq.profile.preset.packs, focus=focus)
    segments = eq.profile.labeler.with_text(doc.text).label(eq.parts().chunker.split(doc.text, "draft"))
    explanations = {s.segment_id: asdict(scorer.explain_one(s)) for s in segments}
    rows = []
    for row in trace.rows:
        row = dict(row)
        row["kept"] = row["id"] in brief.included_ids
        row["reason"] = excluded.get(row["id"], "kept" if row["kept"] else "not_selected")
        row["explanation"] = explanations[row["id"]]
        row["protected_by_profile"] = row["label"] in eq.profile.never_remove
        rows.append(row)
    payload = {"document": asdict(doc), "settings": trace.settings, "status": brief.status.value,
               "rule_version": eq.rules.rule_version, "profile_hash": profile_hash,
               "rows": rows, "excluded": list(brief.excluded), "diet_log": trace.diet_log}
    lines = [f"# 추출 브리프: {doc.title}", "", f"상태: {brief.status.value}",
             f"프로필: {eq.profile.name}", f"원본: {doc.origin}", "", "## 설정", "",
             "```json", json.dumps(trace.settings, ensure_ascii=False, indent=2), "```", "",
             "## 남긴 문장", ""]
    lines += [f"- `{r['id']}` {r['text']}" for r in rows if r["kept"]] or ["(없음)"]
    lines += ["", "## 생략 번호와 사유", ""]
    lines += [f"- `{sid}`: {reason}" for sid, reason in brief.excluded] or ["(없음)"]
    lines += ["", "## 감량 기록", ""] + [f"- {entry}" for entry in trace.diet_log]
    folder.mkdir(parents=True, exist_ok=False)
    (folder / "brief.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (folder / "trace.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (folder / "input.txt").write_text(doc.text, encoding="utf-8")
    return brief.status


def _brief(args):
    if args.budget <= 0 or (args.auto_focus is not None and args.auto_focus <= 0):
        raise ValueError("budget와 auto-focus는 양수여야 합니다")
    _focus(args.focus)
    if args.text is not None:
        docs = [Document(sha256(args.text.encode()).hexdigest()[:16], "붙여넣기", args.text,
                         "text:inline", datetime.now(timezone.utc).isoformat())]
    else:
        docs = [load_source(p, args.allow_network) for p in (args.file or args.url)]
    eq = Equalizer.from_profile(args.profile)
    profile_path = Path(args.profile)
    if not profile_path.is_file():
        profile_path = PROFILES_DIR / f"{args.profile}.json"
    digest = sha256(profile_path.read_bytes()).hexdigest()
    name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + "-" + profile_path.stem
    folder = Path(args.out) / name
    if len(docs) == 1:
        statuses = [_write_brief(folder, docs[0], eq, args, digest)]
    else:
        folder.mkdir(parents=True, exist_ok=False)
        statuses, index = [], ["# 입력 문서별 브리프", ""]
        for n, doc in enumerate(docs, 1):
            child = f"{n:03d}-{doc.source_id}"
            statuses.append(_write_brief(folder / child, doc, eq, args, digest))
            index.append(f"- [{n}. {doc.title}]({child}/brief.md)")
        (folder / "index.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    print(folder.resolve())
    return 3 if Status.BLOCKED in statuses else 0


def _board(args):
    from rag_research_agent.rag import board
    if args.budget <= 0:
        raise ValueError("budget는 양수여야 합니다")
    sets = []
    for pattern in args.sets or [str(ROOT / "data/golden_sets/*.json")]:
        matches = sorted(glob(pattern))
        if not matches:
            raise ValueError(f"골든셋을 찾을 수 없습니다: {pattern}")
        sets.extend(matches)
    return board.main(["--profiles", *(args.profiles or list_profiles()), "--sets", *sets,
                       "--budget", str(args.budget), "--runs", args.out])


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    try:
        args = _parser().parse_args(argv)
        if args.command == "brief":
            return _brief(args)
        if args.command == "board":
            return _board(args)
        if args.command == "score":
            from rag_research_agent.rag import score
            _focus(args.focus)
            return score.main(["--set", args.set, "--packs", *args.packs, "--focus", *args.focus,
                               "--runs", ".runs"])
        for name in list_profiles():
            data = json.loads((PROFILES_DIR / f"{name}.json").read_text(encoding="utf-8"))
            print(f"{name}\t{data.get('label', name)}")
        return 0
    except SystemExit as exc:
        return int(exc.code)
    except (SourceError, OSError, ValueError, KeyError) as exc:
        print(f"입력·설정 오류: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
