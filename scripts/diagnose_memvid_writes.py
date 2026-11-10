"""X0: disposable, synthetic SDK write probes. No retries or production changes."""
import argparse
from collections import Counter
import ctypes
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import itertools
import json
import os
from pathlib import Path
import platform
import re
import shutil
import statistics
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rag_research_agent.observe.gate_grid import wilson


def process_handle_count():
    if os.name != "nt":
        return None
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.GetProcessHandleCount.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    count = wintypes.DWORD()
    if not kernel.GetProcessHandleCount(kernel.GetCurrentProcess(), ctypes.byref(count)):
        return None
    return count.value


def occupancy(path):
    """Read-only Restart Manager query; never call shutdown/restart or enumerate handle contents."""
    if os.name != "nt":
        return {"status": "unsupported", "processes": [], "complete_handle_inventory": False}
    from ctypes import wintypes as w
    class UniqueProcess(ctypes.Structure):
        _fields_ = [("pid", w.DWORD), ("started", w.FILETIME)]
    class ProcessInfo(ctypes.Structure):
        _fields_ = [("process", UniqueProcess), ("name", w.WCHAR * 256), ("service", w.WCHAR * 64),
                    ("application_type", w.UINT), ("status", w.ULONG), ("session", w.DWORD), ("restartable", w.BOOL)]
    try:
        rm = ctypes.WinDLL("Rstrtmgr", use_last_error=True)
        rm.RmStartSession.argtypes = [ctypes.POINTER(w.DWORD), w.DWORD, w.LPWSTR]
        rm.RmRegisterResources.argtypes = [w.DWORD, w.UINT, ctypes.POINTER(w.LPCWSTR), w.UINT, ctypes.POINTER(UniqueProcess), w.UINT, ctypes.POINTER(w.LPCWSTR)]
        rm.RmGetList.argtypes = [w.DWORD, ctypes.POINTER(w.UINT), ctypes.POINTER(w.UINT), ctypes.POINTER(ProcessInfo), ctypes.POINTER(w.DWORD)]
        rm.RmEndSession.argtypes = [w.DWORD]
        handle, key = w.DWORD(), ctypes.create_unicode_buffer(33)
        code = rm.RmStartSession(ctypes.byref(handle), 0, key)
        if code:
            return {"status": "start_error", "code": code, "complete_handle_inventory": False}
        try:
            files = (w.LPCWSTR * 1)(str(path.resolve()))
            code = rm.RmRegisterResources(handle, 1, files, 0, None, 0, None)
            if code:
                return {"status": "register_error", "code": code, "complete_handle_inventory": False}
            needed, size, reasons = w.UINT(), w.UINT(), w.DWORD()
            code = rm.RmGetList(handle, ctypes.byref(needed), ctypes.byref(size), None, ctypes.byref(reasons))
            for _ in range(3):
                if code != 234:  # ERROR_MORE_DATA: process list can change while queried.
                    break
                buffer = (ProcessInfo * needed.value)()
                size.value = needed.value
                code = rm.RmGetList(handle, ctypes.byref(needed), ctypes.byref(size), buffer, ctypes.byref(reasons))
            processes = [] if code or not size.value else [
                {"pid": p.process.pid, "name": p.name, "service": p.service,
                 "is_probe_process": p.process.pid == os.getpid()} for p in buffer[:size.value]]
            return {"status": "ok" if not code else "list_error", "code": code, "processes": processes,
                    "complete_handle_inventory": False,
                    "limit": "RM-visible users of this exact path only; no native handle IDs or SDK temporary-index paths"}
        finally:
            rm.RmEndSession(handle)
    except Exception as exc:
        return {"status": "unavailable", "error": f"{type(exc).__name__}: {exc}", "complete_handle_inventory": False}


def trial(sdk, path, *, lexical=True, batch=8, count=24, wait_ms=0, inspector=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    result = {"path": str(path), "lexical": lexical, "batch": batch, "count": count,
              "wait_ms": wait_ms, "events": [], "timings": [], "first_error": None,
              "process_handles_before": process_handle_count()}
    started = time.perf_counter()
    def timed(stage, operation):
        begin = time.perf_counter()
        ok = False
        try:
            value = operation()
            ok = True
            return value
        finally:
            result["timings"].append({"stage": stage, "ok": ok, "elapsed_ms": (time.perf_counter() - begin) * 1000})
    def error(exc, stage):
        return {"stage": stage, "type": type(exc).__name__, "message": str(exc),
                "errno": getattr(exc, "errno", None), "winerror": getattr(exc, "winerror", None)}
    mem = None
    stage = "open"
    try:
        mem = timed(stage, lambda: sdk.use("basic", str(path), mode="auto", enable_vec=True, enable_lex=lexical))
        stage = "after_create_wait"
        timed(stage, lambda: time.sleep(wait_ms / 1000))
        for start in range(0, count, batch):
            stage = f"put:{start}"
            ids = range(start, min(start + batch, count))
            requests = [{"title": f"DOC-{i}", "text": f"synthetic text {i}",
                           "label": "guide", "metadata": {}, "enable_embedding": False} for i in ids]
            vectors = [[float(j == i % 1024) for j in range(1024)] for i in ids]
            timed(stage, lambda: mem.put_many(requests, embeddings=vectors,
                         embedding_identity={"provider": "external", "model": "synthetic",
                                             "dimension": 1024, "normalized": True}))
            result["events"].append(stage)
        stage = "seal"
        timed(stage, mem.seal)
        result["events"].append(stage)
    except Exception as exc:
        result["first_error"] = error(exc, stage)
        if inspector:
            result["occupancy_before_close"] = inspector(path)
    finally:
        if mem is not None:
            try:
                timed("close", mem.close)
            except Exception as exc:
                result["close_error"] = f"{type(exc).__name__}: {exc}"
                result["first_error"] = result["first_error"] or error(exc, "close")
        result["process_handles_after_close"] = process_handle_count()
        if result["first_error"] and inspector:
            result["occupancy_after_close"] = inspector(path)
    result["success"] = result["first_error"] is None and not result.get("close_error")
    result["elapsed_ms"] = (time.perf_counter() - started) * 1000
    result["operation_elapsed_ms"] = sum(t["elapsed_ms"] for t in result["timings"])
    return result


def summaries(rows):
    result = []
    for condition in sorted({r["condition"] for r in rows}):
        group = [r for r in rows if r["condition"] == condition]
        eligible = [r for r in group if r["condition_established"]]
        durations = [r["elapsed_ms"] for r in eligible]
        successes = sum(r["success"] for r in eligible)
        interval = wilson(successes, len(eligible))
        result.append({"condition": condition, "attempts": len(group), "n": len(eligible),
                       "condition_not_established": len(group) - len(eligible),
                       "success": {"count": successes, "n": len(eligible), "rate": interval["rate"], "wilson95": interval["wilson95"]},
                       "first_failure_stages": dict(Counter(r["first_error"]["stage"] for r in eligible if r["first_error"])),
                       "close_failures": sum(bool(r.get("close_error")) for r in eligible),
                       "elapsed_ms": {"sum": sum(durations), "median": statistics.median(durations) if durations else None,
                                      "max": max(durations) if durations else None},
                       "operation_ms_without_inspection_median": statistics.median(r["operation_elapsed_ms"] for r in eligible) if eligible else None})
    return result


def write_reports(run, configuration, rows, seeds, extra):
    report = {"schema": "rra-memvid-write-diagnostics/2", "configuration": configuration,
              "protocol_sha256": hashlib.sha256(json.dumps(configuration, sort_keys=True).encode()).hexdigest(),
              "summary": summaries(rows), "trials": rows, "seeds": seeds, **extra}
    (run / "diagnosis.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# X0 합성 벡터 경로 시험", "", "성공률은 Wilson 95% 구간과 함께 표시. 0건 실패는 보장이 아니다.", "",
             "| 조건 | n/시도 | 성공 | 성공률 | Wilson 95% | 최초 실패 단계 | close 실패 | 총/중앙/최대 ms |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for s in report["summary"]:
        w = s["success"]
        lines.append(f"| {s['condition']} | {s['n']}/{s['attempts']} | {w['count']} | {w['rate']} | {w['wilson95']} | {s['first_failure_stages']} | {s['close_failures']} | {s['elapsed_ms']} |")
    (run / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=".runs/x0")
    ap.add_argument("--trials", type=int, default=3)
    ap.add_argument("--suite", choices=["legacy", "followup"], default="followup")
    ap.add_argument("--locations", nargs="+", choices=["workspace", "temp", "other"], default=["workspace", "temp"])
    ap.add_argument("--other-root", type=Path)
    ap.add_argument("--wait-ms", nargs="+", type=int, choices=[0,100,500], default=[0,100,500])
    ap.add_argument("--previous-handle", nargs="+", choices=["closed", "hold-reader"], default=["closed", "hold-reader"])
    ap.add_argument("--count", type=int, default=24)
    ap.add_argument("--label", default="baseline")
    args = ap.parse_args(argv)
    out = Path(args.out).resolve()
    if not out.is_relative_to(ROOT / ".runs" / "x0") or not 1 <= args.trials <= 30 or args.count < 1 or not re.fullmatch(r"[A-Za-z0-9_-]+", args.label):
        ap.error("out must be inside .runs/x0; trials 1..30; positive count; ASCII label")
    if "other" in args.locations and (args.other_root is None or not args.other_root.is_dir() or args.other_root.resolve().anchor.lower() == ROOT.anchor.lower()):
        ap.error("other location requires an existing --other-root on another drive")
    from rag_research_agent.guard.network import block_network, scrub_environment
    scrub_environment()
    block_network()
    from rag_research_agent.store.memvid_store import load_memvid
    sdk = load_memvid()
    run_id = uuid.uuid4().hex
    run = out / args.label / run_id
    run.mkdir(parents=True)
    roots = {"workspace": run / "workspace", "temp": Path(tempfile.gettempdir()).resolve() / f"rra-x0-{run_id}"}
    if args.other_root is not None:
        roots["other"] = args.other_root.resolve() / f"rra-x0-{run_id}"
    cases = []
    if args.suite == "legacy":
        cases = [(folder, "workspace", 0, "closed", lex, batch) for folder, lex, batch in
                 [("ascii", True, 8), ("한글", True, 8), ("ascii-no-lex", False, 8), ("ascii-single", True, 1)]]
    else:
        cases = [(f"{location}-w{wait}-{handle}", location, wait, handle, True, 8)
                 for location, wait, handle in itertools.product(dict.fromkeys(args.locations), dict.fromkeys(args.wait_ms), dict.fromkeys(args.previous_handle))]
    configuration = {"platform": platform.platform(), "python": sys.version, "sdk": importlib.metadata.version("memvid-sdk"),
                     "suite": args.suite, "trials_per_condition": args.trials, "count": args.count,
                     "cases": cases, "location_bases": {k: str(ROOT if k == "workspace" else v.parent) for k,v in roots.items()},
                     "order": "fixed round-robin; one seed per condition excluded from rates",
                     "wait_point": "after sdk.use returns, before first put; not before SDK internal creation writes",
                     "previous_handle_control": "own read handle on previous trial's different file; SDK writer always closed",
                     "telemetry": "off", "network": "blocked", "schema_version": 2}
    results, seeds, previous = [], [], {}
    extra = {"label": args.label, "started_at": datetime.now(timezone.utc).isoformat(), "finished": False,
             "pid": os.getpid(), "available_drives": os.listdrives() if hasattr(os, "listdrives") else [],
             "limits": "Single Windows/SDK version. RM is not a complete handle inventory; no antivirus settings changed. Synthetic vectors only."}
    print(run, flush=True)
    # Seeds establish a real previous SDK-file history even for the first counted trial.
    for name, location, wait, handle, lex, batch in cases:
        path = roots[location] / name / "seed.mv2"
        seed = trial(sdk, path, lexical=lex, batch=batch, count=args.count, wait_ms=wait, inspector=occupancy)
        seeds.append({"condition": name, **seed})
        previous[name] = path
    write_reports(run, configuration, results, seeds, extra)
    with (run / "trials.jsonl").open("a", encoding="utf-8") as stream:
        for n in range(args.trials):
            for name, location, wait, handle, lex, batch in cases:
                old = previous[name]
                reader, reader_error = None, None
                if handle == "hold-reader":
                    try:
                        reader = old.open("rb")
                    except OSError as exc:
                        reader_error = str(exc)
                try:
                    path = roots[location] / name / f"trial-{n:03d}.mv2"
                    record = trial(sdk, path, lexical=lex, batch=batch, count=args.count, wait_ms=wait, inspector=occupancy)
                    record.update(condition=name, trial=n, previous_path=str(old), previous_reader_open=reader is not None,
                                  previous_reader_error=reader_error, condition_established=handle == "closed" or reader is not None)
                finally:
                    if reader is not None:
                        reader.close()
                results.append(record)
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
                stream.flush()
                previous[name] = path
            write_reports(run, configuration, results, seeds, extra)
            print(f"round {n + 1}/{args.trials}: {len(results)} probes, {sum(not r['success'] for r in results)} failed", flush=True)
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
    extra.update(lock_control=lock_result, finished=True, finished_at=datetime.now(timezone.utc).isoformat(), cleanup=[])
    for location in dict.fromkeys(c[1] for c in cases):
        if location == "workspace":
            continue
        target = roots[location].resolve()
        intended_parent = Path(tempfile.gettempdir()).resolve() if location == "temp" else args.other_root.resolve()
        if target.parent != intended_parent or target.name != f"rra-x0-{run_id}":
            raise RuntimeError("refusing cleanup outside the exact disposable probe root")
        try:
            shutil.rmtree(target)
            extra["cleanup"].append({"path": str(target), "status": "removed disposable SDK files"})
        except OSError as exc:
            extra["cleanup"].append({"path": str(target), "status": "cleanup failed", "error": str(exc)})
    write_reports(run, configuration, results, seeds, extra)
    print(run / "diagnosis.json")
    print(f"{sum(r['first_error'] is not None for r in results)}/{len(results)} write probes failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
