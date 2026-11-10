"""summarize_run.py - one page per NightCoder run (Markdown + dark HTML) for the morning / Sunday check.

    python summarize_run.py --run C:/Users/Codelab/nc2-rra-codex/runs/20261114-1830 --lane C:/work/rra-codex

Reads: <run>/outbox/<task>/REPORT.md and *.patch, <run>/supervise.log, <work>/wrap.log, the lane branch log.
Writes: <run>/SUMMARY.md and <run>/SUMMARY.html. Nothing is sent anywhere.
"""
from __future__ import annotations

import argparse
import html
import re
import subprocess
from datetime import datetime
from pathlib import Path

PASS_RE = re.compile(r"(\d+)\s+passed")
FAIL_RE = re.compile(r"\b(FAIL|FAILED|NO_COMMIT|TESTS|SCOPE_VIOLATION|FORBIDDEN_FILE|TEST_TAMPERING|UNCOMMITTED)\b")


def task_rows(outbox: Path) -> list[dict]:
    rows = []
    for d in sorted(p for p in outbox.iterdir() if p.is_dir()) if outbox.exists() else []:
        report = d / "REPORT.md"
        text = report.read_text(encoding="utf-8", errors="replace") if report.exists() else ""
        patches = sorted(d.glob("*.patch"))
        passed = PASS_RE.findall(text)
        fail = FAIL_RE.search(text)
        status = "ok" if patches and not fail else ("failed" if fail or not patches else "?")
        subjects = []
        for p in patches:
            m = re.search(r"^Subject: (?:\[PATCH[^\]]*\] )?(.*)$", p.read_text(encoding="utf-8", errors="replace"), re.M)
            if m:
                subjects.append(m.group(1).strip())
        rows.append({"task": d.name, "status": status, "patches": len(patches), "passed": passed[-1] if passed else "",
                     "reason": fail.group(1) if fail else "", "subjects": subjects})
    return rows


def tail(path: Path, n: int) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]


def render(run: Path, lane: str | None, work: Path) -> tuple[str, str]:
    rows = task_rows(run / "outbox")
    ok = sum(r["status"] == "ok" for r in rows)
    failed = [r for r in rows if r["status"] != "ok"]
    queued_left = sorted(p.name for p in (work / "inbox").glob("*.md")) if (work / "inbox").exists() else []
    commits = []
    if lane:
        out = subprocess.run(["git", "-C", lane, "log", "--oneline", "origin/main..HEAD"], capture_output=True, text=True)
        commits = out.stdout.strip().splitlines()
    sup = tail(run / "supervise.log", 20)
    wrap = tail(work / "wrap.log", 10)
    now = datetime.now().isoformat(timespec="minutes")
    md = [f"# NightCoder run {run.name}", "", f"generated {now}", "",
          f"**{ok} ok · {len(failed)} failed · {len(queued_left)} still queued · {len(commits)} commits on the lane branch**", "",
          "| task | status | patches | tests passed | reason / commit subjects |", "| --- | --- | --- | --- | --- |"]
    for r in rows:
        md.append(f"| {r['task']} | {r['status']} | {r['patches']} | {r['passed']} | {r['reason'] or '; '.join(r['subjects'])[:160]} |")
    if queued_left:
        md += ["", "Still queued (not run): " + ", ".join(queued_left)]
    if sup:
        md += ["", "## supervise.log (last 20)", "", "```", *sup, "```"]
    if wrap:
        md += ["", "## wrap.log (last 10)", "", "```", *wrap, "```"]
    md += ["", "Next: apply patches from `outbox/<task>/` (or merge the lane branch) after review; failed tasks: read their REPORT.md."]
    body = "".join(
        f"<tr><td>{html.escape(r['task'])}</td><td class='{r['status']}'>{r['status']}</td><td>{r['patches']}</td>"
        f"<td>{html.escape(r['passed'])}</td><td>{html.escape(r['reason'] or '; '.join(r['subjects'])[:160])}</td></tr>" for r in rows)
    pre = lambda lines: "<pre>" + html.escape("\n".join(lines)) + "</pre>" if lines else "<p class='m'>-</p>"
    page = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>NightCoder Run</title><style>
:root{{--bg:#0e141b;--card:#131c27;--line:#24324a;--text:#e6edf6;--muted:#9aabbd;--cyan:#78d5ef}}
body{{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 "Noto Sans KR","Malgun Gothic",sans-serif;padding:16px}}
section,header{{max-width:1000px;margin:0 auto 14px}} section{{background:var(--card);border:1px solid var(--line);border-left:3px solid #5ba7db;border-radius:10px;padding:12px}}
.e{{color:var(--cyan);font-size:11px;font-weight:700;letter-spacing:.08em}} h1{{margin:4px 0}} .m{{color:var(--muted)}}
.s{{overflow-x:auto}} table{{border-collapse:collapse;width:100%;min-width:620px}} td,th{{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}
th{{color:var(--muted);font-size:12px}} .ok{{color:#91cc45}} .failed{{color:#c58b92}} pre{{white-space:pre-wrap;font-size:12px;background:#0f1822;border:1px solid var(--line);border-radius:8px;padding:8px}}
</style></head><body><header><div class="e">NIGHTCODER · RUN SUMMARY</div><h1>{html.escape(run.name)}</h1>
<p class="m">{now} · <b>{ok} ok</b> · {len(failed)} failed · {len(queued_left)} still queued · {len(commits)} commits</p></header>
<section><div class="s"><table><tr><th>task</th><th>status</th><th>patches</th><th>tests passed</th><th>reason / commits</th></tr>{body}</table></div>
{('<p class="m">still queued: ' + html.escape(', '.join(queued_left)) + '</p>') if queued_left else ''}</section>
<section><div class="e">SUPERVISE.LOG</div>{pre(sup)}</section><section><div class="e">WRAP.LOG</div>{pre(wrap)}</section></body></html>"""
    return "\n".join(md) + "\n", page


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--lane")
    ap.add_argument("--work", help="default: two levels above the run folder")
    a = ap.parse_args(argv)
    run = Path(a.run)
    work = Path(a.work) if a.work else run.parent.parent
    md, page = render(run, a.lane, work)
    (run / "SUMMARY.md").write_text(md, encoding="utf-8")
    (run / "SUMMARY.html").write_text(page, encoding="utf-8")
    print(md)
    print(f"HTML: {run / 'SUMMARY.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
