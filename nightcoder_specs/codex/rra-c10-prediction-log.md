files: src/rag_research_agent/rag/predictions.py, scripts/predictions.py, tests/test_predictions.py, docs/PREDICTION_LOG.ko.md, docs/C10_REPORT_2026-11-10.md
forbid: data/**, profiles/**, .env*
effort: medium
coder: codex

# C10: 예측 기록장 뼈대 (열린 항목 O8, LLM 없음)

## 배경
대표의 최종 목적은 미래 예측이다(`docs/GOLDEN_RULES.ko.md` 8절). 예측은 Equalizer와 분리하고, 예측·근거·시점을 기록해 나중에 실제 결과와 대조한다. 이번에는 **기록·대조 도구만** 만든다(예측 생성 없음).

## 내용
- `rag/predictions.py`: JSONL 저장소(기본 `.runs/predictions.jsonl`). `add(statement, profile, evidence_ids, brief_path, due, confidence=None, tags=())` → ID, `resolve(id, outcome: "hit"|"miss"|"partial"|"void", note, resolved_at)`, `list(open_only)`, `summary()`(필터·태그별 적중률, 기한 지난 미해결 수).
- 모든 기록은 추가만(append-only). 수정은 새 줄로 남기고 최신 상태를 계산.
- `scripts/predictions.py add|resolve|list|summary` 명령.
- `docs/PREDICTION_LOG.ko.md`: 대표용 사용법(예: 브리프를 보고 "6개월 내 X" 예측 기록 → 기한 후 결과 기록 → 필터별 적중률 보기).

## 시험
추가·해결·요약·기한 지남 계산, append-only(파일 줄 수 증가), 잘못된 결과값 거절.

## 공통 규칙
- 저장소 `langchain-rag-research-agent`, 레인 브랜치에서 이전 명세 결과 위에 이어서 작업. 맥락: `docs/EQUALIZER_V0.ko.md`, `docs/HANDOFF_CODEX_PROTOTYPE_2026-11-09.md` 3절.
- 데이터 내용 수정 금지: `data/golden_rules/**`, `profiles/*.json`, `data/equalizer/**`, `data/golden_sets/**`.
- `tests/test_structure.py` 통과 유지(모듈 간 직접 import 금지, 조립은 `rag/`·`scripts/`에서). `KNOWN_DEBT` 증가 금지.
- 기존 시험 기대값 수정·skip·삭제 금지. 네트워크·LLM·`.env` 금지. push 금지.
- **작업이 끝나면 반드시 `git add`와 `git commit`으로 커밋한다**(커밋이 없으면 실패로 처리됨). 막히면 원인만 보고서에 적고, 그 보고서도 커밋한 뒤 멈춘다.
- 보고서: 구현·시험 통과 구분, 전체 시험 `n passed`, 한계·열린 질문.
