"""Offline board demo using real research runners and explicit rule/fake graders."""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
from time import perf_counter
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from rag_research_agent.guard.legal_filter import LegalFilter
from rag_research_agent.rag.eval_retrieval import score_retrieval
from rag_research_agent.rag.graders import FakeLLMGrader, GroundedGrade, RelevanceGrade, RuleGrader
from rag_research_agent.rag.judge import FakeJudge
from rag_research_agent.rag.metric_targets import check_targets, load_targets
from rag_research_agent.rag.research_graph import ResearchConfig, keyword_search, run_baseline
from rag_research_agent.rag.run_trace import JsonlSink, TraceCollector, TraceResearchRunner, event_from_result
from scripts import groundedness_eval, metrics_board, research_eval

MATURITY = "incubating"
CONFIGS = ("baseline_single", "graph_basic", "graph_full", "graph_full + FakeLLMGrader")


def fake_grader():
    # Fixed approval, independent of gold. Finite queues intentionally fail on exhaustion.
    return FakeLLMGrader(
        relevance=[RelevanceGrade(relevant=True, reason="FIXED_APPROVAL_PATH_TEST") for _ in range(2048)],
        grounded=[GroundedGrade(grounded=True, reason="FIXED_APPROVAL_PATH_TEST", unsupported=[])
                  for _ in range(256)])


def execute_case(case, domain, name, k, dataset):
    """Execute actual graph/baseline; return telemetry plus gold-scored sidecar."""
    search = keyword_search(case["docs"])
    metadata = {"config": f"{name};k={k}", "dataset": dataset,
                "track": "fast" if name == CONFIGS[0] else "deep"}
    if name == CONFIGS[0]:
        started = perf_counter()
        result = run_baseline(search, case["question"], k=k,
                              corpus_text=" ".join(case["docs"].values()))
        event = event_from_result(result, domain,
                                  {**metadata, "total_ms": (perf_counter() - started) * 1000})
    else:
        cfg = ResearchConfig(name=name, k=k, stance_split=name != "graph_basic",
                             gap_loop=name != "graph_basic", rewrite_loop=name != "graph_basic",
                             grader=(fake_grader() if name == CONFIGS[3] else
                                     RuleGrader() if name == "graph_full" else None))
        collector = TraceCollector(domain=domain, config=metadata, sink=lambda event: None)
        result = TraceResearchRunner(search, cfg, trace=collector).run(
            case["question"], tuple(case.get("checklist", ())))
        event = collector.last_event
    if domain == "legal":
        verifier = LegalFilter()
        branch = verifier.check_input(case["question"]).branch
        verdict = verifier.verify(result.draft.body(), tuple(s.text for s in result.sources), branch)
        codes = [issue.code for issue in verdict.issues]
        required = case["gold"]["required_statutes"]
        quality = [citation in result.draft.body() for citation in required]
        reference = case["gold"]["answer"]
        gold_sources = [sid for sid, text in case["docs"].items()
                        if any(citation in text for citation in required)]
    else:
        codes = list(result.verify_codes)
        scored = research_eval.score(case, result, " ".join(case["docs"].values()))
        quality = [*scored["metric_hits"].values(), *scored["causal"],
                   *scored["constraints"], *scored["balance"]]
        reference = " ".join(case["gold"]["metrics"]) + " " + " ".join(case["gold"]["con"])
        gold_sources = case.get("gold_sources", case["gold"].get("gold_sources"))
    # Explicit fictional shadow rates: 100 KRW/M input, 200 KRW/M output.
    decisions = [line.split(":", 3)[2] for line in result.log if line.startswith("RELEVANCE:")]
    docs_in, docs_kept = len(decisions), decisions.count("KEEP")
    event = replace(event, grade={"docs_in": docs_in, "docs_kept": docs_kept,
                                  "relevance_drop_rate": (docs_in-docs_kept)/docs_in if docs_in else 0},
                    cost_krw=(event.tokens["in"] * 100 + event.tokens["out"] * 200) / 1_000_000,
                    guard=tuple({"gate": "filter", "code": code, "reason": code, "span": ""}
                                for code in codes))
    ranking = [sid for sid, _ in search(case["question"], k)]
    retrieval = score_retrieval(gold_sources, ranking, ks=(k,))
    judge = FakeJudge().judge(case["question"], result.draft.body(), reference)
    return event, {"run_id": event.run_id, "case": case["id"], "domain": domain,
                   "config": name, "k": k, "quality": quality,
                   "hit": retrieval[f"hit@{k}"] if retrieval else None,
                   "judge_score": judge.score, "judge_correct": judge.correct,
                   "legal_filter_ok": not codes if domain == "legal" else None}


def run_demo(*, out, cases, legal_cases, ks=(1, 3), configs=CONFIGS):
    out = Path(out).resolve()
    if not out.is_relative_to((ROOT / ".runs").resolve()):
        raise ValueError("output must be inside .runs/")
    if not ks or len(set(ks)) != len(ks) or any(type(k) is not int or k < 1 for k in ks):
        raise ValueError("k must contain unique positive integers")
    if not configs or len(set(configs)) != len(configs) or any(c not in CONFIGS for c in configs):
        raise ValueError("unknown or duplicate config")
    events, rows, grounding = [], [], {}
    packs = [("research", Path(cases)), ("legal", Path(legal_cases))]
    sink = JsonlSink(ROOT / ".runs/events")
    for domain, path in packs:
        data = json.loads(path.read_text(encoding="utf-8"))
        selected = [c for c in data["cases"] if c["split"] == "compare"]
        for name in configs:
            if domain == "research":
                ground_cases = json.loads(groundedness_eval.CASES.read_text(encoding="utf-8"))
                grounding[name] = groundedness_eval.evaluate(
                    ground_cases, fake_grader() if name == CONFIGS[3] else RuleGrader())["rows"]
            for k in ks:
                for case in selected:
                    event, row = execute_case(case, domain, name, k, path.name)
                    sink(event)
                    events.append(event)
                    rows.append(row)
    report = {"rows": rows, "grounding": grounding,
              "target_warnings": check_targets(events, load_targets(ROOT / "evals/metric_targets.json"))}
    out.parent.mkdir(parents=True, exist_ok=True)
    sidecar = out.with_name(out.stem + "-" + uuid4().hex + ".json")
    sidecar.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    out.write_text(metrics_board.render(events, comparison=report), encoding="utf-8")
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / ".runs/board_demo/index.html")
    parser.add_argument("--cases", type=Path, default=research_eval.CASES)
    parser.add_argument("--legal-cases", type=Path, default=ROOT / "evals/domains/legal/cases.json")
    parser.add_argument("--k", type=int, nargs="+", default=[1, 3])
    parser.add_argument("--configs", nargs="+", choices=CONFIGS, default=list(CONFIGS))
    args = parser.parse_args(argv)
    try:
        output = run_demo(out=args.out, cases=args.cases, legal_cases=args.legal_cases,
                          ks=tuple(args.k), configs=tuple(args.configs))
    except ValueError as exc:
        parser.error(str(exc))
    print(output)
    return output


if __name__ == "__main__":
    main()
