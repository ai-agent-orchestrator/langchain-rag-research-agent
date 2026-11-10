"""X0: disposable, synthetic SDK write probes. No retries or production changes."""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def trial(sdk, path, *, lexical=True, batch=8, count=24):
    path.parent.mkdir(parents=True, exist_ok=True)
    result = {"path": str(path), "lexical": lexical, "batch": batch, "count": count,
              "events": [], "first_error": None}
    mem = None
    stage = "open"
    try:
        mem = sdk.use("basic", str(path), mode="auto", enable_vec=True, enable_lex=lexical)
        for start in range(0, count, batch):
            stage = f"put:{start}"
            ids = range(start, min(start + batch, count))
            mem.put_many([{"title": f"DOC-{i}", "text": f"synthetic text {i}",
                           "label": "guide", "metadata": {}, "enable_embedding": False} for i in ids],
                         embeddings=[[float(j == i % 1024) for j in range(1024)] for i in ids],
                         embedding_identity={"provider": "external", "model": "synthetic",
                                             "dimension": 1024, "normalized": True})
            result["events"].append(stage)
        stage = "seal"
        mem.seal()
        result["events"].append(stage)
    except Exception as exc:
        result["first_error"] = {"stage": stage, "type": type(exc).__name__, "message": str(exc),
                                 "errno": getattr(exc, "errno", None), "winerror": getattr(exc, "winerror", None)}
    finally:
        if mem is not None:
            try:
                mem.close()
            except Exception as exc:
                result["close_error"] = f"{type(exc).__name__}: {exc}"
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=".runs/x0")
    ap.add_argument("--trials", type=int, default=3)
    args = ap.parse_args(argv)
    out = Path(args.out).resolve()
    if not out.is_relative_to(ROOT / ".runs") or args.trials < 1:
        ap.error("out must be inside this repository's .runs; trials must be positive")
    from rag_research_agent.guard.network import block_network, scrub_environment
    scrub_environment()
    block_network()
    from rag_research_agent.store.memvid_store import load_memvid
    sdk = load_memvid()
    run = out / uuid.uuid4().hex
    run.mkdir(parents=True)
    results = []
    for n in range(args.trials):
        for folder, lexical, batch in [("ascii", True, 8), ("한글", True, 8),
                                       ("ascii-no-lex", False, 8), ("ascii-single", True, 1)]:
            results.append(trial(sdk, run / folder / f"trial-{n}.mv2", lexical=lexical, batch=batch))
    # A held read handle is an explicit lock control, separate from unlocked writes above.
    lock = run / "lock-control.txt"
    lock.write_text("synthetic", encoding="utf-8")
    replacement = run / "replacement.txt"
    replacement.write_text("synthetic", encoding="utf-8")
    with lock.open("rb"):
        try:
            os.replace(replacement, lock)
            lock_result = "replace succeeded with read handle open"
        except OSError as exc:
            lock_result = {"type": type(exc).__name__, "message": str(exc), "winerror": exc.winerror if hasattr(exc, "winerror") else None}
    report = {"platform": platform.platform(), "python": sys.version,
              "sdk": importlib.metadata.version("memvid-sdk"), "trials": results,
              "lock_control": lock_result,
              "limits": "One OS and SDK version only; lock control does not prove the SDK failure has the same cause."}
    target = run / "diagnosis.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(target)
    print(f"{sum(r['first_error'] is not None for r in results)}/{len(results)} write probes failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
