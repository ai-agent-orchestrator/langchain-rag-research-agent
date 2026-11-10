files: src/rag_research_agent/rag/retry_graph.py, src/rag_research_agent/rag/query_rewrite.py, tests/test_retry_graph.py, docs/E2_REPORT_2026-11-10.md
forbid: src/rag_research_agent/rag/brief.py, src/rag_research_agent/rag/stages.py, .env*
effort: high
coder: codex

# E2: 근거 부족 시 재검색 루프 (RAG 그래프, LLM 없이 규칙으로)

## 전제
P2b(`rag/stages.py`, `rag/equalizer_graph.py`)와 C17(`observe/golden_v2.py`)이 커밋돼 있어야 한다. 없으면 보고서에 "전제 없음"만 적고 커밋 후 멈춘다.

## 내용
- `rag/query_rewrite.py` (순수 Python): 규칙 기반 질의 변형 — ① 접속어("그리고", "또", ",")로 나눠 하위 질문 ② 키워드만 남긴 질의(`core.lexical.lex_terms`) ③ 숫자·기간 표현 제거 질의. 변형 목록과 이유 반환.
- `rag/retry_graph.py` (LangGraph): `retrieve → grade → (충분: equalize → end) / (부족: rewrite → retrieve)`. 판정 = 최고 점수 ≥ τ(노브①) **그리고** 결과 조각 수 ≥ 1. 하위 질문 결과는 RRF로 합침. **최대 재시도 2회**(무한 루프 금지), 각 시도 기록을 상태에 남김. 끝까지 부족하면 `REQUEST_MORE`(생성 0회).
- 서재는 `Library` 객체를 주입. 그래프는 P2b 단계 함수를 재사용.

## 시험·평가
가짜 임베더 + `data/golden_retrieval/terms_v2.json`: multi_hop·comparison 문항에서 재검색 전후 Recall@k를 `golden_v2` 지표로 비교해 보고서에 표(합성 소규모, 통계적 결론 아님). 무한 루프 없음(시도 횟수 ≤ 3), 근거 없음 문항은 REQUEST_MORE.

## 공통 규칙
데이터(`data/golden_rules/**`, `profiles/*.json`, `data/equalizer/**`, `data/golden_sets/**`, `data/golden_retrieval/**`) 수정 금지, 구조 시험 통과(`KNOWN_DEBT` 증가 금지, LangChain·LangGraph·LangSmith import는 `rag/` 어댑터 파일에만), 기존 시험 기대값 수정·skip 금지, 네트워크·모델 다운로드·LLM 호출 금지. **끝나면 반드시 커밋.** 막히면 원인만 보고서에 적고 커밋 후 멈춤. 보고서: 구현·시험 통과 구분, 전체 시험 `n passed`.
