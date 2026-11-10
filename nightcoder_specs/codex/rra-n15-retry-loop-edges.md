files: tests/test_retry_graph_edges.py, docs/N15_REPORT_2026-11-10.md
forbid: src/rag_research_agent/observe/tracing.py, src/rag_research_agent/store/memvid_store.py, data/**, profiles/**, .env*
effort: low
coder: codex
status: ready
order: 150
repo: research

# N15: E2 재검색 루프 경계 시험

## 배경
`rag/retry_graph.py`와 `rag/query_rewrite.py`(E2)는 시험 4개만 있다(`tests/test_retry_graph.py`).

## 할 일
`tests/test_retry_graph_edges.py` (생산 코드 수정 금지, 기존 시험과 같은 fake 구성):
- 모든 변형이 원 질의와 같을 때(중복 제거 후 0개) 추가 시도 없이 종료하는지
- 숫자·기간만 있는 질의, 접속어만 있는 질의, 매우 긴 질의
- 최대 재시도(총 3회) 경계: 3번째에 근거가 생기면 성공, 아니면 REQUEST_MORE
- 시도 기록(질의·출처·점수·τ)의 개수와 순서
- 검색 장애가 중간 시도에서 나면 무근거로 바뀌지 않고 올라가는지
기대와 다른 동작은 시험을 맞추지 말고 보고서에 적는다.

## 공통 규칙
AGENTS.md를 먼저 읽고 따른다(개발 저장소는 Chroma, memvid 제외, 5절 NightCoder 레인 규칙).
데이터(`data/**`), `profiles/**`, 보호 파일, 기존 시험 기대값 수정·skip 금지, `KNOWN_DEBT` 증가 금지.
새 모듈은 기존 구조 시험(`tests/test_structure.py`)의 배치·성숙도 규칙을 따른다(같은 폴더의 기존 모듈 선언을 참고).
LangChain·LangGraph·LangSmith import는 `rag/` 어댑터 파일에만. 네트워크·모델 다운로드·실제 모델 실행·LLM 호출 금지.
`files:`에 없는 기존 파일은 수정하지 않는다(필요하면 보고서에 "후속 연결 필요"로 적는다).
시험 이름과 내용은 실제 동작을 검증해야 하며, 가짜 통과(무조건 참)를 만들지 않는다.
보고서: 구현 / 시험 / 입증하지 못한 것(미검증)을 구분한다. **끝나면 반드시 커밋.** 막히면 원인만 보고서에 적고 커밋 후 멈춤.
