files: src/rag_research_agent/retrieve/breaker.py, tests/test_retrieval_breaker.py, docs/N6_REPORT_2026-11-10.md
forbid: src/rag_research_agent/observe/tracing.py, src/rag_research_agent/store/memvid_store.py, data/**, profiles/**, .env*
effort: medium
coder: codex
status: hold   # 2026-11-10: Claude가 claude/n6-n7-n11 브랜치에서 개발
order: 60
repo: research

# N6: 검색 장애 서킷브레이커 부품 (연결은 하지 않음)

## 배경
검색 장애는 RetrievalUnavailable로 올라간다(`core/contracts.py`). 장애가 반복될 때 빠르게 실패하고 회복을 감지하는 부품이 없다.

## 할 일
`retrieve/breaker.py`: 표준 라이브러리만 사용하는 CircuitBreaker.
- 상태 closed / open / half-open. 연속 실패 n회(기본 5)에 open, open 동안 호출은 즉시 RetrievalUnavailable(원인: breaker open),
  쿨다운(기본 30초) 뒤 half-open에서 1회 시험 호출, 성공하면 closed, 실패하면 다시 open.
- RetrievalUnavailable만 실패로 센다. 다른 예외(프로그래밍 오류)는 그대로 올리고 카운트하지 않는다.
- 시계(clock)를 주입받아 시험에서 시간을 조작한다. 스레드 안전.
- 상태 변화는 원문 없이 상태·횟수만 기록하는 콜백을 받을 수 있다.
기존 GuidancePipeline이나 Library에 연결하지 않는다(보고서에 연결 위치 제안만).

## 시험 `tests/test_retrieval_breaker.py`
상태 전이 전부, 다른 예외 비계수, 쿨다운 경계, half-open 동시 호출 1회만 통과, 스레드 동시 호출.

## 공통 규칙
AGENTS.md를 먼저 읽고 따른다(개발 저장소는 Chroma, memvid 제외, 5절 NightCoder 레인 규칙).
데이터(`data/**`), `profiles/**`, 보호 파일, 기존 시험 기대값 수정·skip 금지, `KNOWN_DEBT` 증가 금지.
새 모듈은 기존 구조 시험(`tests/test_structure.py`)의 배치·성숙도 규칙을 따른다(같은 폴더의 기존 모듈 선언을 참고).
LangChain·LangGraph·LangSmith import는 `rag/` 어댑터 파일에만. 네트워크·모델 다운로드·실제 모델 실행·LLM 호출 금지.
`files:`에 없는 기존 파일은 수정하지 않는다(필요하면 보고서에 "후속 연결 필요"로 적는다).
시험 이름과 내용은 실제 동작을 검증해야 하며, 가짜 통과(무조건 참)를 만들지 않는다.
보고서: 구현 / 시험 / 입증하지 못한 것(미검증)을 구분한다. **끝나면 반드시 커밋.** 막히면 원인만 보고서에 적고 커밋 후 멈춤.
