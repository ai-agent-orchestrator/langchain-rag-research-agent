"""Research-graph experiment: run configs over synthetic cases, append results, rebuild the board.

    python scripts/research_eval.py                    # compare split, all configs
    python scripts/research_eval.py --cases evals/research/cases_v2.ko.json
    python scripts/research_eval.py --split confirm --configs graph_full   # confirm the chosen config once
    python scripts/research_eval.py --note "k=3 시험"   # label this run on the board

Results: .runs/research_eval/runs.jsonl (one line per run, history kept) and .runs/research_eval/board.html.
Synthetic data, rule-based nodes, no model calls: tokens are *estimated* (shadow) model tokens.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rag_research_agent.core.research import NO_COUNTER_EVIDENCE  # noqa: E402
from rag_research_agent.observe.gate_grid import wilson  # noqa: E402
from rag_research_agent.rag.research_graph import (  # noqa: E402
    ResearchConfig, ResearchRunner, keyword_search, run_baseline,
)

CASES = ROOT / "evals" / "research" / "cases.ko.json"
OUT = ROOT / ".runs" / "research_eval"
CONFIGS = {
    "baseline_single": None,   # one search, first sentences; reads the whole corpus as one model call would
    "graph_basic": ResearchConfig(name="graph_basic", stance_split=False, gap_loop=False, rewrite_loop=False),
    "graph_split": ResearchConfig(name="graph_split", gap_loop=False, rewrite_loop=False),
    "graph_full": ResearchConfig(name="graph_full"),
    "graph_full_auto": ResearchConfig(name="graph_full_auto", use_checklist=False),
}
_NUM = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")


def numbers(text):
    return {n.replace(",", "") for n in _NUM.findall(text)}


def score(case, result, corpus_text):
    gold = case["gold"]
    sentences = [s.text for s in result.draft.sentences if not s.note]
    body = " ".join(sentences)
    metric_hits = {}
    for name, value in gold["metrics"].items():
        key = name.split()[-1]
        metric_hits[name] = any(key in s and value in numbers(s) for s in sentences)
    causal = [all(p in body for p in group) for group in gold["causal"]]
    constraints = [p in body for p in gold["constraints"]]
    if gold["con"]:
        balance = [any(p in body for p in gold["con"])]
    else:
        balance = []
    noted = any(s.note and s.text == NO_COUNTER_EVIDENCE for s in result.draft.sentences)
    unsupported = sorted(numbers(body) - numbers(corpus_text))
    tokens_in = sum(t for _, k, t in result.cost if k == "model_in")
    tokens_out = sum(t for _, k, t in result.cost if k == "model_out")
    return {
        "case": case["id"], "metric_hits": metric_hits, "causal": causal, "constraints": constraints,
        "balance": balance, "no_con_case": not gold["con"], "no_con_noted": noted,
        "unsupported_numbers": unsupported, "tokens_in": tokens_in, "tokens_out": tokens_out,
        "gap_searches": result.path.count("retrieve_gap"), "rewrites": result.path.count("rewrite"),
        "verify_codes": list(result.verify_codes), "stopped": result.stopped, "path_len": len(result.path),
        "report": result.report, "log": list(result.log),
    }


def aggregate(rows):
    def rate(items):
        n = len(items)
        ok = sum(1 for x in items if x)
        w = wilson(n - ok, n) if n else {"wilson95": None}
        lo_hi = w["wilson95"]
        return {"ok": ok, "n": n, "rate": ok / n if n else None,
                "ci": [1 - lo_hi[1], 1 - lo_hi[0]] if lo_hi else None}
    metric = rate([v for r in rows for v in r["metric_hits"].values()])
    causal = rate([v for r in rows for v in r["causal"]])
    constraint = rate([v for r in rows for v in r["constraints"]])
    balance = rate([v for r in rows for v in r["balance"]])
    parts = [x["rate"] for x in (metric, causal, constraint, balance) if x["rate"] is not None]
    return {
        "metric_coverage": metric, "causal_retention": causal, "constraint_retention": constraint,
        "balance": balance, "quality": sum(parts) / len(parts) if parts else None,
        "unsupported_numbers": sum(len(r["unsupported_numbers"]) for r in rows),
        "no_con_noted": sum(r["no_con_noted"] for r in rows if r["no_con_case"]),
        "no_con_cases": sum(r["no_con_case"] for r in rows),
        "tokens_mean": sum(r["tokens_in"] + r["tokens_out"] for r in rows) / max(1, len(rows)),
        "loops_mean": sum(r["gap_searches"] + r["rewrites"] for r in rows) / max(1, len(rows)),
        "verify_pass": sum(1 for r in rows if not r["verify_codes"]), "n_cases": len(rows),
    }


BACKGROUND = ("{tag} 관련 배경 자료 {i}번이다. 시장 환경은 일반적으로 다양한 요인의 영향을 받으며 여러 가지 측면을 종합적으로 "
              "살펴보는 것이 중요하다. 전문가들은 장기적인 관점에서 접근할 필요가 있다고 말한다. 과거 사례를 돌아보면 비슷한 흐름이 "
              "반복되기도 했고 그렇지 않기도 했다. 관련 기관과 업계, 학계의 다양한 의견을 함께 듣는 것도 필요하다. 이러한 흐름은 "
              "앞으로도 계속될 가능성이 있으며 지속적인 관찰이 필요하다. 결론적으로 말하면 균형 잡힌 시각을 유지하는 것이 중요하다.")


def padded(case, extra):
    tag = case["question"].split()[0]
    docs = dict(case["docs"])
    for i in range(1, extra + 1):
        docs[f"pad{i:03d}"] = BACKGROUND.format(tag=tag, i=i)
    return docs


def sweep(cases, sizes):
    """Cost crossover: a single call reads the whole corpus; the graph reads only what it retrieved."""
    out = []
    for extra in sizes:
        point = {"extra_docs": extra}
        for name in ("baseline_single", "graph_full"):
            rows = []
            for case in cases:
                corpus = padded(case, extra)
                text = " ".join(corpus.values())
                search = keyword_search(corpus)
                result = (run_baseline(search, case["question"], corpus_text=text) if name == "baseline_single"
                          else ResearchRunner(search, CONFIGS[name]).run(case["question"], tuple(case.get("checklist", ()))))
                rows.append(score(case, result, text))
            s = aggregate(rows)
            point[name] = {"tokens_mean": s["tokens_mean"], "quality": s["quality"], "loops_mean": s["loops_mean"],
                           "corpus_tokens": sum(len(" ".join(padded(c, extra).values())) // 2 for c in cases) / len(cases)}
        out.append(point)
    return out


def git_sha():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    except OSError:
        return ""


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", type=Path, default=CASES, help="question JSON file (default: %(default)s)")
    ap.add_argument("--split", default="compare", choices=["compare", "confirm", "all"])
    ap.add_argument("--configs", default=",".join(CONFIGS))
    ap.add_argument("--k", type=int, default=None, help="override passages per branch for graph configs")
    ap.add_argument("--note", default="")
    ap.add_argument("--sweep", default="0,10,30,60",
                    help="extra background documents per case for the cost sweep ('' to skip)")
    a = ap.parse_args(argv)
    try:
        cases_bytes = a.cases.read_bytes()
    except OSError as exc:
        ap.error(f"cannot read cases file '{a.cases}': {exc.strerror}")
    data = json.loads(cases_bytes.decode("utf-8"))
    cases = [c for c in data["cases"] if a.split == "all" or c["split"] == a.split]
    run = {"at": dt.datetime.now().isoformat(timespec="seconds"), "sha": git_sha(), "split": a.split,
           "note": a.note, "dataset": data["version"], "configs": {},
           "cases_file": a.cases.name, "cases_sha256": hashlib.sha256(cases_bytes).hexdigest()}
    for name in [c.strip() for c in a.configs.split(",") if c.strip()]:
        cfg = CONFIGS[name]
        if cfg is not None and a.k:
            cfg = replace(cfg, k=a.k)
        rows = []
        for case in cases:
            corpus = case["docs"]
            corpus_text = " ".join(corpus.values())
            search = keyword_search(corpus)
            if cfg is None:
                result = run_baseline(search, case["question"], corpus_text=corpus_text)
            else:
                result = ResearchRunner(search, cfg).run(case["question"], tuple(case.get("checklist", ())))
            rows.append(score(case, result, corpus_text))
        run["configs"][name] = {"config": asdict(cfg) if cfg else {"name": name}, "summary": aggregate(rows), "cases": rows}
    run["sweep"] = sweep(cases, [int(x) for x in a.sweep.split(",") if x.strip()]) if a.sweep else []
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "runs.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(run, ensure_ascii=False) + "\n")
    runs = [json.loads(l) for l in (OUT / "runs.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    from research_board import render  # noqa: E402  (scripts/ is on sys.path when run as a script)
    (OUT / "board.html").write_text(render(runs), encoding="utf-8")
    for name, c in run["configs"].items():
        s = c["summary"]
        print(f"{name:16s} quality={s['quality']:.2f} metric={s['metric_coverage']['ok']}/{s['metric_coverage']['n']} "
              f"causal={s['causal_retention']['ok']}/{s['causal_retention']['n']} constraint={s['constraint_retention']['ok']}/{s['constraint_retention']['n']} "
              f"balance={s['balance']['ok']}/{s['balance']['n']} tokens={s['tokens_mean']:.0f} loops={s['loops_mean']:.1f}")
    print(f"board: {OUT / 'board.html'}")


if __name__ == "__main__":
    main()
