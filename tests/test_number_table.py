import csv
from io import StringIO

from rag_research_agent.compose.numbers import extract_numbers, to_csv, to_markdown
from rag_research_agent.ingest.sentences import SentenceChunker


def rows(text):
    result = extract_numbers(SentenceChunker().split(text), text)
    assert all(row.raw in text and row.value in row.raw and row.unit in row.raw for row in result)
    return result


def test_percentage_points_period_and_comparison():
    data = rows("2026년 1분기 전년 동기 대비 성장률은 2.5%, 차이는 0.3%p다.")
    assert [(r.value, r.unit) for r in data] == [("2.5", "%"), ("0.3", "%p")]
    assert data[0].indicator == "성장률" and data[0].period == "2026년 1분기"
    assert all(r.base == "전년 동기 대비" for r in data)


def test_revisions_amounts_and_no_numbers():
    data = rows("최근 3개월 속보치는 2.1%, 확정치는 2.3%다. 매출은 1,200억 원이고 건수는 32건이다.")
    assert [(r.value, r.unit) for r in data] == [("2.1", "%"), ("2.3", "%"), ("1,200", "억 원"), ("32", "건")]
    assert data[0].period == "최근 3개월"
    assert rows("수치가 없는 합성 문장이다.") == []
    assert "수치" not in to_csv(data)
    assert list(csv.DictReader(StringIO(to_csv(data))))[0]["value"] == "2.1"
    assert "| s01 |" in to_markdown(data)
