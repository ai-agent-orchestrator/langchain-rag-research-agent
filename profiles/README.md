# 필터 프로필 (내 필터 만들기)

프로필 파일 하나 = 분야 필터 하나. 누구든 `_template.json`을 복사해 이름과 내용을 바꾸면 바로 쓸 수 있다. 코드는 고치지 않는다.

```python
from rag_research_agent import Equalizer
brief, trace = Equalizer.from_profile("profiles/litigation.json").brief(text, budget=400)
# 또는 이름만: Equalizer.from_profile("litigation")
```

비교 보드: `python scripts/filter_board.py --profiles litigation my_filter --budget 300` → `.runs/board.html`

## 항목

| 항목 | 뜻 | 없으면 |
| --- | --- | --- |
| `name`, `label`, `description` | 이름, 표시 이름, 설명 | 파일 이름 |
| `rules` | 골든룰 파일 경로(이 파일 기준) 또는 `"default"` | 공통 150개 |
| `packs` | 켤 분야 묶음 (`macro`, `geopolitics`, `tech`, `defense`, `legal`) | 없음 |
| `knobs` | `similarity`(창), `edge_weight`(방패): `Low`/`Mid`/`High` 또는 0~1 | Mid / High |
| `focus` | 기본 집중 키워드 `{"키워드": 가중치}` (최대 5) | 없음 |
| `external_allowed` | 외부 공급자 허용 여부 | 허용 |
| `ontology.classes` | 이 분야의 문장 분류. **위에서부터** 먼저 맞는 분류가 붙음. `cues`(포함 표현), `patterns`(정규식) | 전부 Unclassified |
| `ontology.diet_order` | 예산 초과 시 **먼저 빼는** 분류 순서 | Unclassified만 |
| `ontology.never_remove` | 절대 빼지 않는 분류 | 없음 |

정의하지 않은 분류 이름을 `diet_order`·`never_remove`에 쓰면 불러올 때 오류가 난다.

## 제공 프로필 (v1 초안, 보정 전)

`research`(DESIGN 기본 순서), `litigation`(감량 순서는 O1 대표 결정 대기), `politics`(레드라인 보호), `macro`, `tech`, `defense`(전략·정책 수준), `counseling`(위험 신호 항상 보호, 외부 거부).

## 고치는 요령

보드에서 중요한 문장이 빠졌으면 `trace.rows`의 `label`을 본다. 미분류(Unclassified)로 잡혀 먼저 빠졌다면 그 문장을 잡을 분류를 추가하거나 기존 분류의 `cues`를 늘린다. 한 번에 하나만 바꾸고 보드를 다시 돌린다.
