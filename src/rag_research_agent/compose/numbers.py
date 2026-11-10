"""Extract numeric values verbatim, with segment provenance; never calculate new values."""
from __future__ import annotations

MATURITY = "incubating"

import csv
from dataclasses import dataclass, asdict
from io import StringIO
import re

_VALUE = re.compile(r"(?<![\w.])(?P<value>[+−-]?\d[\d,]*(?:\.\d+)?)\s*(?P<unit>%p|%|bp|퍼센트|달러|조(?:\s*원)?|억(?:\s*원)?|만(?:\s*[원명건])?|원|명|건|배)(?![A-Za-z])")
_PERIOD = re.compile(r"(?:19|20)\d{2}년(?:\s*[1-4]분기|\s*\d{1,2}월)?|[1-4]분기|\d{1,2}월|최근\s*\d+개월")
_BASE = re.compile(r"전년\s*동기\s*대비|전년\s*대비|전기\s*대비|전월\s*대비|목표\s*대비")


@dataclass(frozen=True)
class NumberRow:
    segment_id: str
    indicator: str
    value: str
    unit: str
    period: str
    base: str
    raw: str


def extract_numbers(segments, source_text):
    rows = []
    for segment in segments:
        text = source_text[segment.start:segment.end]
        for match in _VALUE.finditer(text):
            prefix = text[:match.start()]
            periods = list(_PERIOD.finditer(prefix)) or list(_PERIOD.finditer(text))
            bases = list(_BASE.finditer(prefix)) or list(_BASE.finditer(text))
            indicator = re.search(r"([가-힣A-Za-z_]+?)(?:은|는|이|가)?\s*$", prefix)
            rows.append(NumberRow(segment.segment_id, indicator.group(1) if indicator else "",
                                  match["value"], match["unit"], periods[-1][0] if periods else "",
                                  bases[-1][0] if bases else "", match[0]))
    return rows


def to_markdown(rows):
    keys = list(NumberRow.__dataclass_fields__)
    lines = ["| 구간 | 지표 | 값 | 단위 | 기간 | 비교 기준 | 원문 |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for row in rows:
        data = asdict(row)
        lines.append("| " + " | ".join(data[k].replace("|", "\\|").replace("\n", " ") for k in keys) + " |")
    return "\n".join(lines)


def to_csv(rows):
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(NumberRow.__dataclass_fields__))
    writer.writeheader()
    writer.writerows(asdict(row) for row in rows)
    return stream.getvalue()
