"""Add and resolve human predictions in the local append-only journal."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from rag_research_agent.rag.predictions import PredictionLog


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--path", default=".runs/predictions.jsonl")
    sub = ap.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add")
    add.add_argument("--statement", required=True)
    add.add_argument("--profile", required=True)
    add.add_argument("--evidence-ids", nargs="*", default=[])
    add.add_argument("--brief-path", required=True)
    add.add_argument("--due", required=True)
    add.add_argument("--confidence", type=float)
    add.add_argument("--tags", nargs="*", default=[])
    resolve = sub.add_parser("resolve")
    resolve.add_argument("id")
    resolve.add_argument("--outcome", required=True, choices=["hit", "miss", "partial", "void"])
    resolve.add_argument("--note", default="")
    resolve.add_argument("--resolved-at")
    listing = sub.add_parser("list")
    listing.add_argument("--open-only", action="store_true")
    sub.add_parser("summary")
    args = ap.parse_args(argv)
    log = PredictionLog(args.path)
    try:
        if args.command == "add":
            result = log.add(args.statement, args.profile, args.evidence_ids, args.brief_path, args.due, args.confidence, args.tags)
        elif args.command == "resolve":
            log.resolve(args.id, args.outcome, args.note, args.resolved_at)
            result = {"resolved": args.id}
        elif args.command == "list":
            result = log.list(args.open_only)
        else:
            result = log.summary()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError) as exc:
        print(f"입력 오류: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
