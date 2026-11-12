"""Offline, data-defined domain evaluation; no executable code is loaded from packs."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rag_research_agent.observe.gate_grid import wilson  # noqa: E402

MATURITY = "incubating"
PACKS = ROOT / "evals" / "domains"
OUT = ROOT / ".runs" / "domain_eval"


def field(record, path):
    """Resolve dictionary keys only; never evaluate expressions or attributes."""
    value = record
    for key in path.split("."):
        if not isinstance(value, dict) or key not in value:
            raise ValueError(f"missing target field: {path}")
        value = value[key]
    return value


def validate_metrics(metrics):
    if not isinstance(metrics, list) or not metrics:
        raise ValueError("empty metrics: metrics.json must define at least one metric")
    names = set()
    for metric in metrics:
        if not isinstance(metric, dict):
            raise ValueError("each metric must be an object")
        name = metric.get("name")
        if not isinstance(name, str) or not name or name in names:
            raise ValueError("metric names must be nonempty and unique")
        names.add(name)
        if metric.get("kind") not in {"contains", "forbidden", "count"}:
            raise ValueError(f"{name}: kind must be contains, forbidden or count")
        if not isinstance(metric.get("field"), str) or not metric["field"]:
            raise ValueError(f"{name}: target field required")
        if type(metric.get("safety")) is not bool:
            raise ValueError(f"{name}: safety must be a boolean")
        if metric.get("match", "all") not in {"all", "any"}:
            raise ValueError(f"{name}: match must be all or any")
        if metric["kind"] == "count":
            if type(metric.get("expected")) is not int or metric["expected"] < 0:
                raise ValueError(f"{name}: nonnegative expected count required")
        elif ("values" in metric) == ("values_field" in metric):
            raise ValueError(f"{name}: provide exactly one of values or values_field")
    return metrics


def research_pack(retrieval=False):
    """Register the existing research corpus without copying or modifying it."""
    data = json.loads((ROOT / "evals/research/cases.ko.json").read_text(encoding="utf-8"))
    labels = {}
    labels_path = ROOT / "evals/research/gold_sources.json"
    if retrieval and labels_path.exists():
        labels = json.loads(labels_path.read_text(encoding="utf-8"))
        if not isinstance(labels, dict) or set(labels) - {c["id"] for c in data["cases"]}:
            raise ValueError("gold_sources must map known research case IDs to source ID lists")
        for original in data["cases"]:
            if original["id"] not in labels:
                continue
            sources = labels[original["id"]]
            if (not isinstance(sources, list) or
                    any(not isinstance(s, str) or s not in original["docs"] for s in sources)):
                raise ValueError("gold_sources must contain source IDs from the case docs")
    cases = []
    for original in data["cases"]:
        case = dict(original)
        if retrieval and case["id"] in labels:
            case["gold_sources"] = labels[case["id"]]
        gold = case["gold"]
        case["expected"] = {
            "metrics": [[name.split()[-1], value] for name, value in gold["metrics"].items()],
            "causal": gold["causal"], "constraints": gold["constraints"],
            "balance": [gold["con"]] if gold["con"] else [],
        }
        cases.append(case)
    metrics = [{"name": name, "kind": "contains", "field": "body", "safety": False,
                "values_field": f"expected.{key}", "match": match}
               for name, key, match in (("metric_coverage", "metrics", "all"),
                                        ("causal_retention", "causal", "all"),
                                        ("constraint_retention", "constraints", "all"),
                                        ("balance", "balance", "any"))]
    metrics.append({"name": "unsupported_numbers", "kind": "count",
                    "field": "unsupported_numbers", "expected": 0, "safety": True})
    return cases, validate_metrics(metrics)


def load_pack(domain, packs=PACKS, retrieval=False):
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", domain):
        raise ValueError("domain must be a simple folder name")
    if domain == "research":
        return research_pack(retrieval=retrieval)
    folder = Path(packs) / domain
    data = json.loads((folder / "cases.json").read_text(encoding="utf-8"))
    cases = data.get("cases") if isinstance(data, dict) else data
    if not isinstance(cases, list) or not cases:
        raise ValueError(f"empty pack: {domain}: cases.json must contain at least one case")
    metrics = json.loads((folder / "metrics.json").read_text(encoding="utf-8"))
    return cases, validate_metrics(metrics)


def research_output(case, retrieval=False):
    # Lazy imports keep the generic evaluator independent of LangGraph/models/stores.
    from rag_research_agent.rag.research_graph import ResearchRunner, keyword_search

    search = keyword_search(case["docs"])
    ranked_ids = [sid for sid, _ in search(case["question"], 5)] if retrieval else None
    result = ResearchRunner(search).run(
        case["question"], tuple(case.get("checklist", ())))
    body = " ".join(s.text for s in result.draft.sentences if not s.note)
    number = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")
    def numbers(text):
        return {n.replace(",", "") for n in number.findall(text)}
    output = {"body": body, "unsupported_numbers": sorted(
        numbers(body) - numbers(" ".join(case["docs"].values())))}
    if retrieval:
        output["retrieved_ids"] = ranked_ids
    return output


def measure(metric, case, output):
    value = field(output, metric["field"])
    if metric["kind"] == "count":
        if not isinstance(value, (str, list)):
            raise ValueError("count target must be text or a list")
        count = len(value)
        return [count == metric["expected"]], count
    if not isinstance(value, str):
        raise ValueError("contains/forbidden target must be text")
    terms = field(case, metric["values_field"]) if "values_field" in metric else metric["values"]
    if not isinstance(terms, list):
        raise ValueError("metric values must be a list of strings or string groups")
    checks, occurrences = [], 0
    for term in terms:
        group = term if isinstance(term, list) else [term]
        if not group or any(not isinstance(t, str) or not t for t in group):
            raise ValueError("metric terms must be nonempty strings")
        hits = [t in value for t in group]
        hit = any(hits) if metric.get("match", "all") == "any" else all(hits)
        checks.append(not hit if metric["kind"] == "forbidden" else hit)
        occurrences += sum(value.count(t) for t in group)
    return checks, occurrences


def evaluate(cases, metrics, evaluator=None, split="compare", retrieval=False, judge=None):
    """evaluator(case) -> JSON field mapping; default scores case['output']."""
    validate_metrics(metrics)
    if split not in {"compare", "confirm"}:
        raise ValueError("split must be compare or confirm")
    if not cases:
        raise ValueError("empty pack: at least one case required")
    ids = [c.get("id") for c in cases]
    if any(not isinstance(i, str) or not i for i in ids) or len(ids) != len(set(ids)):
        raise ValueError("case IDs must be nonempty and unique")
    if any(c.get("split", "compare") not in {"compare", "confirm"} for c in cases):
        raise ValueError("case split must be compare or confirm")
    selected = [c for c in cases if c.get("split", "compare") == split]
    if not selected:
        raise ValueError(f"empty pack for split: {split}")
    buckets = {m["name"]: {"checks": [], "violations": [], "count": 0} for m in metrics}
    rows, retrieval_scores, verdicts, disagreements = [], [], [], []
    for case in selected:
        output = evaluator(case) if evaluator else field(case, "output")
        row = {"case": case["id"], "metrics": {}}
        if retrieval and case.get("gold_sources") and case.get("type") != "injection":
            from rag_research_agent.rag.eval_retrieval import score_retrieval

            score = score_retrieval(case["gold_sources"], field(output, "retrieved_ids"))
            row["retrieval"] = score
            retrieval_scores.append(score)
        for metric in metrics:
            if not metric["safety"] and case.get("type") == "injection":
                continue
            checks, count = measure(metric, case, output)
            bucket = buckets[metric["name"]]
            bucket["checks"].extend(checks)
            if checks:
                bucket["violations"].append(not all(checks))
            bucket["count"] += count
            row["metrics"][metric["name"]] = {"ok": sum(checks), "n": len(checks), "count": count}
        if judge is not None and "reference" in case and case.get("type") != "injection":
            from rag_research_agent.rag.judge import JudgeVerdict

            reference = case["reference"]
            if not isinstance(reference, str) or not reference.strip():
                raise ValueError("reference must be nonempty text")
            answer = field(output, "answer" if "answer" in output else "body")
            question = field(case, "question")
            if not isinstance(answer, str) or not isinstance(question, str):
                raise ValueError("judge question and answer must be text")
            verdict = JudgeVerdict.model_validate(judge.judge(question, answer, reference))
            row["judge"] = verdict.model_dump()
            verdicts.append(verdict)
            mismatches = {name: stats["ok"] == stats["n"]
                          for name, stats in row["metrics"].items()
                          if stats["n"] and (stats["ok"] == stats["n"]) != verdict.correct}
            if mismatches:
                disagreements.append({"case": case["id"], "judge_correct": verdict.correct,
                                      "rule_metrics": mismatches})
        rows.append(row)
    quality, safety = {}, {}
    for metric in metrics:
        bucket = buckets[metric["name"]]
        if metric["safety"]:
            stats = wilson(sum(bucket["violations"]), len(bucket["violations"]))
            stats["wilson95_upper"] = stats["wilson95"][1] if stats["n"] else None
            stats["count"] = bucket["count"]
            safety[metric["name"]] = stats
        else:
            checks = bucket["checks"]
            stats = wilson(sum(checks), len(checks))
            stats["ok"] = stats.pop("errors")
            quality[metric["name"]] = stats
    rates = [s["rate"] for s in quality.values() if s["n"]]
    result = {"split": split, "n_cases": len(selected), "quality_metrics": quality,
            "quality_mean": sum(rates) / len(rates) if rates else None,
            "safety_metrics": safety, "cases": rows}
    if retrieval:
        from rag_research_agent.rag.eval_retrieval import aggregate_retrieval

        result["retrieval"] = aggregate_retrieval(retrieval_scores)
    if judge is not None:
        accuracy = wilson(sum(v.correct for v in verdicts), len(verdicts))
        accuracy["ok"] = accuracy.pop("errors")
        result["judge"] = {"n": len(verdicts),
                           "mean_score": sum(v.score for v in verdicts) / len(verdicts) if verdicts else None,
                           "accuracy": accuracy}
        result["judge_disagreements"] = disagreements
    return result


def run(domain, packs=PACKS, split="compare", evaluator=None, retrieval=False, judge="none"):
    if judge not in {"none", "fake"}:
        raise ValueError("judge must be none or fake")
    selected_judge = None
    if judge == "fake":
        from rag_research_agent.rag.judge import FakeJudge

        selected_judge = FakeJudge()
    cases, metrics = load_pack(domain, packs, retrieval=retrieval)
    if split != "compare":
        raise ValueError("CLI supports compare only; confirm requires a separately selected configuration")
    if evaluator is None and domain == "research":
        def selected_evaluator(case):
            return research_output(case, retrieval=retrieval and bool(case.get("gold_sources"))
                                   and case.get("type") != "injection")
    else:
        selected_evaluator = evaluator
    result = evaluate(cases, metrics, selected_evaluator, split, retrieval=retrieval, judge=selected_judge)
    if selected_judge is not None:
        result["judge"]["evaluation"] = "fake_rule_path_test"
    result.update(domain=domain, schema_version=1,
                  evaluation=("injected_evaluator" if evaluator is not None else
                              "synthetic_rule_path_test" if domain == "research" else "provided_outputs"),
                  at=dt.datetime.now(dt.timezone.utc).isoformat())
    target = OUT / domain / "runs.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(result, ensure_ascii=False, allow_nan=False) + "\n")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", required=True)
    parser.add_argument("--packs", type=Path, default=PACKS)
    parser.add_argument("--retrieval", action="store_true", help="score labelled retrieval rankings")
    parser.add_argument("--judge", choices=("none", "fake"), default="none",
                        help="optional reference-answer path test judge")
    args = parser.parse_args(argv)
    try:
        result = run(args.domain, args.packs, retrieval=args.retrieval, judge=args.judge)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    summary = {"domain": args.domain, "n_cases": result["n_cases"],
               "quality_mean": result["quality_mean"], "safety_metrics": result["safety_metrics"]}
    if args.retrieval:
        summary["retrieval"] = result["retrieval"]
    if args.judge != "none":
        summary["judge"] = result["judge"]
        summary["judge_disagreements"] = result["judge_disagreements"]
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
