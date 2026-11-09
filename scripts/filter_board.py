"""Numeric board: run every filter (and/or a knob grid) on every golden set and compare.

    python scripts/filter_board.py                       # all filters x all golden sets
    python scripts/filter_board.py --filters litigation politics --budget 300
    python scripts/filter_board.py --grid                # also the 3x3 knob grid with no filter

Writes .runs/board.md and .runs/board.html (dark, opens on a phone) and appends .runs/board_history.jsonl,
so each board shows the change against the previous board (did my rule / filter edit help?).
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rag_research_agent.core.types import Knobs  # noqa: E402
from rag_research_agent.knobs.mapper import load_config  # noqa: E402
from rag_research_agent.rag.brief import DEFAULT_CONFIG, Parts, build_brief  # noqa: E402


def measure(gset: dict, brief, trace, budget: int) -> dict:
    keep = {k.strip() for k in gset.get("must_keep", [])}
    cliche = {c.strip() for c in gset.get("cliche", [])}
    kept = [r for r in trace.rows if r.get("kept")]
    texts = {r["text"] for r in kept}
    used = sum(len(r["text"]) for r in kept)
    return {
        "status": brief.status.value,
        "kept": len(kept),
        "keep_hit": round(len(texts & keep) / len(keep), 3) if keep else None,   # share of must-keep sentences kept
        "cliche_left": len(texts & cliche),
        "protected": sum(1 for r in trace.rows if r["protected"]),
        "used": used,
        "budget": budget,
        "compression": round(used / max(1, sum(len(r["text"]) for r in trace.rows)), 3),
    }


def run_board(sets: list[Path], filters: list[str], grid: bool, budget: int, task: str | None) -> list[dict]:
    parts = Parts().ready()
    rows = []
    for sp in sets:
        g = json.loads(sp.read_text(encoding="utf-8"))
        configs = [(f, dict(preset=f)) for f in filters]
        if grid:
            configs += [(f"knobs s={s} w={w}", dict(knobs=Knobs(s, w))) for s in (0.2, 0.5, 0.8) for w in (0.2, 0.5, 0.8)]
        for name, kw in configs:
            b, t = build_brief(g["draft"], task, budget=budget, parts=parts, **kw)
            rows.append({"set": g.get("name", sp.stem), "config": name, "settings": t.settings, **measure(g, b, t, budget)})
    return rows


def previous(history: Path) -> dict:
    if not history.exists():
        return {}
    lines = [l for l in history.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not lines:
        return {}
    last = json.loads(lines[-1])
    return {(r["set"], r["config"]): r for r in last["rows"]}


def delta(cur, old, key, higher_better=True):
    if old is None or old.get(key) is None or cur.get(key) is None:
        return ""
    d = round(cur[key] - old[key], 3)
    if d == 0:
        return ""
    good = (d > 0) == higher_better
    return f" ({'+' if d > 0 else ''}{d}{' ▲' if good else ' ▼'})"


COLS = [("keep_hit", "보존 적중", True), ("cliche_left", "클리셰 남음", False), ("kept", "남긴 문장", None),
        ("compression", "압축률", None), ("protected", "보호", None)]


def to_markdown(rows, prev, meta) -> str:
    out = [f"# Filter board · {meta['time']}", "", f"rules v`{meta['rule_version']}` · budget {meta['budget']} · task {meta['task']!r}", "",
           "보존 적중 = 꼭 남길 문장 중 남은 비율(높을수록 좋음) · 클리셰 남음 = 낮을수록 좋음 · 압축률 = 남긴 글자 / 원문 글자. 괄호는 지난 보드 대비 변화.", ""]
    for s in sorted({r["set"] for r in rows}):
        out += [f"## {s}", "", "| 설정 | 상태 | " + " | ".join(c[1] for c in COLS) + " |", "| --- | --- | " + " | ".join("---" for _ in COLS) + " |"]
        for r in [r for r in rows if r["set"] == s]:
            o = prev.get((r["set"], r["config"]))
            cells = [f"{r[k]}{delta(r, o, k, hb) if hb is not None else ''}" for k, _, hb in COLS]
            out.append(f"| {r['config']} | {r['status']} | " + " | ".join(cells) + " |")
        out.append("")
    return "\n".join(out)


def to_html(rows, prev, meta) -> str:
    def bar(v, good_high=True):
        if v is None:
            return "-"
        pct = int(v * 100)
        color = "#4cc3a8" if (v >= 0.8 if good_high else v <= 0.2) else ("#ddb965" if (v >= 0.5 if good_high else v <= 0.5) else "#c58b92")
        return f'<div class="bar"><span style="width:{pct}%;background:{color}"></span></div><b>{v}</b>'
    sections = []
    for s in sorted({r["set"] for r in rows}):
        trs = []
        for r in [r for r in rows if r["set"] == s]:
            o = prev.get((r["set"], r["config"]))
            trs.append("<tr>" + f"<td class='name'>{html.escape(r['config'])}</td><td class='st st-{r['status']}'>{r['status']}</td>"
                       f"<td>{bar(r['keep_hit'])}<i>{html.escape(delta(r, o, 'keep_hit'))}</i></td>"
                       f"<td>{r['cliche_left']}<i>{html.escape(delta(r, o, 'cliche_left', False))}</i></td>"
                       f"<td>{r['kept']}</td><td>{r['compression']}</td><td>{r['protected']}</td></tr>")
        sections.append(f"<section><div class='eyebrow'>GOLDEN SET</div><h2>{html.escape(s)}</h2><div class='scroll'><table>"
                        "<tr><th>설정</th><th>상태</th><th>보존 적중</th><th>클리셰 남음</th><th>남긴 문장</th><th>압축률</th><th>보호</th></tr>"
                        + "".join(trs) + "</table></div></section>")
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Filter Board</title><style>
:root{{--bg:#0e141b;--card:#131c27;--line:#24324a;--text:#e6edf6;--muted:#9aabbd;--cyan:#78d5ef}}
body{{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 "Noto Sans KR","Malgun Gothic",sans-serif;padding:16px}}
header,section{{max-width:1000px;margin:0 auto 16px}} section{{background:var(--card);border:1px solid var(--line);border-left:3px solid #5ba7db;border-radius:10px;padding:14px}}
section:nth-of-type(2n){{border-left-color:#4cc3a8}} .eyebrow{{color:var(--cyan);font-size:11px;letter-spacing:.08em;font-weight:700}}
h1{{margin:4px 0}} h2{{margin:2px 0 10px;font-size:17px}} p{{color:var(--muted);margin:4px 0}}
.scroll{{overflow-x:auto}} table{{border-collapse:collapse;width:100%;min-width:640px}} th,td{{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}}
th{{color:var(--muted);font-weight:600;font-size:12px}} td.name{{font-weight:600}} i{{color:var(--muted);font-style:normal;font-size:12px;margin-left:4px}}
.bar{{display:inline-block;width:70px;height:6px;background:#24324a;border-radius:3px;margin-right:6px;vertical-align:middle}} .bar span{{display:block;height:100%;border-radius:3px}}
.st{{font-size:12px}} .st-OK{{color:#91cc45}} .st-BUDGET_PROTECTED_OVERFLOW,.st-OUTPUT_REJECTED,.st-BLOCKED{{color:#c58b92}} .st-REQUEST_MORE{{color:#ddb965}}
footer{{max-width:1000px;margin:0 auto;color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.06em}}
</style></head><body><header><div class="eyebrow">EQUALIZER · FILTER BOARD</div><h1>필터 비교 보드</h1>
<p>{html.escape(meta['time'])} · rules v{html.escape(meta['rule_version'])} · budget {meta['budget']} · task {html.escape(repr(meta['task']))}</p>
<p>보존 적중 = 꼭 남길 문장 중 남은 비율(높을수록 좋음). 클리셰 남음 = 낮을수록 좋음. 압축률 = 남긴 글자 / 원문 글자. 회색 괄호 = 지난 보드 대비 변화.</p></header>
{''.join(sections)}<footer>합성 골든셋 기준 · 규칙·필터는 v0 초안이며 보정 전</footer></body></html>"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sets", nargs="*", default=sorted(str(p) for p in (ROOT / "data/golden_sets").glob("*.json")))
    ap.add_argument("--filters", nargs="*")
    ap.add_argument("--grid", action="store_true")
    ap.add_argument("--budget", type=int, default=300)
    ap.add_argument("--task")
    ap.add_argument("--runs", default=str(ROOT / ".runs"))
    a = ap.parse_args(argv)
    cfg = load_config(DEFAULT_CONFIG)
    filters = a.filters or list(dict.fromkeys(p.name for p in cfg.presets.values()))
    rows = run_board([Path(s) for s in a.sets], filters, a.grid, a.budget, a.task)
    runs = Path(a.runs)
    runs.mkdir(parents=True, exist_ok=True)
    history = runs / "board_history.jsonl"
    prev = previous(history)
    meta = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "rule_version": Parts().ready().rules.rule_version,
            "budget": a.budget, "task": a.task}
    md = to_markdown(rows, prev, meta)
    (runs / "board.md").write_text(md, encoding="utf-8")
    (runs / "board.html").write_text(to_html(rows, prev, meta), encoding="utf-8")
    with history.open("a", encoding="utf-8") as f:
        f.write(json.dumps({**meta, "rows": [{k: v for k, v in r.items() if k != "settings"} for r in rows]}, ensure_ascii=False) + "\n")
    print(md)
    print(f"\nHTML: {runs / 'board.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
