files: src/rag_research_agent/rag/langsmith_export.py, scripts/export_langsmith.py, tests/test_langsmith_export.py, docs/LANGSMITH_EVAL.ko.md, docs/E3_REPORT_2026-11-10.md
forbid: src/rag_research_agent/observe/tracing.py, .env*
effort: medium
coder: codex

# E3: 골든셋·평가 결과를 LangSmith 형식으로 내보내기 (업로드는 대표 실행 시만)

## 배경
수업에서 LangSmith 데이터셋·평가자·실험을 배운다. 우리 원칙은 서비스에서 LangSmith 끔, 평가에서만 허용 필드(`observe/tracing.py`). 그래서 **로컬에서 평가하고, LangSmith 형식으로 내보내기만** 한다.

## 내용
- `rag/langsmith_export.py`: 골든셋 v2 → LangSmith 데이터셋 예제 목록(`inputs={"question"}`, `outputs={"answerable", "relevant":[{source, grade, quote}]}`, `metadata={type, split, id}`)을 JSONL로. 평가 결과(C17 실행 산출물) → 실험 결과 JSONL(질문 ID별 지표). **합성 골든셋만 허용**: 파일의 `note`/이름에 SYNTHETIC 표시가 없으면 거절.
- `scripts/export_langsmith.py --set ... --out .runs/langsmith/`: 파일만 만든다. `--upload` 옵션은 `observe.tracing.evaluation_client`를 쓰되 **대표가 직접 실행할 때만**: API 키가 없으면 안내 후 종료, 시험에서는 절대 호출하지 않음(가짜 클라이언트 주입).
- 업로드 페이로드는 `observe.tracing.allowlist`를 통과한 필드만.
- `docs/LANGSMITH_EVAL.ko.md`: 수업의 LangSmith 평가 흐름과 우리 로컬 평가의 대응표(데이터셋 ↔ 골든셋 v2, 평가자 ↔ golden_v2 지표, 실험 ↔ eval_retrieval_v2 실행), 업로드 명령.

## 시험
내보내기 형식, SYNTHETIC 아닌 파일 거절, 업로드 경로가 가짜 클라이언트로만 호출되고 허용 필드만 포함, 키 없을 때 안내 종료.

## 공통 규칙
데이터(`data/golden_rules/**`, `profiles/*.json`, `data/equalizer/**`, `data/golden_sets/**`, `data/golden_retrieval/**`) 수정 금지, 구조 시험 통과(`KNOWN_DEBT` 증가 금지, LangChain·LangGraph·LangSmith import는 `rag/` 어댑터 파일에만), 기존 시험 기대값 수정·skip 금지, 네트워크·모델 다운로드·LLM 호출 금지. **끝나면 반드시 커밋.** 막히면 원인만 보고서에 적고 커밋 후 멈춤. 보고서: 구현·시험 통과 구분, 전체 시험 `n passed`.
