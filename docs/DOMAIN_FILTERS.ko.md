# 도메인 필터: LangGraph 가드레일의 교체 부품

2026-11-11 KST · 상태: 계약 + 리서치 필터 v1 구현 · 전체 그래프 설계: `docs/RESEARCH_GRAPH_DESIGN.ko.md`

## 왜 도메인별로 나누는가

LLM이 틀리는 지점이 도메인마다 다르다. 그래서 그래프 모양(분류 → 로컬 검색 → 규정 필터)은 고정하고,
**State 칸과 필터 기준만 도메인별로 바꿔 끼운다.**

| 도메인 | 핵심 위험(환각 유형) | State·필터 설계 핵심 | 상태 |
| --- | --- | --- | --- |
| 리서치·개념 | 인과관계 유실, 피상적 일반화, 출처 없는 수치 | 온톨로지 추출 + 원문 대조 검수 루프 + 고밀도 필터 | **v1 구현** |
| 법률 | 사건 시차 뒤섞임, 없는 조항·폐지 판례 인용 | 시차 로그 리듀서 + 검증된 조항 강제 주입 + 사건 유형별 경로 격리 | 예정 |
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
