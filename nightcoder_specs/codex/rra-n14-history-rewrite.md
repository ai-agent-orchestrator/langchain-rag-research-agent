files: src/rag_research_agent/rag/history_rewrite.py, tests/test_history_rewrite.py, docs/N14_REPORT_2026-11-10.md
forbid: src/rag_research_agent/observe/tracing.py, src/rag_research_agent/store/memvid_store.py, data/**, profiles/**, .env*
effort: medium
coder: codex
status: ready
order: 140
repo: research

# N14: 대화 이력 기반 질의 재작성 (규칙 기반, LLM 없음)

## 배경
후속 질문("그건 언제부터야?")은 이전 대화 없이 검색하면 근거를 못 찾는다. E2의 `rag/query_rewrite.py`는 단일 질의 분해다.

## 할 일
`rag/history_rewrite.py` (LLM·네트워크 없음):
- 입력: 최근 대화 턴 목록(사용자 질의만, 최대 N턴)과 현재 질의. 출력: 재작성 질의 + 적용한 규칙 이유 목록.
- 규칙: 지시어(그거, 그건, 이것, 해당, 위의 등)나 매우 짧은 질의일 때 직전 질의의 핵심어(기존 lex_terms 재사용)를 덧붙임.
  지시어가 없고 충분히 긴 질의는 그대로. 개인정보 마스킹은 이 모듈 바깥 책임임을 docstring에 적는다.
- 재작성 결과가 원래 질의를 포함하도록 한다(정보 손실 금지).
기존 GuidancePipeline에 연결하지 않는다.

## 시험 `tests/test_history_rewrite.py`
지시어 감지, 이력 없음, 긴 질의 불변, 최대 턴 제한, 이유 목록.

## 공통 규칙
AGENTS.md를 먼저 읽고 따른다(개발 저장소는 Chroma, memvid 제외, 5절 NightCoder 레인 규칙).
데이터(`data/**`), `profiles/**`, 보호 파일, 기존 시험 기대값 수정·skip 금지, `KNOWN_DEBT` 증가 금지.
새 모듈은 기존 구조 시험(`tests/test_structure.py`)의 배치·성숙도 규칙을 따른다(같은 폴더의 기존 모듈 선언을 참고).
LangChain·LangGraph·LangSmith import는 `rag/` 어댑터 파일에만. 네트워크·모델 다운로드·실제 모델 실행·LLM 호출 금지.
`files:`에 없는 기존 파일은 수정하지 않는다(필요하면 보고서에 "후속 연결 필요"로 적는다).
시험 이름과 내용은 실제 동작을 검증해야 하며, 가짜 통과(무조건 참)를 만들지 않는다.
보고서: 구현 / 시험 / 입증하지 못한 것(미검증)을 구분한다. **끝나면 반드시 커밋.** 막히면 원인만 보고서에 적고 커밋 후 멈춤.
