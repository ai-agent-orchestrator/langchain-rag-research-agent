"""B01 chunking with a deterministic token counter (the real E5 tokenizer runs in ingest_guides)."""
from pathlib import Path
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "synthetic_guides"

from memvid_guardrail.ingest.chunking import build_chunks, load_guides, split_document
from memvid_guardrail.embed.providers import FakeEmbedder
from memvid_guardrail.guard.masking import contains_pii, mask_pii

COUNT = FakeEmbedder().count_tokens


def test_chunks_respect_budget_and_keep_title_and_headings():
    docs = load_guides(FIXTURE)
    chunks = build_chunks(docs, COUNT, "fake")
    assert {c.document_id for c in chunks} == {d.document_id for d in docs}
    for chunk in chunks:
        assert chunk.token_count <= 300
        assert chunk.safe_text.startswith(chunk.title + "\n")
        assert "합성 학습 자료이며" not in chunk.safe_text   # disclaimer line is not indexed
        last_line = chunk.safe_text.rstrip().splitlines()[-1]
        assert not last_line.startswith("## ")           # a heading never ends a chunk alone


def test_chunking_is_deterministic_and_ids_are_unique():
    docs = load_guides(FIXTURE)
    first = build_chunks(docs, COUNT, "fake")
    second = build_chunks(docs, COUNT, "fake")
    assert [c.chunk_id for c in first] == [c.chunk_id for c in second]
    assert [c.content_hash for c in first] == [c.content_hash for c in second]
    assert len({c.chunk_id for c in first}) == len(first)


def test_small_budget_forces_overlap_within_a_section():
    doc = load_guides(FIXTURE)[0]
    pieces = split_document(doc, COUNT, max_tokens=80, overlap_tokens=20)
    assert len(pieces) > 3 and all(tokens <= 80 for _, tokens in pieces)
    lines = [set(text.splitlines()[1:]) for text, _ in pieces]
    assert any(lines[i] & lines[i + 1] for i in range(len(lines) - 1))  # some unit carried over


def test_learning_masking_patterns():
    text = "연락처 010-1234-5678, 메일 test@example.com, 번호 900101-1234567"
    masked = mask_pii(text)
    assert "[PHONE]" in masked and "[EMAIL]" in masked and "[ID_NUMBER]" in masked
    assert not contains_pii(masked)
    assert mask_pii("홍길동") == "홍길동"  # names are not detected: documented S1 limitation
