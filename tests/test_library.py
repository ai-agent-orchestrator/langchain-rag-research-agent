"""Research library: folder -> chunks -> Chroma -> search -> Equalizer brief (synthetic documents)."""
import sys
from pathlib import Path

import pytest

pytest.importorskip("chromadb", reason="needs the `chroma` extra")

from rag_research_agent.core.contracts import RetrievalUnavailable
from rag_research_agent.embed.providers import FakeEmbedder
from rag_research_agent.ingest.paragraphs import paragraph_chunks
from rag_research_agent.rag.library import Library, load_folder

DOCS = [
    ("macro", "macro.md", "가상국 금리는 3.0%에서 3.5%로 올랐다.\n\n소비 둔화는 금리 때문으로 보였지만 실제로는 가계부채 부담이 누적된 결과였다."),
    ("tech", "tech.md", "가상 회사는 연내 출시를 목표로 했지만 출시가 연기됐다.\n\n독립 벤치마크 결과는 아직 공개되지 않았다."),
    ("legal", "legal.md", "을은 해지 통보 14일 뒤에야 보증금 반환을 요구했다.\n\n누수의 실제 원인은 배관 공사였다."),
]


def test_paragraph_chunks_keep_text_and_split_long_paragraphs():
    cs = paragraph_chunks("d", "t", "짧은 문단.\n\n" + "긴 문장입니다. " * 80, max_chars=120)
    assert cs[0].safe_text == "짧은 문단." and all(len(c.safe_text) <= 130 for c in cs[1:]) and len(cs) > 3


def test_build_search_reopen_and_embedder_guard(tmp_path):
    lib = Library(tmp_path, embedder=FakeEmbedder(64)).build(DOCS)
    assert len(lib.chunks) == 6
    top = lib.search("가계부채 금리", k=3)
    assert top[0][0].document_id == "macro"
    again = Library(tmp_path, embedder=FakeEmbedder(64)).open()
    assert again.search("보증금 반환", k=1, mode="lex")[0][0].document_id == "legal"
    with pytest.raises(RetrievalUnavailable):
        Library(tmp_path, embedder=FakeEmbedder(32)).open()


def test_brief_runs_profile_on_retrieved_chunks(tmp_path):
    lib = Library(tmp_path, embedder=FakeEmbedder(64)).build(DOCS)
    brief, trace, hits = lib.brief("금리 가계부채", profile="macro", k=3, budget=400)
    assert hits and brief.status.value in ("OK", "BUDGET_PROTECTED_OVERFLOW")
    assert "가계부채" in brief.final_prompt_input


def test_library_board_builds_html_from_a_folder(tmp_path):
    folder = tmp_path / "docs"
    folder.mkdir()
    for _id, name, text in DOCS:
        (folder / name).write_text(text, encoding="utf-8")
    assert len(load_folder(folder)) == 3
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts"))
    import library_board as lb
    out = tmp_path / "board.html"
    assert lb.main(["--path", str(tmp_path / "lib"), "--add", str(folder), "--query", "금리", "--profile", "macro", "--out", str(out)]) == 0
    assert "저장소 확인 보드" in out.read_text(encoding="utf-8")
