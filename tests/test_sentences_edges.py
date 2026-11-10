"""Synthetic boundary cases through the real SentenceChunker; no model or store."""

import pytest

from rag_research_agent.ingest.sentences import SentenceChunker


@pytest.mark.parametrize("text, expected", [
    ("마침표 없는 문장", ["마침표 없는 문장"]),
    ("  끝맺음 없음\t", ["끝맺음 없음"]),
    ("첫 줄\n둘째 줄", ["첫 줄", "둘째 줄"]),
    ("첫 줄\r\n\r\n둘째 줄\r셋째 줄", ["첫 줄", "둘째 줄", "셋째 줄"]),
    ("값은 0.25다. 다음은 12.50이다.", ["값은 0.25다.", "다음은 12.50이다."]),
    ("Dr. Lee met Mr. Park. Done.", ["Dr. Lee met Mr. Park.", "Done."]),
    ("Use e.g. apples and i.e. fruit. Done.", ["Use e.g. apples and i.e. fruit.", "Done."]),
    ("Items etc. Next item.", ["Items etc. Next item."]),
    ("1. 첫 문장. 설명.\n2. 다음 항목", ["1. 첫 문장. 설명.", "2. 다음 항목"]),
    ("  123. 항목. 설명.\n끝.", ["123. 항목. 설명.", "끝."]),
    ('"A. B." Next.', ['"A. B."', "Next."]),
    ('"완료."라고 말했다. 다음.', ['"완료."라고 말했다.', "다음."]),
    ("“A. B.” Next.", ["“A. B.”", "Next."]),
    ("앞 (A. B.) 뒤. 다음.", ["앞 (A. B.) 뒤.", "다음."]),
    ("앞 ([A. B.]) 뒤. 다음.", ["앞 ([A. B.]) 뒤.", "다음."]),
    ("끝... 다음?! 마지막", ["끝...", "다음?!", "마지막"]),
])
def test_sentence_boundary_pieces_preserve_original_text(text, expected):
    segments = SentenceChunker().split(text, "synthetic")

    assert [text[segment.start:segment.end] for segment in segments] == expected
    assert [segment.segment_id for segment in segments] == [
        f"s{number:02d}" for number in range(1, len(expected) + 1)
    ]
    assert all(segment.source == "synthetic" for segment in segments)
    assert all(0 <= segment.start < segment.end <= len(text) for segment in segments)
    assert all(left.end <= right.start for left, right in zip(segments, segments[1:]))


@pytest.mark.parametrize("text", ["", "\n", "\r\n", "\n\r\n\r", " \t ", " \n\t\r\n "])
def test_empty_or_whitespace_only_input_has_no_segments(text):
    assert SentenceChunker().split(text) == []


@pytest.mark.parametrize("text, offsets, expected", [
    ("  반복.\r\n\t반복.  ", [(2, 5), (8, 11)], ["반복.", "반복."]),
    ("\n  😀가.  나\t\r\n끝", [(3, 6), (8, 9), (12, 13)], ["😀가.", "나", "끝"]),
    ("\tA  B.\t C\n", [(1, 6), (8, 9)], ["A  B.", "C"]),
])
def test_exact_offsets_reference_original_without_normalization(text, offsets, expected):
    segments = SentenceChunker().split(text)

    assert [(segment.start, segment.end) for segment in segments] == offsets
    assert [text[start:end] for start, end in offsets] == expected
    assert all(segment.source == "draft" for segment in segments)
