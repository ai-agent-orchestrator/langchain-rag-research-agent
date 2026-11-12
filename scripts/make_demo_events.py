"""Generate deterministic synthetic RunEvents, without running a graph or model.

Usage: python scripts/make_demo_events.py --seed 42 --per-domain 25
Output: .runs/events/demo-<seed-label>/events.jsonl and summary.json.
All counts, timings, prices and guard findings are invented demo observations.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from math import sqrt
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rag_research_agent.core.run_events import NodeEvent, RunEvent, cost_krw  # noqa: E402

MATURITY = "incubating"
DOMAINS = ("research", "legal", "medical", "life")
# Explicitly fictional KRW/million-token rates, not current market prices.
DEMO_PRICING = {"demo-slm": {"in": 100, "out": 200},
                "demo-flagship": {"in": 1000, "out": 2000}}


def _label(text: str) -> str:
    # Letter-only identifiers avoid accidentally resembling personal identifiers.
    return sha256(text.encode("utf-8")).hexdigest().translate(str.maketrans("0123456789", "ghijklmnop"))


def generate_events(seed: int = 42, per_domain: int = 25) -> list[RunEvent]:
    """Return exactly per_domain real RunEvents for each of the four domains."""
    if type(seed) is not int:
        raise ValueError("seed must be an integer")
    if type(per_domain) is not int or per_domain < 1:
        raise ValueError("per_domain must be a positive integer")
    rng = random.Random(seed)
    events = []
    for domain in DOMAINS:
        for index in range(per_domain):
            track = "fast" if rng.random() < .6 else "deep"
            loops = {"rewrite": 0, "gap": 0, "verify": 0}
            path = ["retrieve", "grade"]
            if track == "deep":
                loops = {"rewrite": rng.randint(0, 2), "gap": rng.randint(0, 1),
                         "verify": rng.randint(0, 1)}
                for _ in range(loops["gap"]):
                    path.extend(("retrieve_gap", "grade"))
                for _ in range(loops["rewrite"]):
                    path.extend(("rewrite", "retrieve", "grade"))
            end_type = rng.choices(("END", "give_up", "cutoff"), weights=(8, 1, 1))[0]
            if end_type == "END":
                path.append("generate")
                for _ in range(loops["verify"]):
                    path.extend(("verify", "write"))
            else:
                # These demo runs stop before generation, so there is no draft to verify.
                loops["verify"] = 0
            nodes = []
            usage = {model: {"in": 0, "out": 0} for model in DEMO_PRICING}
            calls = {"slm": 0, "flagship": 0}
            for name in path:
                model = ("demo-slm" if name in ("grade", "verify") else
                         "demo-flagship" if name in ("generate", "write") else None)
                incoming = rng.randint(80, 400) if model else 0
                outgoing = rng.randint(10, 90) if model else 0
                nodes.append(NodeEvent(name, rng.randint(20, 250), incoming, outgoing, model, True))
                if model:
                    usage[model]["in"] += incoming
                    usage[model]["out"] += outgoing
                    calls["slm" if model == "demo-slm" else "flagship"] += 1
            docs_in = rng.randint(4, 12)
            docs_kept = rng.randint(0, docs_in)
            guard = ()
            if end_type != "END" or sum(loops.values()):
                guard = ({"gate": "grounded", "code": "UNSUPPORTED_NUMBER",
                          "reason": "합성 예시: 가상 지표 근거 불일치", "span": ""},)
            total_ms = sum(node.ms for node in nodes)
            # Demo convention: the first token arrives halfway through the first
            # generation node. No-generation runs use total_ms as a sentinel.
            ttft_ms = total_ms
            elapsed_ms = 0
            for node in nodes:
                if node.model == "demo-flagship":
                    ttft_ms = elapsed_ms + node.ms / 2
                    break
                elapsed_ms += node.ms
            events.append(RunEvent(
                run_id="demo-" + _label(f"{seed}:{domain}:{index}"), domain=domain,
                track=track, config="demo_fast" if track == "fast" else "demo_deep",
                dataset="synthetic-demo-v1", sha="demo-unversioned", path=tuple(path),
                end_type=end_type, loops=loops, calls=calls,
                tokens={direction: sum(v[direction] for v in usage.values()) for direction in ("in", "out")},
                cost_krw=cost_krw(usage, DEMO_PRICING),
                ttft_ms=ttft_ms,
                total_ms=total_ms,
                grade={"docs_in": docs_in, "docs_kept": docs_kept,
                       "relevance_drop_rate": (docs_in - docs_kept) / docs_in},
                guard=guard, nodes=tuple(nodes), estimated=True,
            ))
    return events


def _ratio(count: int, n: int) -> dict:
    if not n:
        return {"count": count, "n": 0, "ratio": None, "wilson95": None}
    p, z = count / n, 1.959963984540054
    denominator = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denominator
    radius = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return {"count": count, "n": n, "ratio": p,
            "wilson95": [max(0, center - radius), min(1, center + radius)]}


def _summary(events: list[RunEvent]) -> dict:
    n = len(events)
    return {"n": n,
            "tracks": {track: _ratio(sum(e.track == track for e in events), n)
                       for track in ("fast", "deep")},
            "mean_cost_krw": sum(e.cost_krw for e in events) / n if n else None,
            "mean_loops": {key: sum(e.loops[key] for e in events) / n if n else None
                           for key in ("rewrite", "gap", "verify")},
            "mean_total_loops": sum(sum(e.loops.values()) for e in events) / n if n else None}


def summarize_events(events) -> dict:
    """Routing counts/Wilson intervals and cost/loop means; separate estimation cohorts.

    Empty means/ratios are None (unverified), never a zero-run guarantee.
    This is routing telemetry, not retrieval quality or a quality evaluation.
    """
    events = list(events)
    result = {}
    for estimated, label in ((True, "estimated"), (False, "non_estimated")):
        cohort = [e for e in events if e.estimated == estimated]
        result[label] = {**_summary(cohort), "domains": {
            domain: _summary([e for e in cohort if e.domain == domain])
            for domain in sorted(set(DOMAINS) | {e.domain for e in cohort})}}
    return result


def write_events(events, directory: Path) -> Path:
    """Write a batch inside .runs/events; reruns replace only that batch's files."""
    directory = Path(directory).resolve()
    base = (ROOT / ".runs/events").resolve()
    if directory == base or not directory.is_relative_to(base):
        raise ValueError("output must be inside .runs/events/")
    events = list(events)
    payload = "".join(e.to_json(dumps=json.dumps) + "\n" for e in events)
    summary = json.dumps(summarize_events(events), ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    directory.mkdir(parents=True, exist_ok=True)
    output = directory / "events.jsonl"
    output.write_text(payload, encoding="utf-8", newline="\n")
    (directory / "summary.json").write_text(summary, encoding="utf-8", newline="\n")
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--per-domain", type=int, default=25)
    parser.add_argument("--output", type=Path, help="batch directory inside .runs/events/")
    args = parser.parse_args(argv)
    try:
        events = generate_events(args.seed, args.per_domain)
        output = write_events(events, args.output or ROOT / ".runs/events" / ("demo-" + _label(str(args.seed))))
    except ValueError as exc:
        parser.error(str(exc))
    print(output)


if __name__ == "__main__":
    main()
