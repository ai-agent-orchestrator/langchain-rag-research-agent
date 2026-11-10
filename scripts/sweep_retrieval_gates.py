"""Sweep saved E4/E5 scores, never load an embedding model or tune on confirm."""
import argparse
import html
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rag_research_agent.observe.gate_grid import sweep


def write_report(record, absolutes, gaps, out):
    result = sweep(record["evaluation_rows"], absolutes, gaps)
    fake = record.get("model", "") == "fake" or "fake" in record.get("model_id", "")
    columns = {"path_test": result if fake else None, "real_model": None if fake else result}
    lines = ["# E6 판정 경계", "", result["note"], "",
             "| split | τ_abs | τ_gap | 오수용: fake 경로 시험 | 오수용: 실제 모델 | 오거절: fake 경로 시험 | 오거절: 실제 모델 |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    def cell(rate):
        return f"{rate['errors']}/{rate['n']} = {rate['rate']}; Wilson95={rate['wilson95']}"
    for split, rows in [("compare", result["compare_grid"]), ("confirm (선택된 한 조합)", [result["confirm"]] if result["confirm"] else [])]:
        for row in rows:
            fa, fr = cell(row["false_accept"]), cell(row["false_refusal"])
            values = [fa, "미실행", fr, "미실행"] if fake else ["미실행", fa, "미실행", fr]
            lines.append(f"| {split} | {row['tau_abs']} | {row['tau_gap']} | " + " | ".join(values) + " |")
    text = "\n".join(lines)
    # One pair of FAR/FRR curves per gap value; vertical bars show Wilson intervals.
    svg = ['<svg viewBox="0 0 900 480" role="img" aria-label="compare 판정 경계 곡선">']
    xs = sorted(set(absolutes))
    def x(a):
        return 70 + 750 * (a - min(xs)) / (max(xs) - min(xs) or 1)
    svg.append('<path d="M70 30V420H840" fill="none" stroke="black"/><text x="60" y="20">오류율 (0~1)</text><text x="750" y="465">τ_abs</text>')
    colors = ["#125ac1", "#bb4400", "#237b35", "#713fab"]
    for n, gap in enumerate(sorted(set(gaps))):
        rows = sorted((r for r in result["compare_grid"] if r["tau_gap"] == gap), key=lambda r: r["tau_abs"])
        for metric, dash in [("false_accept", ""), ("false_refusal", 'stroke-dasharray="6 4"')]:
            points = []
            for row in rows:
                rate = row[metric]
                if rate["rate"] is None:
                    continue
                px, py = x(row["tau_abs"]), 420 - 380 * rate["rate"]
                low, high = rate["wilson95"]
                points.append(f"{px},{py}")
                svg.append(f'<g stroke="{colors[n % 4]}"><title>{html.escape(metric)}; gap={gap}; abs={row["tau_abs"]}; {cell(rate)}</title><path d="M{px} {420-380*high}V{420-380*low}"/><circle cx="{px}" cy="{py}" r="4"/></g>')
            svg.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="{colors[n % 4]}" {dash}><title>{metric}, gap={gap}</title></polyline>')
    svg.append('</svg><p>실선: 오수용, 점선: 오거절. 점에 마우스를 올리면 τ와 Wilson 구간을 표시합니다. confirm은 곡선에서 제외합니다.</p>')
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "gates.json").write_text(json.dumps(columns, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "gates.md").write_text(text, encoding="utf-8")
    (out / "gates.html").write_text('<!doctype html><meta charset="utf-8"><title>E6 gate grid</title>' + "\n".join(svg) + '<pre>' + html.escape(text) + '</pre>', encoding="utf-8")
    return columns


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", required=True)
    ap.add_argument("--tau-abs", nargs="+", type=float, default=[0, .2, .4, .6, .8, 1])
    ap.add_argument("--tau-gap", nargs="+", type=float, default=[0, .05, .1, .2])
    ap.add_argument("--out", default=".runs/e6")
    args = ap.parse_args(argv)
    if not Path(args.out).resolve().is_relative_to(ROOT / ".runs"):
        ap.error("results must be inside .runs")
    write_report(json.loads(Path(args.input).read_text(encoding="utf-8")), args.tau_abs, args.tau_gap, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
