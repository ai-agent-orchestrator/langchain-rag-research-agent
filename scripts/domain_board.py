"""Render offline R21 histories as a self-contained, data-defined domain board."""
from __future__ import annotations

import argparse
from html import escape
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.domain_eval import load_pack, validate_metrics  # noqa: E402

MATURITY = "incubating"
PACKS = ROOT / "evals" / "domains"
OUT = ROOT / ".runs" / "domain_eval"

STYLE = """
:root{color-scheme:light dark;--bg:#fafaf7;--panel:#fff;--ink:#20252b;--line:#ccd1d6}
@media(prefers-color-scheme:dark){:root{--bg:#15191d;--panel:#20262c;--ink:#edf0f3;--line:#58616a}}
:root[data-theme=light]{color-scheme:light;--bg:#fafaf7;--panel:#fff;--ink:#20252b;--line:#ccd1d6}
:root[data-theme=dark]{color-scheme:dark;--bg:#15191d;--panel:#20262c;--ink:#edf0f3;--line:#58616a}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 system-ui}
main{max-width:1100px;margin:auto;padding:16px;overflow-wrap:anywhere}
section{margin:24px 0;padding:12px;background:var(--panel);border:1px solid var(--line);border-radius:8px;min-width:0}
h1{font-size:1.6rem}h2{font-size:1.3rem}h3{font-size:1.1rem}
table{width:100%;table-layout:fixed;border-collapse:collapse}th,td{padding:8px;text-align:left;border-bottom:1px solid var(--line);overflow-wrap:anywhere}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:.85rem}select{max-width:100%;font:inherit}
@media(max-width:650px){table,thead,tbody,tr,th,td{display:block;width:100%}thead{display:none}
tr{margin:12px 0;border:1px solid var(--line)}td::before{content:attr(data-label);display:block;font-weight:bold}}
"""


def text(value):
    return escape(str(value), quote=True)


def percent(value):
    return "미검증" if value is None else f"{value:.1%}"


def statistic(stats, safety):
    if not stats or stats.get("n") is None:
        return "미검증 (표본 수 없음)"
    if not stats["n"]:
        return "미검증 (n=0)"
    interval = stats.get("wilson95")
    ci = (f"{percent(interval[0])}–{percent(interval[1])}"
          if interval else "미검증")
    numerator = stats.get("errors" if safety else "ok", "미검증")
    result = f"{numerator}/{stats['n']} · {percent(stats.get('rate'))} · Wilson 95% [{ci}]"
    if safety:
        result = f"위반 {result} · Wilson 상한 {percent(stats.get('wilson95_upper'))}"
    return result


def table(headers, rows):
    head = "".join(f'<th scope="col">{text(h)}</th>' for h in headers)
    body = "".join("<tr>" + "".join(
        f'<td data-label="{text(h)}">{text(v)}</td>' for h, v in zip(headers, row)
    ) + "</tr>" for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def run_groups(runs):
    """Never mix synthetic path tests and model runs in the same table."""
    groups = {}
    for index, run in enumerate(runs, 1):
        groups.setdefault(run.get("evaluation", "미검증"), []).append((index, run))
    return groups


def load_domains(runs_root=OUT, packs=PACKS, domains=None):
    """Read existing histories and the same pack definitions used by R21."""
    runs_root = Path(runs_root)
    if domains is None:
        domains = sorted(p.parent.name for p in runs_root.glob("*/runs.jsonl"))
    result = {}
    for domain in domains:
        _, metrics = load_pack(domain, packs)  # Also validates domain before path use.
        history = runs_root / domain / "runs.jsonl"
        runs = [json.loads(line) for line in history.read_text(encoding="utf-8").splitlines()
                if line.strip()]
        if any(not isinstance(r, dict) or r.get("domain") != domain
               or r.get("schema_version") != 1 for r in runs):
            raise ValueError(f"{domain}: expected R21 schema_version=1 and matching domain")
        result[domain] = {"metrics": metrics, "runs": runs}
    return result


def render(domains):
    """Render all safety tables before any quality, cost, or history tables.

    Runs remain separate (including compare/confirm and evaluator provenance).
    Missing historical fields are never inferred or treated as zero.
    """
    for domain in domains.values():
        validate_metrics(domain["metrics"])
    parts = ['<!doctype html><html lang="ko"><head><meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width,initial-scale=1">',
             f"<title>Domain Evaluation Board</title><style>{STYLE}</style></head><body><main>",
             '<h1>도메인 평가 보드</h1><label>테마 <select id="theme" aria-label="테마">',
             '<option value="">자동</option><option value="light">밝게</option>',
             '<option value="dark">어둡게</option></select></label>',
             '<p>경로 시험과 실제 모델 결과는 실행 유형별로 해석하세요. '
             '0건은 안전 보장이 아닙니다. 품질 분모는 R21의 injection 제외 결과를 사용합니다.</p>']
    for safety, section_id, title in [(True, "safety", "안전 지표"),
                                      (False, "quality", "품질 지표")]:
        parts.append(f'<section id="{section_id}"><h2>{title}</h2>')
        for name, domain in domains.items():
            parts.append(f"<h3>{text(name)}</h3>")
            metrics = [m for m in domain["metrics"] if m["safety"] == safety]
            if not metrics:
                parts.append("<p>정의된 지표 없음 · 미검증</p>")
                continue
            key = "safety_metrics" if safety else "quality_metrics"
            for evaluation, runs in run_groups(domain["runs"]).items():
                parts.append(f"<h4>실행 유형: {text(evaluation)}</h4>")
                rows = [[index, run.get("split", "미검증"), evaluation,
                         *[statistic(run.get(key, {}).get(m["name"]), safety) for m in metrics]]
                        for index, run in runs]
                parts.append(table(["실행", "분할", "실행 유형", *[m["name"] for m in metrics]], rows))
            if not domain["runs"]:
                parts.append("<p>실행 기록 없음 · 미검증</p>")
        parts.append("</section>")
    parts.append('<section id="tokens"><h2>추정 토큰</h2>'
                 '<p>R21은 토큰을 기록하지 않습니다. 아래 값은 기록에 tokens_mean이 있을 때만 표시합니다.</p>')
    for name, domain in domains.items():
        for evaluation, runs in run_groups(domain["runs"]).items():
            parts.append(f"<h3>{text(name)} · {text(evaluation)}</h3>")
            rows = [[index, run.get("tokens_mean") if run.get("tokens_mean") is not None else "미검증"]
                    for index, run in runs]
            parts.append(table(["실행", "추정 토큰 / 문항"], rows))
    parts.append('</section><section id="history"><h2>실행 기록</h2>')
    for name, domain in domains.items():
        parts.append(f"<h3>{text(name)}</h3>")
        for index, run in enumerate(domain["runs"], 1):
            parts.append(f'<details><summary>#{index} · {text(run.get("at", "미검증"))} · '
                         f'{text(run.get("split", "미검증"))} · {text(run.get("evaluation", "미검증"))}'
                         f'</summary><pre>{text(json.dumps(run, ensure_ascii=False, indent=2))}</pre></details>')
    if not domains:
        parts.append("<p>실행 기록 없음 · 미검증</p>")
    parts.append('</section></main><script>document.getElementById("theme").addEventListener('
                 '"change",e=>{document.documentElement.dataset.theme=e.target.value});</script></body></html>')
    return "\n".join(parts)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", action="append", help="repeat to select domains; default: all histories")
    parser.add_argument("--packs", type=Path, default=PACKS)
    parser.add_argument("--runs-root", type=Path, default=OUT)
    parser.add_argument("--output", type=Path, default=OUT / "board.html")
    args = parser.parse_args(argv)
    try:
        target = args.output.resolve()
        if not target.is_relative_to((ROOT / ".runs").resolve()):
            raise ValueError("output must be inside .runs/")
        if target.suffix.lower() != ".html":
            raise ValueError("output must be an HTML file")
        html = render(load_domains(args.runs_root, args.packs, args.domain))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html, encoding="utf-8")
    except (ValueError, OSError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
