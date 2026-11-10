# LangGraph 가드레일: RAG 노드 + 경로 통제

2026-11-10 KST · 작성: Claude · 상태: incubating, 합성 시험만

## 왜

기존 RAG 경로(검색 → 근거 판정 → 생성)는 한 방향입니다. 재검색, 일시 장애, 반복 실행이 섞이면
어디서 멈출지, 비용이 얼마나 쌓였는지 통제하는 곳이 없었습니다. 이번 구조는 RAG 컴포넌트를 바꾸지 않고
LangGraph `StateGraph`의 독립 노드로 넣은 뒤, 바깥 엣지에서 분류·반복·비용·오류를 통제합니다.

## 구조

```text
START → classify ──research──→ rag ──route_by_cost_and_health──→ finish → END
           │                    ├──retry (일시 장애)──→ rag
           └──smalltalk──→ finish └──kill (반복 한도 / 비용 / 노드 오류)──→ kill → END
```

| 노드·엣지 | 하는 일 | 하지 않는 일 |
| --- | --- | --- |
| `classify` (제1관문) | 요청을 research / smalltalk로 분류 | 원문을 외부로 보내지 않음(기본 규칙 라우터) |
| `rag` (메인 노드) | `GuidancePipeline.ainvoke` 호출, 횟수·비용 단위 누적 | 파이프라인 내부 수정, 예외 메시지 저장 |
| `route_by_cost_and_health` (제2관문) | 순수 Python 판정: retry / finish / kill | 모델 호출, 원격 로그 조회 |
| `finish` | 답변 반환(smalltalk면 고정 안내, 생성 0회) | |
| `kill` | 중단 코드 기록(LOOP_LIMIT, COST_LIMIT, NODE_ERROR) | 원인 메시지 노출 |

### 제2관문 판정 규칙

1. 노드 오류(일시 장애가 아닌 예외, 예: `DraftRejected`) → `kill` (`NODE_ERROR`). 다시 시도하지 않습니다.
2. 누적 비용 단위 > `max_cost` → `kill` (`COST_LIMIT`).
3. 일시 장애(`RetrievalUnavailable`, `InferenceCapacityExceeded`, `InferenceTimeout`)
   - 실행 횟수 < `max_loops` → `retry`
   - 그 외 → `kill` (`LOOP_LIMIT`)
4. 그 외 → `finish`

기본값: `max_loops=3`, `max_cost=15.0`. 첨부 설계안(루프 > 3, 비용 > 15)과 같은 기준입니다.

### 비용 단위

모델 토큰이나 금액이 아니라 **로컬 추정 단위**입니다. 기본: RAG 호출 1회당 0.1, 생성 호출 1회당 1.0.
실제 백본(Llama 등)을 정하면 `cost=` 함수에 실제 토큰 수 계산을 넣으면 됩니다. LangSmith로 비용을 읽지 않습니다.
서비스 경로는 원격 tracing을 끄는 원칙(`observe/tracing.py`)을 따르기 때문입니다.

## 보안 순서

- 기본 라우터(`rule_router`)는 길이와 인사말 패턴만 봅니다. 어디로도 데이터를 보내지 않습니다.
- LLM 라우터(`structured_router(model, masker)`)는 `with_structured_output(RouteDecision)`을 쓰고,
  **마스킹된 텍스트만** `<DATA>` 블록으로 보냅니다. masker 없이는 만들 수 없습니다. 모델 오류나 이상한 출력이면 규칙 라우터로 되돌아갑니다.
- 입력 정책 검사, 마스킹, 인용 검증은 지금처럼 `GuidancePipeline` 안에서 실행됩니다.
- 모든 실행은 `serving_trace_guard()` 안에서 돕니다. 시험에서 tracing 환경변수를 켜 둔 상태로도 업로드 시도 0회를 확인했습니다.

## 사용

```python
from rag_research_agent.rag.guardrail_graph import GuardrailRunner, GuardrailLimits
from rag_research_agent.rag.http_mapping import validate_request, map_outcome

runner = GuardrailRunner(pipeline.ainvoke, limits=GuardrailLimits(max_loops=3, max_cost=15.0))

bad = validate_request(body)            # 400은 파이프라인 전에
if bad:
    return bad
try:
    result = await runner.ainvoke(body)  # GuardrailResult: reply, route, stop_code, loops, cost_units, path
    return map_outcome(result)           # (status, body, headers)
except Exception as exc:
    return map_outcome(exc)
```

설정 값은 `rag/settings_loader.py`의 `load_settings()`로 읽을 수 있습니다(N7).

## HTTP 매핑 (`rag/http_mapping.py`, N11)

| 결과 | 상태 | 본문 |
| --- | --- | --- |
| 답변(OK), 근거 없음(REQUEST_MORE) | 200 | 기존 `GuidanceReply.to_dict()` |
| 입력 정책 차단(BLOCKED) | 200 | 기존 `{"blocked": true, "reasonCode", "answer"}` |
| 검색 장애, 서킷 open | 503 + `Retry-After: 30` | `{"error": "RETRIEVAL_UNAVAILABLE"}` |
| 작업 슬롯 부족 | 503 + `Retry-After: 5` | `GENERATION_CAPACITY_EXCEEDED` |
| 추론 시간 초과 | 504 | `INFERENCE_TIMEOUT` |
| 백본 미설정 / RAG 꺼짐 | 503 | `BACKBONE_NOT_CONFIGURED` / `RAG_DISABLED` |
| 모델 초안 거절 | 502 | `AI_DRAFT_REJECTED` |
| 가드레일 한도 중단 | 503 | `GUARDRAIL_STOPPED` (원인이 일시 장애면 그 장애 코드) |
| 잘못된 요청(파이프라인 전) | 400 | `INVALID_REQUEST` |
| 그 외 예외 | 500 | `INTERNAL_ERROR` |

오류 본문에는 고정 코드만 들어갑니다. 예외 메시지, 질의 원문, 스택은 넣지 않습니다.

## 검증한 것과 아닌 것

- 검증: 시험 `tests/test_guardrail_graph.py` 25개. 경로별 동작, 재시도·한도, 비용 중단, 순수 함수 판정,
  라우터 마스킹, 실제 `GuidancePipeline`(fake 모델·검색)을 노드로 넣은 끝-끝 실행과 tracing 업로드 0회.
- 미검증: 실제 Llama·실제 E5·실제 Chroma에서의 동작, 실제 토큰 비용, 실제 LLM 라우터의 분류 정확도, 웹 서버 연결.
- 결정 필요: 정책 차단을 200으로 둘지 422로 바꿀지, `AI_DRAFT_REJECTED`를 502로 둘지(설계 문서는 상태 코드를 정하지 않음).
