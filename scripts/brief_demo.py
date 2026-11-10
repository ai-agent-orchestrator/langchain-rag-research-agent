"""Turn the two knobs and see what the brief keeps (feedback loop for the Equalizer).

    python scripts/brief_demo.py --set data/golden_sets/macro_synthetic_v1.json --preset research --budget 300
    python scripts/brief_demo.py --set data/golden_sets/macro_synthetic_v1.json --similarity 0.8 --edge 0.2 --task "금리 가계부채"
    python scripts/brief_demo.py --set data/golden_sets/macro_synthetic_v1.json --sweep        # compare knob grid
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rag_research_agent.core.types import Knobs  # noqa: E402
from rag_research_agent.rag.brief import build_brief  # noqa: E402
from rag_research_agent.compose.numbers import extract_numbers, to_markdown
from rag_research_agent.ingest.sentences import SentenceChunker


def keep_stats(trace, gset):
    keep = {k.strip() for k in gset.get("must_keep", [])}
    cliche = {c.strip() for c in gset.get("cliche", [])}
    kept = {r["text"] for r in trace.rows if r.get("kept")}
    return (len(kept & keep), len(keep), len(kept & cliche), len(kept))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", required=True)
    ap.add_argument("--preset")
    ap.add_argument("--similarity", type=float)
    ap.add_argument("--edge", type=float)
    ap.add_argument("--task")
    ap.add_argument("--budget", type=int, default=600)
    ap.add_argument("--packs", nargs="*")
    ap.add_argument("--focus", nargs="*", default=[])
    ap.add_argument("--sweep", action="store_true")
    a = ap.parse_args(argv)
    gset = json.loads(Path(a.set).read_text(encoding="utf-8"))
    focus = {k: float(w or 1) for k, _, w in (f.partition(":") for f in a.focus)} or None

    if a.sweep:
        print(f"budget {a.budget} · task {a.task!r}\n")
        print("| similarity | edge_weight | 남긴 문장 | 보존 목록 적중 | 클리셰 남음 | 상태 |\n| --- | --- | --- | --- | --- | --- |")
        for s in (0.2, 0.5, 0.8):
            for w in (0.2, 0.5, 0.8):
                b, t = build_brief(gset["draft"], a.task, Knobs(s, w), budget=a.budget, packs=a.packs, focus=focus)
                hit, total, cl, n = keep_stats(t, gset)
                print(f"| {s} | {w} | {n} | {hit}/{total} | {cl} | {b.status.value} |")
        return 0

    knobs = Knobs(a.similarity, a.edge) if a.similarity is not None and a.edge is not None else None
    b, t = build_brief(gset["draft"], a.task, knobs, a.preset, a.budget, focus, a.packs)
    hit, total, cl, n = keep_stats(t, gset)
    print("설정:", json.dumps(t.settings, ensure_ascii=False))
    print(f"상태: {b.status.value} · 남긴 문장 {n} · 보존 목록 적중 {hit}/{total} · 클리셰 남음 {cl}\n")
    print("| id | 관련도 | 엣지 | 최종 | 보호 | 후보 | 남김 | 문장 |\n| --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in t.rows:
        print(f"| {r['id']} | {r['relevance']} | {r['edge']} | {r['final']} | {'●' if r['protected'] else ''} | "
              f"{'●' if r['chosen'] else ''} | {'●' if r.get('kept') else ''} | {r['text']} |")
    if t.diet_log:
        print("\n감량 기록:\n" + "\n".join(f"- {x}" for x in t.diet_log))
    print("\n백본에 들어갈 입력:\n" + (b.final_prompt_input or "(없음)"))
    segments = [s for s in SentenceChunker().split(gset["draft"]) if s.segment_id in b.included_ids]
    print("\n## 수치 추출표\n" + to_markdown(extract_numbers(segments, gset["draft"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
