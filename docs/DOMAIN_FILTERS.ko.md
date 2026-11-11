# 도메인 필터: LangGraph 가드레일의 교체 부품

2026-11-11 KST · 상태: 계약 + 리서치 필터 v1 구현 + 법률 필터 뼈대 구현 · 전체 그래프 설계: `docs/RESEARCH_GRAPH_DESIGN.ko.md`

## 왜 도메인별로 나누는가

LLM이 틀리는 지점이 도메인마다 다르다. 그래서 그래프 모양(분류 → 로컬 검색 → 규정 필터)은 고정하고,
**State 칸과 필터 기준만 도메인별로 바꿔 끼운다.**

| 도메인 | 핵심 위험(환각 유형) | State·필터 설계 핵심 | 상태 |
| --- | --- | --- | --- |
| 리서치·개념 | 인과관계 유실, 피상적 일반화, 출처 없는 수치 | 온톨로지 추출 + 원문 대조 검수 루프 + 고밀도 필터 | **v1 구현** |
| 법률 | 사건 시차 뒤섞임, 없는 조항·폐지 판례 인용 | 설계: 시차 로그 리듀서 + 검증된 조항 강제 주입 + 사건 유형별 경로 격리 | **뼈대 구현** (키워드 분기·조문/날짜 규칙, 합성 시험 정의) |
| 의료 | 진단 단정, 금기 약물 누락, 가이드라인 불일치 | 응급 여부 입력 필터 + 가이드라인 근거 매핑 + 면책·전문의 권고 출력 | 예정 |
| 로컬 비즈니스·행정 | 지역·기관 예외 무시, 구버전 양식 | 관할·조건 분기 + 최신 규정 DB 강제 + 구비서류 체크리스트 | 예정 |

## 계약 (`guard/domain_filter.py`)

```python
class DomainFilter(Protocol):
    name: str; version: str
    def check_input(self, text) -> InputDecision        # allowed, code, branch
    def verify(self, answer, evidence, branch) -> Verdict  # ok, issues(code, retryable), scores
    def finalize(self, answer, branch) -> str            # 고지문·면책 등
```

- 순수 Python. 모델·네트워크·다른 모듈 import 없음. 결과는 **코드만** 돌려준다(원문 없음).
- 규칙을 바꾸면 `version`을 올린다. 결과를 나중에 설명할 수 있어야 한다.
- 등록: `register("legal", LegalFilter)`. 사용: `GuardrailRunner(rag, domain=get_filter("research"))`.

## 그래프에 끼우면 생기는 것 (`rag/guardrail_graph.py`)

- `screen`: `check_input`이 막으면 RAG를 부르지 않고 BLOCKED로 끝난다.
- `verify`: 생성된 답변(OK)만 검수한다. 고칠 수 있는 문제(`retryable`)면 예산 안에서 다시 생성하고,
  끝내 통과하지 못하면 **검증 안 된 글을 내보내지 않고** `VERIFY_FAILED` 안전 답변을 준다.
- `domain_log`: 관문 판정 코드가 리듀서로 누적된다(`SCREEN:PASS`, `VERIFY:FAIL:CAUSAL_LOSS` …).
- RAG 호출이 `(reply, evidence_texts)`를 돌려주면 검수가 그 근거와 대조한다
  (`GuidancePipeline.ainvoke_with_evidence`). 근거가 없으면 `NO_EVIDENCE`(재시도 안 함).
- 한도: `GuardrailLimits(max_loops=3, max_cost=15.0, max_verify_rounds=2)`.

## 리서치 필터 v1 규칙 (`guard/research_filter.py`, `research-filter/1`)

| 코드 | 판정 | 재시도 |
| --- | --- | --- |
| `UNSUPPORTED_NUMBER` | 답변의 숫자가 근거에 없음(인용 표시 `[1]`은 제외) | 예 |
| `UNGROUNDED_SENTENCE` | 문장의 내용어 중 근거에 있는 비율 < 0.5 | 예 |
| `CAUSAL_LOSS` | 근거에 인과 표현이 있는데 답변에 없음 | 예 |
| `CONSTRAINT_DROPPED` | 근거의 조건·예외가 답변에서 빠짐 | 예 |
| `LOW_DENSITY` | 구체 문장(수치·인과·조건·근거 용어 3개 이상) 비율 < 0.5 | 예 |
| `NO_EVIDENCE` | 대조할 근거 없음 | 아니오 |

한계(미검증): 규칙 기반이라 동의어·바꿔 말하기를 근거 없음으로 볼 수 있고, 인과·조건 판정은 표현 단위다.
실제 모델 출력과 실제 문서로 오탐률을 아직 재지 않았다. 다음 단계는 claim 단위 대조다(설계 문서 4·8절).

## 법률 필터 뼈대 (`guard/legal_filter.py`, `legal-filter/1`)

명시적으로 선택할 때만 적용하며 기본 그래프·기본 도메인은 변경하지 않는다.

```python
from rag_research_agent.guard.legal_filter import LegalFilter  # import 시 등록
from rag_research_agent.guard.domain_filter import get_filter

runner = GuardrailRunner(rag, domain=get_filter("legal"))
```

- 입력: 공백은 `EMPTY_INPUT`으로 차단한다. 키워드는 형사(`criminal`) → 가사(`family`) →
  민사(`civil`) 순서로 먼저 일치하는 분기를 선택하고 나머지는 `other`다. 혼합 사건도 이 우선순위다.
- `UNSUPPORTED_STATUTE`: 답변의 `제\d+조` 표기가 근거에 없으면 반환한다. 중복 표기는 한 번 센다.
- `REPEALED_CITED`: 근거의 같은 절에 `폐지`·`삭제`·`구법`과 함께 나온 조문을 답변이 인용하면 반환한다.
  절은 줄바꿈·쉼표·세미콜론 또는 문장부호 뒤 공백으로 나눈다. 다른 절·다른 문서로 상태를 전파하지 않는다.
- `TIMELINE_MIXED`: 근거와 답변에 공통인 유효한 전체 날짜 두 개 이상의 언급 순서가 다르면 반환한다.
  `2025-01-02`와 `2025년 1월 2일`을 같은 날짜로 보고 중복은 첫 언급만 남긴다.
  근거 순서는 문서 튜플 순서와 문서 내 언급 순서다. 단일 날짜·날짜 없는 답변은 이 규칙으로 차단하지 않는다.
- 위 세 오류와 `EMPTY_ANSWER`는 재시도 가능하다. 근거가 없거나 공백뿐이면 `NO_EVIDENCE`로 안전 종료한다.
- 통과한 답변에는 `법률 자문이 아닙니다`를 추가한다. 로그·Verdict에는 코드와 개수만 남긴다.

등록은 법률 모듈 import 시 `register("legal", LegalFilter)`와 공유 `BUILTINS` 항목 추가로 수행한다.
모듈을 import하기 전 최초 `get_filter("legal")` 자동 로딩은 **후속 연결 필요**다.
중앙 `domain_filter.py`는 R18의 허용 변경 범위 밖이므로 수정하지 않았다.

한계·미검증: 법령명·항·호·시행일·판례 유효성을 구분하지 않는다. 같은 절의 여러 조문에는 상태가 함께 적용된다.
부정문(예: 삭제되지 않음), 과거 법률의 정당한 설명, 날짜와 사건의 대응·날짜 누락·근거에 없는 날짜,
역순 회고 표현은 의미를 해석하지 않는다. 정렬되지 않은 근거 순서도 오탐을 만들 수 있다.
사건 유형 branch는 기존 그래프 State에 기록되며 검색 경로 격리·시차 로그 리듀서·검증 조항 주입은
**후속 연결 필요**다. 합성 규칙·실제 그래프 교체 시험의 실행 및 실제 법률 문서 품질은 미검증이다.
실행 제약과 시험 명령은 [R18 보고서](R18_REPORT_2026-11-11.md)에 기록한다.
