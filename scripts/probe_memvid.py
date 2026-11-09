"""B02a: check the memvid features RAG v1 depends on, with synthetic vectors only.

Usage:  python scripts/probe_memvid.py --out docs/evidence/B02a/memvid_capabilities_<os>.json
Exit code 0 only when every required check passes. Network is blocked for the whole run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import random
import shutil
import sys
import tempfile
from pathlib import Path

from rag_research_agent.guard.network import ATTEMPTS, block_network, scrub_environment

REQUIRED = ["telemetry_off", "put_external_vectors", "query_vector_search", "score_direction",
            "lexical_search", "dimension_mismatch_put", "dimension_mismatch_query", "seal_and_reopen",
            "title_roundtrip", "no_network_attempts", "pointer_swap_while_open"]


def unit(vec):
    norm = math.sqrt(sum(x * x for x in vec))
    return [x / norm for x in vec]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--dimension", type=int, default=1024)
    args = parser.parse_args()
    scrub_environment()
    block_network()
    from rag_research_agent.store.memvid_store import load_memvid
    results: dict[str, dict] = {}

    def record(name, ok, detail=""):
        results[name] = {"pass": bool(ok), "detail": str(detail)[:300]}

    memvid = load_memvid()
    record("telemetry_off", not memvid.is_telemetry_enabled(), os.environ.get("MEMVID_TELEMETRY"))
    work = Path(tempfile.mkdtemp(prefix="memvid-probe-"))
    rng = random.Random(7)
    dim = args.dimension
    base = [[rng.gauss(0, 1) for _ in range(dim)] for _ in range(5)]
    vectors = [unit(b) for b in base]
    titles = [f"GUIDE-00{i}:c01:v1" for i in range(5)]
    texts = ["합성 안내문 보증금 계약서 준비"] + [f"합성 안내문 다른 주제 {i}" for i in range(1, 5)]
    path = work / "probe-v1.mv2"
    try:
        mem = memvid.use("basic", str(path), mode="auto", enable_vec=True, enable_lex=True)
        try:
            mem.put_many([{"title": t, "label": "guide", "text": x, "metadata": {}, "enable_embedding": False}
                          for t, x in zip(titles, texts)], embeddings=vectors,
                         embedding_identity={"provider": "external", "model": "synthetic", "dimension": dim,
                                             "normalized": True})
            record("put_external_vectors", True)
        except Exception as exc:
            record("put_external_vectors", False, f"{type(exc).__name__}: {exc}")
        query = unit([b + rng.gauss(0, 0.1) for b in base[2]])
        try:
            hits = mem.find("", k=3, mode="sem", query_embedding=query)["hits"]
            record("query_vector_search", hits and hits[0]["title"] == titles[2],
                   [(h["title"], round(float(h["score"]), 4)) for h in hits])
            record("score_direction", len(hits) > 1 and float(hits[0]["score"]) > float(hits[1]["score"]),
                   "higher score = closer")
            record("title_roundtrip", all(h["title"] in titles for h in hits), "provenance via title")
        except Exception as exc:
            for name in ("query_vector_search", "score_direction", "title_roundtrip"):
                record(name, False, f"{type(exc).__name__}: {exc}")
        try:
            hits = mem.find("보증금", k=3, mode="lex")["hits"]
            record("lexical_search", hits and hits[0]["title"] == titles[0], [h["title"] for h in hits])
        except Exception as exc:
            record("lexical_search", False, f"{type(exc).__name__}: {exc}")
        try:
            mem.put_many([{"title": "BAD", "label": "guide", "text": "x", "metadata": {}, "enable_embedding": False}],
                         embeddings=[[0.1] * (dim // 2)])
            record("dimension_mismatch_put", False, "accepted a wrong-dimension vector")
        except Exception as exc:
            record("dimension_mismatch_put", True, type(exc).__name__)
        try:
            mem.find("", k=3, mode="sem", query_embedding=[0.1] * (dim // 2))
            record("dimension_mismatch_query", False, "accepted a wrong-dimension query")
        except Exception as exc:
            record("dimension_mismatch_query", True, type(exc).__name__)
        mem.seal()
        mem.close()
        reopened = memvid.use("basic", str(path), mode="open", enable_vec=True, read_only=True)
        hits = reopened.find("", k=1, mode="sem", query_embedding=query)["hits"]
        record("seal_and_reopen", hits and hits[0]["title"] == titles[2])
        # Activation swaps a small pointer file while the index is still open (Windows locking check).
        pointer = work / "active.json"
        pointer.write_text(json.dumps({"file": path.name}), encoding="utf-8")
        tmp = work / "active.json.tmp"
        tmp.write_text(json.dumps({"file": "probe-v2.mv2"}), encoding="utf-8")
        try:
            os.replace(tmp, pointer)
            record("pointer_swap_while_open", True)
        except OSError as exc:
            record("pointer_swap_while_open", False, f"{type(exc).__name__}: {exc}")
        # Informational: can an open .mv2 be replaced or deleted? Expected to fail on Windows.
        try:
            other = work / "other.mv2"
            shutil.copyfile(path, other)
            os.replace(other, path)
            results["info_replace_open_mv2"] = {"pass": True, "detail": "replace allowed"}
        except OSError as exc:
            results["info_replace_open_mv2"] = {"pass": False, "detail": f"{type(exc).__name__}: {exc}"}
        reopened.close()
    finally:
        record("no_network_attempts", not ATTEMPTS, ATTEMPTS)
        shutil.rmtree(work, ignore_errors=True)
    try:
        from importlib.metadata import version
        sdk_version = version("memvid-sdk")
    except Exception:
        sdk_version = "unknown"
    report = {"platform": platform.platform(), "python": sys.version.split()[0], "memvid_sdk": sdk_version,
              "dimension": dim, "required": REQUIRED, "results": results,
              "all_required_pass": all(results.get(n, {}).get("pass") for n in REQUIRED)}
    report["sha256"] = hashlib.sha256(json.dumps(results, sort_keys=True).encode()).hexdigest()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"all_required_pass": report["all_required_pass"], "out": str(out)}))
    return 0 if report["all_required_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
