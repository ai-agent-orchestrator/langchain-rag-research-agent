import json
from pathlib import Path
import re

import pytest
from rag_research_agent.ingest.sentences import SentenceChunker


def pieces(text):
    segs = SentenceChunker().split(text, "synthetic")
    assert [s.segment_id for s in segs] == [f"s{n:02d}" for n in range(1, len(segs) + 1)]
    values = [text[s.start:s.end] for s in segs]
    assert all(value == value.strip() and value for value in values)
    assert all(s.source == "synthetic" for s in segs)
    return values


@pytest.mark.parametrize("text,expected", [
    ("금리는 3.5%다. 버전은 v2.1이다.", ["금리는 3.5%다.", "버전은 v2.1이다."]),
    ("2026. 11. 9. 발표했다. 다음 날이다.", ["2026. 11. 9. 발표했다.", "다음 날이다."]),
    ('"완료했다." 고 말했다. 다음이다.', ['"완료했다." 고 말했다.', "다음이다."]),
    ('"완료했다." 다음이다.', ['"완료했다."', "다음이다."]),
    ("사례(예: A. B.)를 살폈다. 다음이다.", ["사례(예: A. B.)를 살폈다.", "다음이다."]),
    ("Dr. Kim works in U.S. office. Inc. results follow.", ["Dr. Kim works in U.S. office.", "Inc. results follow."]),
    ("- 첫째다. 설명이다.\n1. 둘째다. 추가다.\n• 셋째다.", ["- 첫째다. 설명이다.", "1. 둘째다. 추가다.", "• 셋째다."]),
    (" \n\n  첫째。 둘째！ 셋째？  \n", ["첫째。", "둘째！", "셋째？"]),
])
def test_korean_offsets_and_boundaries(text, expected):
    assert pieces(text) == expected


def test_existing_synthetic_sets_keep_segment_counts():
    root = Path(__file__).resolve().parents[1]
    for path in (root / "data/golden_sets").glob("*.json"):
        text = json.loads(path.read_text(encoding="utf-8"))["draft"]
        old = [s for s in re.split(r"(?<=[.!?。])\s+|\n+", text) if s.strip()]
        assert len(pieces(text)) == len(old), path.name
