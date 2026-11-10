files: src/rag_research_agent/rag/lc_adapters.py, tests/test_lc_adapters.py, docs/ATTACH.ko.md, docs/E1_REPORT_2026-11-10.md
forbid: src/rag_research_agent/rag/brief.py, src/rag_research_agent/rag/library.py, src/rag_research_agent/rag/profile.py, .env*
effort: medium
coder: codex

# E1: LangChain 출구 — 다른 프로젝트에 붙이는 표준 인터페이스

## 목표 (대표 원칙: 모든 개발은 모듈로, Python + LangChain으로 다른 작업에 붙일 수 있게)
우리 부품을 LangChain 표준 객체로 감싼다. **새 로직 없음**, 기존 공개 함수를 감싸기만 한다.

## 내용 `rag/lc_adapters.py` (LangChain import는 이 파일 안에서만)
- `LibraryRetriever(BaseRetriever)`: `Library.search(query, k, mode)` → `Document(page_content=chunk.safe_text, metadata={chunk_id, document_id, title, score, rank})`. 필드: `library`, `k`, `mode`.
- `EqualizerRunnable`: `RunnableLambda` 기반. 입력 `{"text": ..., "task": ...}` 또는 문자열 → `Equalizer.from_profile(profile).brief(...)` → `{"brief": final_prompt_input, "status", "kept_ids", "excluded"}`. 프로필·예산은 생성 인자.
- `library_brief_tool(library, profile)`: LangChain `Tool`(`@tool` 또는 `StructuredTool`) — 이름 `research_brief`, 설명은 한국어 한 줄, 입력 질문 → 서재 검색 + Equalizer 브리프 문자열. 에이전트에 그대로 꽂을 수 있게.
- 체인 예: `LibraryRetriever | 문서 합치기 | EqualizerRunnable` (LCEL 파이프) 함수 `make_research_chain(library, profile)`.

## 문서 `docs/ATTACH.ko.md` (대표용, 짧게)
"다른 프로젝트에 붙이기" 3가지: ① 순수 Python(`Equalizer`, `Library`) ② LangChain(Retriever·Runnable·Tool, 코드 5줄 예) ③ LangGraph(P2b의 `build_graph` 서브그래프, P2b 완료 시). 수업 개념(Retriever, LCEL, Tool)과 대응표.

## 시험
가짜 임베더 서재로 Retriever가 Document를 돌려줌·메타데이터, Runnable 입력 두 형식, Tool 호출 결과 문자열, LCEL 체인 1회. Chroma 미설치면 해당 시험 `importorskip`(이유 명시).

## 공통 규칙
데이터(`data/golden_rules/**`, `profiles/*.json`, `data/equalizer/**`, `data/golden_sets/**`, `data/golden_retrieval/**`) 수정 금지, 구조 시험 통과(`KNOWN_DEBT` 증가 금지, LangChain·LangGraph·LangSmith import는 `rag/` 어댑터 파일에만), 기존 시험 기대값 수정·skip 금지, 네트워크·모델 다운로드·LLM 호출 금지. **끝나면 반드시 커밋.** 막히면 원인만 보고서에 적고 커밋 후 멈춤. 보고서: 구현·시험 통과 구분, 전체 시험 `n passed`.
