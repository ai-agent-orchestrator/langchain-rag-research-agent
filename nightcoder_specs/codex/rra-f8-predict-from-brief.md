files: src/rag_research_agent/rag/predictions.py, scripts/predictions.py, tests/test_predictions_from_brief.py, docs/PREDICTION_LOG.ko.md, docs/F8_REPORT_2026-11-10.md
forbid: data/**, profiles/**, .env*
effort: low
coder: codex

# F8: 리서치 결과에서 바로 예측 기록 (C10 연결)

## 내용
- `scripts/predictions.py add --from-research .runs/research/<시각>/result.json --statement "..." --due 2027-05-10 [--confidence 0.6]`: 근거 구간 ID·출처 문서·프로필·브리프 경로를 결과 파일에서 자동으로 채운다(대표는 예측 문장과 기한만 입력).
- `summary`에 필터·태그·분야별 적중률과 "기한 지난 미해결" 목록을 표로.
- F1이 없으면 `--from-brief <brief_demo trace.json>`도 지원하거나, 전제 없음 보고.

## 시험
합성 result.json으로 자동 채움, 잘못된 경로 거절, 요약 표.

## 공통 규칙
데이터(`data/**`, `profiles/*.json`) 내용 수정 금지, 구조 시험 통과(`KNOWN_DEBT` 증가 금지, LangChain·LangGraph·LangSmith import는 `rag/` 어댑터 파일에만), 기존 시험 기대값 수정·skip 금지, 네트워크·모델 다운로드·LLM 호출 금지, 모든 새 기능은 순수 Python 공개 함수 + 얇은 CLI. **끝나면 반드시 커밋.** 막히면 원인만 보고서에 적고 커밋 후 멈춤. 보고서: 구현·시험 통과 구분, 전체 시험 `n passed`.
