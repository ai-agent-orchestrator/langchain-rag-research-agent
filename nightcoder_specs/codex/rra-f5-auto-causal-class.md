files: src/rag_research_agent/ontology/rule_labeler.py, src/rag_research_agent/rag/profile.py, schemas/profile.schema.json, tests/test_auto_classes.py, docs/F5_REPORT_2026-11-10.md
forbid: data/**, profiles/*.json, .env*
effort: medium
coder: codex

# F5: 프로필 "자동 분류" 옵션 (인과·한계 문장이 미분류로 먼저 빠지는 문제)

## 배경
소송 프로필에서 핵심 인과 문장("~로 보였지만 실제로는 ~가 원인")이 분류 cue에 안 걸려 Unclassified로 잡혀 감량 때 먼저 빠졌다(`docs/EQUALIZER_V0.ko.md` 첫 보드 기록).

## 내용
- 프로필 형식에 선택 항목 `ontology.auto_classes` 추가(없으면 기존 동작 그대로):
  `{"from_rules": {"causal": "원인", "always_protect": "Constraint_Guardrail"}}` — 분류 cue에 안 걸린 문장 중 골든룰 인과 유형이 걸리면 지정 분류로, 항상 보호 유형이면 지정 분류로.
- 라벨러가 골든룰을 직접 import하지 않도록(모듈 경계) **판정 함수를 주입**받는다: `RuleLabeler(classes, fallback=callable)`. 조립(`rag/profile.py`)에서 `edge.scorer`의 설명 결과로 fallback을 만든다.
- `schemas/profile.schema.json`에 항목 추가, P3 lint가 알 수 없는 분류 이름을 잡도록.
- 제공 프로필 파일은 수정하지 않는다. 대표가 원하면 F4 흐름으로 켠다(보고서에 제안 문구).

## 시험
임시 프로필로: auto_classes 없으면 기존과 동일, 있으면 인과 문장이 지정 분류로, 그 분류가 diet_order 뒤쪽이면 감량에서 늦게 빠짐, 모듈 경계 시험 통과.

## 공통 규칙
데이터(`data/**`, `profiles/*.json`) 내용 수정 금지, 구조 시험 통과(`KNOWN_DEBT` 증가 금지, LangChain·LangGraph·LangSmith import는 `rag/` 어댑터 파일에만), 기존 시험 기대값 수정·skip 금지, 네트워크·모델 다운로드·LLM 호출 금지, 모든 새 기능은 순수 Python 공개 함수 + 얇은 CLI. **끝나면 반드시 커밋.** 막히면 원인만 보고서에 적고 커밋 후 멈춤. 보고서: 구현·시험 통과 구분, 전체 시험 `n passed`.
