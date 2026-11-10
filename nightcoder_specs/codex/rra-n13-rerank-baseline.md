files: src/rag_research_agent/retrieve/rerank.py, tests/test_rerank.py, docs/N13_REPORT_2026-11-10.md
forbid: src/rag_research_agent/observe/tracing.py, src/rag_research_agent/store/memvid_store.py, data/**, profiles/**, .env*
effort: medium
coder: codex
status: ready
order: 130
repo: research

# N13: 재순위화(reranker) 인터페이스와 모델 없는 기준선

## 배경
근거 판정 개선 후보로 reranker가 있다. 실제 reranker 모델은 쓰지 않는다. 나중에 모델을 끼울 수 있게 인터페이스와 기준선만 만든다.

## 할 일
`retrieve/rerank.py`:
- Protocol `Reranker.rerank(query, chunks) -> list[(chunk, score)]`. 기존 Chunk/검색 결과 타입을 소스에서 확인해 사용.
- 기준선 1: 원래 순위 유지(IdentityReranker). 기준선 2: 질의 단어 겹침(기존 `core/lexical.py`·lex_terms 재사용) 기반 재정렬,
  동점이면 원래 순위 유지(안정 정렬).
- 점수는 0~1로 정규화하고 "확률 보정 아님"을 docstring에 적는다.
기존 검색 경로·Library에 연결하지 않는다.

## 시험 `tests/test_rerank.py`
Identity 불변, 겹침 재정렬, 안정 정렬, 빈 입력, 한글 질의.

## 공통 규칙
AGENTS.md를 먼저 읽고 따른다(개발 저장소는 Chroma, memvid 제외, 5절 NightCoder 레인 규칙).
데이터(`data/**`), `profiles/**`, 보호 파일, 기존 시험 기대값 수정·skip 금지, `KNOWN_DEBT` 증가 금지.
새 모듈은 기존 구조 시험(`tests/test_structure.py`)의 배치·성숙도 규칙을 따른다(같은 폴더의 기존 모듈 선언을 참고).
LangChain·LangGraph·LangSmith import는 `rag/` 어댑터 파일에만. 네트워크·모델 다운로드·실제 모델 실행·LLM 호출 금지.
`files:`에 없는 기존 파일은 수정하지 않는다(필요하면 보고서에 "후속 연결 필요"로 적는다).
시험 이름과 내용은 실제 동작을 검증해야 하며, 가짜 통과(무조건 참)를 만들지 않는다.
보고서: 구현 / 시험 / 입증하지 못한 것(미검증)을 구분한다. **끝나면 반드시 커밋.** 막히면 원인만 보고서에 적고 커밋 후 멈춤.
