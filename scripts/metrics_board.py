"""Offline metrics board. Inputs are complete RunEvent JSONL records, nodes nested.

Run: python scripts/metrics_board.py [--events .runs/events] [--output ...]
Guard reasons must already be masked. HTML escaping is not PII masking.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from html import escape
import json
from math import sqrt
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rag_research_agent.core.run_events import RunEvent  # noqa: E402
from rag_research_agent.rag.guard_audit import aggregate_guard_audit  # noqa: E402

MATURITY = "incubating"


def load_events(directory: Path) -> list[RunEvent]:
    """Read */events.jsonl deterministically; invalid/duplicate runs fail closed."""
    events, seen = [], set()
    for path in sorted(Path(directory).glob("*/events.jsonl")):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                event = RunEvent.from_json(line, loads=json.loads)
                if event.run_id in seen:
                    raise ValueError("duplicate run_id")
            except (TypeError, ValueError):
                # Never echo record contents or parser exception text.
                raise ValueError(f"Invalid run event at {path}:{line_number}") from None
            seen.add(event.run_id)
            events.append(event)
    return events


def ratio(count: int, total: int) -> str:
    if not total:
        return "미검증 (n=0)"
    p, z = count / total, 1.959963984540054
    d = 1 + z * z / total
    center = (p + z * z / (2 * total)) / d
    radius = z * sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / d
    return (f"{p:.1%} ({count}/{total}; Wilson 95% "
            f"{max(0, center-radius):.1%}–{min(1, center+radius):.1%})")


def listing(rows) -> str:
    return "<ul>" + "".join(f"<li>{escape(str(k))}: {escape(str(v))}</li>"
                            for k, v in rows) + "</ul>"


def bars(values) -> str:
    if not values:
        return "<p>노드 계측 없음</p>"
    maximum = max(values.values()) or 1
    return "".join(
        f'<div>{escape(name)}: {value:.2f} ms (호출당 평균)'
        f'<svg viewBox="0 0 100 6" role="img" aria-label="{escape(name, quote=True)} ms">'
        f'<rect width="{value / maximum * 100:.2f}" height="6" /></svg></div>'
        for name, value in sorted(values.items()))


def panels(events, *, gold, injections) -> str:
    n = len(events)
    paths = Counter(" → ".join(e.path) or "(빈 경로)" for e in events)
    ends = Counter(e.end_type for e in events)
    rewrites = Counter(e.loops["rewrite"] for e in events)
    trace = "<h3>경로 빈도</h3>" + listing(sorted(paths.items()))
    trace += "<h3>종료 유형</h3>" + listing((k, ratio(ends[k], n)) for k in ("END", "give_up", "cutoff"))
    trace += "<h3>rewrite 루프 분포</h3>" + listing((f"{k}회", v) for k, v in sorted(rewrites.items()))
    cost = listing([
        ("SLM 호출 수", sum(e.calls["slm"] for e in events)),
        ("Flagship 호출 수", sum(e.calls["flagship"] for e in events)),
        ("입력 토큰", sum(e.tokens["in"] for e in events)),
        ("출력 토큰", sum(e.tokens["out"] for e in events)),
        ("총 원가 KRW", f"{sum(e.cost_krw for e in events):.4f}"),
        ("건당 원가 KRW", f"{sum(e.cost_krw for e in events)/n:.4f}" if n else "미검증"),
        ("Fast", ratio(sum(e.track == "fast" for e in events), n)),
        ("Deep", ratio(sum(e.track == "deep" for e in events), n)),
    ])
    audit = aggregate_guard_audit(events, gold=gold, injection_run_ids=injections)
    guard = "<p>검색 품질 분모에서 injection 실행 제외. 과차단은 골드 대비 의심 신호입니다.</p>"
    if audit:
        row = next(iter(audit.values()))  # one domain and estimation cohort
        drop, over = row["grade"]["relevance_drop_rate"], row["overblocking"]
        guard += listing([
            ("품질 실행 수", row["quality_runs"]),
            ("RelevanceGrade 탈락률", ratio(drop["count"], drop["total"])),
            ("과차단 의심", ratio(over["count"], over["total"])),
            ("골드 실행 수", over["gold_runs"]),
        ])
        guard += "<h3>GroundedGrade / 필터 반려 코드·reason (발생 횟수)</h3>"
        guard += listing((code, f'{bucket["count"]}회 · ' + " / ".join(bucket["reason"]))
                         for code, bucket in sorted(row["guard"].items()))
    else:
        guard += "<p>미검증 (n=0)</p>"
    timings = defaultdict(list)
    for event in events:
        for node in event.nodes:
            timings[node.name].append(node.ms)
    latency = bars({k: sum(v)/len(v) for k, v in timings.items()})
    latency += listing([
        ("TTFT 평균 ms", f"{sum(e.ttft_ms for e in events)/n:.2f}" if n else "미검증"),
        ("전체 실행 평균 ms", f"{sum(e.total_ms for e in events)/n:.2f}" if n else "미검증"),
        ("실행 표본 수", n),
    ])
    return '<div class="grid">' + "".join(
        f'<section class="panel" data-panel="{key}"><h2>{title}</h2>{body}</section>'
        for key, title, body in (
            ("trace", "실행 궤적", trace), ("cost", "비용 통제", cost),
            ("guard", "환각 방어 · R37", guard), ("latency", "성능·레이턴시", latency))) + "</div>"


STYLE = """
:root{color-scheme:light dark;--bg:#f6f7fa;--panel:white;--ink:#182235;--line:#d7dfeb;--accent:#346ac4}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#111827;--panel:#1e293b;--ink:#eef2ff;--line:#475569;--accent:#8ab4ff}}
:root[data-theme=dark]{--bg:#111827;--panel:#1e293b;--ink:#eef2ff;--line:#475569;--accent:#8ab4ff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.6 system-ui}
main{max-width:1200px;margin:auto;padding:16px;overflow-wrap:anywhere}h1{font-size:1.6rem}h2{font-size:1.2rem}h3{font-size:1rem}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.panel{min-width:0;border:1px solid var(--line);border-radius:12px;background:var(--panel);padding:16px}
nav{display:flex;flex-wrap:wrap;gap:8px;margin:16px 0}button,select{font:inherit;color:var(--ink);background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:6px;max-width:100%;white-space:normal;overflow-wrap:anywhere}
button[aria-selected=true]{border:2px solid var(--accent)}ul{padding-left:20px}svg{display:block;width:100%;height:12px;margin:4px 0 12px}rect{fill:var(--accent)}[hidden]{display:none!important}
@media(max-width:640px){.grid{grid-template-columns:minmax(0,1fr)}}
"""


def render(events, *, gold=None, injection_run_ids=()) -> str:
    events = [e if isinstance(e, RunEvent) else RunEvent(**e) for e in events]
    if len({e.run_id for e in events}) != len(events):
        raise ValueError("duplicate run_id")
    injections = tuple(injection_run_ids)
    domains = sorted({e.domain for e in events})
    tabs, bodies = [], []
    for i, domain in enumerate(domains):
        tabs.append(f'<button role="tab" id="tab-{i}" aria-controls="domain-{i}" '
                    f'aria-selected="{str(i == 0).lower()}">{escape(domain)}</button>')
        body = f'<div role="tabpanel" id="domain-{i}" aria-labelledby="tab-{i}"' + (" hidden" if i else "") + ">"
        for estimated in (True, False):
            cohort = [e for e in events if e.domain == domain and e.estimated == estimated]
            if cohort:
                label = "추정 계측 · 경로 시험 (estimated=true)" if estimated else "비추정 계측 (estimated=false; 실제 모델 품질 미검증)"
                body += f"<h2>{label} · n={len(cohort)}</h2>" + panels(cohort, gold=gold, injections=injections)
        bodies.append(body + "</div>")
    if not domains:
        bodies.append("<p>실행 기록 없음 · 미검증</p>" + panels([], gold=gold, injections=injections))
    return ('<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>계측 보드</title><style>' + STYLE + '</style></head><body><main>'
            '<h1>계측 보드 · 4패널</h1><label>테마 <select id="theme"><option value="auto">자동</option>'
            '<option value="light">밝게</option><option value="dark">어둡게</option></select></label>'
            '<p>원가는 이벤트 cost_krw 기준. 비율은 표본 수·Wilson 95% 구간 포함. 관측 0건은 보장이 아닙니다.</p>'
            '<nav role="tablist" aria-label="도메인">' + "".join(tabs) + '</nav>' + "".join(bodies) +
            '</main><script>'
            'document.getElementById("theme").onchange=e=>{document.documentElement.dataset.theme=e.target.value};'
            'document.querySelectorAll("[role=tab]").forEach(t=>{t.onclick=()=>{'
            'document.querySelectorAll("[role=tab]").forEach(b=>b.setAttribute("aria-selected",String(b===t)));'
            'document.querySelectorAll("[role=tabpanel]").forEach(p=>{p.hidden=p.id!==t.getAttribute("aria-controls")});'
            '}});</script></body></html>')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, default=ROOT / ".runs/events")
    parser.add_argument("--output", type=Path, default=ROOT / ".runs/metrics_board/index.html")
    parser.add_argument("--injection-run-id", action="append", default=[])
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / ".runs").resolve()):
        parser.error("output must be inside .runs/")
    html = render(load_events(args.events), injection_run_ids=args.injection_run_id)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    main()
