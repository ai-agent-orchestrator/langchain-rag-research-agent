"""Build/open the research library and see what is inside (dark HTML, opens on a phone).

    python scripts/library_board.py --add path/to/folder                 # (re)build from .txt/.md files
    python scripts/library_board.py --query "금리와 가계부채" --profile macro --budget 600
Writes .runs/library_board.html. Real documents stay under .runs/ (git-ignored).
"""
from __future__ import annotations

import argparse
import html
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rag_research_agent.rag.library import Library, load_folder  # noqa: E402

CSS = """:root{--bg:#0e141b;--card:#131c27;--line:#24324a;--text:#e6edf6;--muted:#9aabbd;--cyan:#78d5ef}
body{margin:0;background:var(--bg);color:var(--text);font:14px/1.55 "Noto Sans KR","Malgun Gothic",sans-serif;padding:16px}
header,section{max-width:1000px;margin:0 auto 16px}section{background:var(--card);border:1px solid var(--line);border-left:3px solid #5ba7db;border-radius:10px;padding:14px}
section:nth-of-type(2n){border-left-color:#4cc3a8}.eyebrow{color:var(--cyan);font-size:11px;letter-spacing:.08em;font-weight:700}
h1{margin:4px 0}h2{margin:2px 0 10px;font-size:17px}p,.muted{color:var(--muted)}.scroll{overflow-x:auto}
table{border-collapse:collapse;width:100%}th,td{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{color:var(--muted);font-size:12px}td.n{white-space:nowrap}pre{white-space:pre-wrap;background:#0f1822;border:1px solid var(--line);border-radius:8px;padding:10px}
footer{max-width:1000px;margin:0 auto;color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.06em}"""


def esc(x) -> str:
    return html.escape(str(x))


def render(lib: Library, query: str | None, profile: str | None, budget: int, k: int) -> str:
    per_doc = Counter(c.document_id for c in lib.chunks)
    docs = "".join(f"<tr><td>{esc(d)}</td><td class='n'>{n}</td><td>{esc(next(c.title for c in lib.chunks if c.document_id == d))}</td></tr>"
                   for d, n in per_doc.items())
    samples = "".join(f"<tr><td class='n'>{esc(c.chunk_id)}</td><td>{esc(c.safe_text[:160])}{'…' if len(c.safe_text) > 160 else ''}</td></tr>"
                      for c in lib.chunks[:12])
    parts = [f"<section><div class='eyebrow'>STORE</div><h2>{esc(lib.collection)} · 조각 {len(lib.chunks)}개 · 문서 {len(per_doc)}개</h2>"
             f"<p>저장소 Chroma · 임베더 {esc(type(lib.embedder).__name__)} (가짜 임베더 결과는 키워드 유사도에 가깝습니다)</p>"
             f"<div class='scroll'><table><tr><th>문서</th><th>조각</th><th>제목</th></tr>{docs}</table></div></section>",
             f"<section><div class='eyebrow'>SAMPLES</div><h2>저장된 조각 (처음 12개)</h2><div class='scroll'><table>"
             f"<tr><th>ID</th><th>본문</th></tr>{samples}</table></div></section>"]
    if query:
        rows = []
        for mode in ("hybrid", "vector", "lex"):
            for c, s, r in lib.search(query, k, mode):
                rows.append(f"<tr><td class='n'>{mode}</td><td class='n'>{r}</td><td class='n'>{s}</td><td class='n'>{esc(c.chunk_id)}</td><td>{esc(c.safe_text[:140])}</td></tr>")
        parts.append(f"<section><div class='eyebrow'>SEARCH</div><h2>질문: {esc(query)}</h2><div class='scroll'><table>"
                     f"<tr><th>방식</th><th>순위</th><th>점수</th><th>조각</th><th>본문</th></tr>{''.join(rows)}</table></div></section>")
        if profile:
            brief, trace, _ = lib.brief(query, profile, k, budget)
            kept = sum(1 for r in trace.rows if r.get("kept"))
            parts.append(f"<section><div class='eyebrow'>EQUALIZER · {esc(profile)}</div><h2>브리프 ({esc(brief.status.value)} · 남긴 문장 {kept}/{len(trace.rows)})</h2>"
                         f"<pre>{esc(brief.final_prompt_input or '(없음)')}</pre>"
                         f"<p class='muted'>감량 기록: {esc('; '.join(trace.diet_log) or '-')}</p></section>")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return (f"<!doctype html><html lang='ko'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>Library Board</title><style>{CSS}</style></head><body><header><div class='eyebrow'>RESEARCH LIBRARY</div>"
            f"<h1>저장소 확인 보드</h1><p>{now}</p></header>{''.join(parts)}<footer>로컬 저장 · 외부 전송 없음 · v0</footer></body></html>")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default=str(ROOT / ".runs/library"))
    ap.add_argument("--add", help="folder with .txt/.md files; rebuilds the library")
    ap.add_argument("--query")
    ap.add_argument("--profile")
    ap.add_argument("--budget", type=int, default=800)
    ap.add_argument("-k", type=int, default=8)
    ap.add_argument("--out", default=str(ROOT / ".runs/library_board.html"))
    a = ap.parse_args(argv)
    lib = Library(a.path)
    if a.add:
        docs = load_folder(a.add)
        lib.build(docs)
        print(f"built: {len(lib.chunks)} chunks from {len(docs)} documents")
    else:
        lib.open()
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(lib, a.query, a.profile, a.budget, a.k), encoding="utf-8")
    print(f"HTML: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
