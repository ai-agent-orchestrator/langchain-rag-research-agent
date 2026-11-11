# 계측 보드 설계 — 4대 지표와 이벤트 스키마

> 필수 설계 요건. 에이전트가 돌아가는 것을 넘어 **내부 상태·루프 회전수·토큰 원가·환각 차단**을 실시간으로 계측해 도메인(법률·의료·리서치 등 3~5개) 파이프라인을 데이터로 튜닝한다 (Data-Driven Harness Tuning). Spring Boot — FastAPI — LangGraph 3단 백엔드와 맞물리도록 이벤트 하나를 단위로 한다.

## 1. 보드 4대 패널

| 패널 | 측정 지표 | 튜닝 활용 |
|---|---|---|
| 1. 실행 궤적 (Workflow Trace) | 실행 경로 `retrieve → grade → rewrite → …`; 종료 유형: 정상 `END` / 안전 종료 `give_up` / 강제 차단 `cutoff` | 어떤 질문 유형에서 rewrite 루프가 많이 도는지 보고 검색 프롬프트·채점 기준을 조정 |
| 2. 비용 통제 (Cost Control) | 모델별 호출 수(SLM 심판 vs Flagship 작문); 입력/출력 토큰 분리, 건당 예상 원가(원) | 건당 평균 원가가 목표(예: 1.5원)를 넘는지 감시, Fast Track(단순 RAG) / Deep Track(자기 교정) 라우팅 비율 조절 |
| 3. 환각 방어 (Guardrail Audit) | RelevanceGrade 탈락률; GroundedGrade 반려 사유(`reason`) 로그(수치·조문 오류) | 도메인별로 어디서 숫자를 자주 틀리는지, 채점기가 너무 깐깐해 보조 조문까지 버리는지 진단 |
| 4. 성능·레이턴시 (Latency) | 노드별 소요 시간(ms): 검색, 병렬 채점(`abatch`), 최종 생성; 첫 토큰 도달 시간(TTFT) | 병목 노드 식별 → 비동기 병렬화·경량 모델 교체 결정 |

## 2. 이벤트 스키마 (1 run = 1 `run` + N `node` 이벤트)

```json
{
  "run_id": "uuid", "domain": "research|legal|medical|life", "track": "fast|deep",
  "config": "graph_full", "dataset": "cases.ko.v2", "sha": "abc1234",
  "path": ["retrieve", "grade", "rewrite", "retrieve", "grade", "generate"],
  "end_type": "END|give_up|cutoff", "loops": {"rewrite": 1, "gap": 0, "verify": 0},
  "calls": {"slm": 4, "flagship": 1},
  "tokens": {"in": 1320, "out": 210}, "cost_krw": 1.2, "ttft_ms": 740, "total_ms": 5900,
  "grade": {"docs_in": 8, "docs_kept": 5, "relevance_drop_rate": 0.375},
  "guard": [{"gate": "grounded", "code": "UNSUPPORTED_NUMBER", "reason": "…", "span": "18%"}],
  "nodes": [{"name": "retrieve", "ms": 120, "tokens_in": 0, "tokens_out": 0, "model": null}]
}
```

- 토큰은 입력/출력을 분리해 기록하고, 원가는 단가표(`pricing.json`)로 환산한다. 규칙 기반 노드는 shadow token(추정)임을 `estimated: true`로 표시.
- `guard[].code`는 필터 코드(`UNSUPPORTED_NUMBER`, `GAP:<metric>` 등)를 그대로 쓴다 — 도메인 필터가 바뀌어도 보드는 같은 스키마로 읽는다.
- Spring Boot는 `run_id`로 요청과 이벤트를 연결하고, FastAPI가 LangGraph 노드 콜백에서 이벤트를 수집해 JSONL로 쌓는다(현재 보드는 `runs.jsonl` → HTML).

## 3. 구현 순서
1. 노드 콜백으로 `nodes[]`와 `path` 수집 (현재 `result.path/cost/log`를 확장).
2. 종료 유형·루프 회전수·호출 수·원가 필드 추가.
3. 보드 4패널 렌더 (`research_board.py`를 도메인 공통으로 일반화, 패널 단위 분리).
4. 목표선(원가 1.5원, 응답 6초 등)을 설정 파일로 두고 초과 시 경고 표시.
