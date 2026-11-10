"""Sentence-level filter comparison and local board history sparklines."""
from __future__ import annotations

import argparse
from collections import defaultdict
import html
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from scripts import filter_board
from rag_research_agent.rag.profile import Equalizer

CSS = "body{background:#0e141b;color:#e6edf6;font:14px/1.6 sans-serif;margin:20px}section{background:#131c27;padding:16px;margin:16px 0;border-radius:10px}.scroll{overflow-x:auto}table{border-collapse:collapse;min-width:850px}td,th{padding:8px;border-bottom:1px solid #24324a;text-align:left}svg{background:#0e141b}"


def compare(set_path, a, b, budget=200):
    gset = json.loads(Path(set_path).read_text(encoding="utf-8"))
    ba, ta = Equalizer.from_profile(a).brief(gset["draft"], budget=budget)
    bb, tb = Equalizer.from_profile(b).brief(gset["draft"], budget=budget)
    left, right = {r["id"]: r for r in ta.rows}, {r["id"]: r for r in tb.rows}
    rows = []
    for sid in dict.fromkeys([*left, *right]):
        ra, rb = left.get(sid, {}), right.get(sid, {})
        text = ra.get("text", rb.get("text", ""))
        kept_a, kept_b = bool(ra.get("kept")), bool(rb.get("kept"))
        rows.append({"id": sid, "text": text, "a": kept_a, "b": kept_b,
                     "label_a": ra.get("label", ""), "label_b": rb.get("label", ""),
                     "score_a": ra.get("final", 0), "score_b": rb.get("final", 0),
                     "mark": "KEEP" if text in gset.get("must_keep", []) else "CLICHE" if text in gset.get("cliche", []) else "",
                     "different": kept_a != kept_b})
    rows.sort(key=lambda r: not r["different"])
    return {"a": a, "b": b, "rows": rows, "differences": sum(r["different"] for r in rows),
            "metrics_a": filter_board.measure(gset, ba, ta, budget),
            "metrics_b": filter_board.measure(gset, bb, tb, budget)}


def history_series(path):
    series = defaultdict(lambda: {"keep_hit": [], "cliche_left": []})
    if not path or not Path(path).exists():
        return {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        run = json.loads(line)
        for row in run.get("rows", []):
            key = row["set"] + " / " + row["config"]
            for metric in ("keep_hit", "cliche_left"):
                series[key][metric].append(row.get(metric))
    return dict(series)


def sparkline(values):
    points = [(i, float(v)) for i, v in enumerate(values) if isinstance(v, (int, float))]
    if not points:
        return "(기록 없음)"
    high = max(1, max(v for _, v in points))
    coords = " ".join(f"{5 + i * 150 / max(1, len(values) - 1):.1f},{35 - v * 30 / high:.1f}" for i, v in points)
    return f'<svg viewBox="0 0 160 40" width="160" height="40" role="img" aria-label="실행별 추이"><polyline points="{coords}" fill="none" stroke="#78d5ef" stroke-width="2"/></svg>'


def render(comparison, series):
    rows = comparison["rows"] if comparison else []
    md = ["# 필터 차이 보드", "", f"차이 문장: {comparison['differences'] if comparison else 0}", "",
          "| ID | A | B | A 분류 | B 분류 | A 점수 | B 점수 | 표시 | 문장 |", "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    table = []
    for row in rows:
        values = [row["id"], "●" if row["a"] else "○", "●" if row["b"] else "○", row["label_a"], row["label_b"],
                  row["score_a"], row["score_b"], row["mark"], row["text"]]
        md.append("| " + " | ".join(str(v).replace("|", "\\|").replace("\n", " ") for v in values) + " |")
        table.append("<tr>" + "".join(f"<td>{html.escape(str(v))}</td>" for v in values) + "</tr>")
    histories = []
    md += ["", "## 실행 추이", ""]
    for key, metrics in series.items():
        histories.append(f"<h3>{html.escape(key)}</h3>")
        for metric, values in metrics.items():
            histories.append(f"<p>{metric}: {sparkline(values)} {html.escape(str(values))}</p>")
            md.append(f"- {key} · {metric}: {values}")
    if not series:
        histories.append("<p>실행 기록이 없습니다.</p>")
        md.append("실행 기록이 없습니다.")
    names = f"A: {comparison['a']} · B: {comparison['b']}" if comparison else "실행 기록 추이"
    page = ('<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>필터 차이 보드</title><style>{CSS}</style></head><body><h1>필터 차이 보드</h1><p>{html.escape(names)}</p>'
            f'<p>차이 문장: {comparison["differences"] if comparison else 0}</p><section class="scroll"><table>'
            '<tr><th>ID</th><th>A</th><th>B</th><th>A 분류</th><th>B 분류</th><th>A 점수</th><th>B 점수</th><th>표시</th><th>문장</th></tr>'
            + "".join(table) + '</table></section><section><h2>실행 추이</h2>' + "".join(histories) + '</section></body></html>')
    return page, "\n".join(md)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--a", default="litigation")
    ap.add_argument("--b", default="research")
    ap.add_argument("--set")
    ap.add_argument("--budget", type=int, default=200)
    ap.add_argument("--history")
    ap.add_argument("--out", default=".runs")
    args = ap.parse_args(argv)
    try:
        if args.budget <= 0:
            raise ValueError("budget must be positive")
        result = compare(args.set, args.a, args.b, args.budget) if args.set else None
        page, md = render(result, history_series(args.history))
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "board_diff.html").write_text(page, encoding="utf-8")
        (out / "board_diff.md").write_text(md, encoding="utf-8")
        print(out / "board_diff.html")
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f"입력 오류: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
