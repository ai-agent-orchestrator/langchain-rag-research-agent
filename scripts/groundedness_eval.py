"""Offline standalone grounding evaluation; no graph, provider or model is created.

python scripts/groundedness_eval.py --grader rule
python scripts/groundedness_eval.py --grader fake  # fixed approval, path test only
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

MATURITY = "incubating"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rag_research_agent.core.research import Claim, Draft, ReportSentence, ResearchPlan
from rag_research_agent.guard.research_filter import verify_report
from rag_research_agent.observe.gate_grid import wilson
from rag_research_agent.rag.graders import FakeLLMGrader, GroundedGrade, Grader, RuleGrader

CASES = ROOT / "evals/groundedness/cases.ko.json"
OUT = ROOT / ".runs/groundedness/runs.jsonl"
FAULTS = {"none", "invented_number", "altered_number", "invented_statute",
          "causal_assertion", "one_sided", "uncited"}


def validate_cases(cases):
    """Reject malformed labels/citations before judging any cases."""
    if not isinstance(cases, list):
        raise ValueError("cases must be a list")
    ids = set()
    for case in cases:
        if not isinstance(case.get("id"), str) or not case["id"] or case["id"] in ids:
            raise ValueError("unique nonempty case IDs required")
        ids.add(case["id"])
        if case.get("expected") not in {"pass", "block"} or case.get("fault_type") not in FAULTS:
            raise ValueError("invalid expected/fault_type")
        if (case["expected"] == "pass") != (case["fault_type"] == "none"):
            raise ValueError("normal cases must pass; planted faults must block")
        evidence, answer = case.get("evidence"), case.get("answer")
        if not isinstance(evidence, list) or not isinstance(answer, list) or not answer:
            raise ValueError("evidence and nonempty answer lists required")
        claim_ids = set()
        for item in evidence:
            if not isinstance(item.get("id"), str) or not item["id"] or item["id"] in claim_ids:
                raise ValueError("unique nonempty evidence IDs required")
            claim_ids.add(item["id"])
            if not isinstance(item.get("text"), str) or not item["text"].strip():
                raise ValueError("nonempty evidence text required")
            if item.get("stance", "neutral") not in {"neutral", "pro", "con"}:
                raise ValueError("invalid stance")
            if item.get("kind", "fact") not in {"fact", "claim", "causal", "constraint"}:
                raise ValueError("invalid kind")
        for item in answer:
            if not isinstance(item.get("text"), str) or not item["text"].strip():
                raise ValueError("nonempty answer text required")
            if not isinstance(item.get("claim_ids"), list) or any(
                not isinstance(i, str) for i in item["claim_ids"]
            ):
                raise ValueError("claim_ids must be a list of strings")
    return cases


def evaluate(cases, grader: Grader):
    """Always apply the real report verifier, then the injected R42 grader.

    Labels are used only after both decisions. Explicit sentence citations avoid
    inventing attribution from the answer, and evidence spans cover full paragraphs.
    """
    validate_cases(cases)
    rows = []
    for case in cases:
        claims = [Claim(e["id"], e["id"], 0, len(e["text"]), e["text"],
                        stance=e.get("stance", "neutral"), kind=e.get("kind", "fact"))
                  for e in case["evidence"]]
        draft = Draft(tuple(ReportSentence(s["text"], tuple(s["claim_ids"]))
                            for s in case["answer"]))
        codes = list(verify_report(draft, ResearchPlan(()), claims, [],
                                   check_claim_alignment=True))
        grade = grader.grade_grounded(draft.body(), tuple(c.text for c in claims))
        if not grade.grounded:
            codes.append("UNGROUNDED")
        rows.append({"id": case["id"], "expected": case["expected"],
                     "fault_type": case["fault_type"], "blocked": bool(codes),
                     "codes": codes, "grade": grade.model_dump(),
                     "end_type": "give_up" if codes else "END"})
    return {"metrics": aggregate(rows), "rows": rows}


def aggregate(rows):
    def rate(items):
        result = wilson(sum(r["blocked"] for r in items), len(items))
        # The numerator is a detection (or false block), not always an error.
        result["count"] = result.pop("errors")
        return result

    faulty = [r for r in rows if r["expected"] == "block"]
    return {"detection": rate(faulty),
            "overblocking": rate([r for r in rows if r["expected"] == "pass"]),
            "by_fault_type": {kind: rate([r for r in faulty if r["fault_type"] == kind])
                              for kind in sorted(FAULTS - {"none"})}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=CASES)
    parser.add_argument("--grader", choices=("rule", "fake"), default="rule")
    args = parser.parse_args(argv)
    raw = args.cases.read_bytes()
    cases = validate_cases(json.loads(raw))
    # Fixed independent approval isolates the verifier + slot plumbing. Never gold-derived.
    grader = RuleGrader() if args.grader == "rule" else FakeLLMGrader(grounded=[
        GroundedGrade(grounded=True, reason="FIXED_APPROVAL_PATH_TEST", unsupported=[])
        for _ in cases
    ])
    result = evaluate(cases, grader)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                         text=True, check=True).stdout.strip()
    record = {"run_id": str(uuid4()), "timestamp": datetime.now(timezone.utc).isoformat(),
              "sha": sha, "domain": "research", "config": "standalone_groundedness",
              "dataset": args.cases.name, "cases_sha256": hashlib.sha256(raw).hexdigest(),
              "grader": args.grader, "evaluation_kind": "rule_synthetic" if args.grader == "rule"
              else "fake_path_test", "split": "compare", "path": ["verify", "grade_grounded"],
              "graph_executed": False, "model_calls": 0, **result}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(json.dumps({"grader": args.grader, "evaluation_kind": record["evaluation_kind"],
                      **result["metrics"]}, ensure_ascii=False, indent=2))
    return record


if __name__ == "__main__":
    main()
