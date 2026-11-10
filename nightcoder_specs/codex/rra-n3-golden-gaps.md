files: src/rag_research_agent/observe/golden_gaps.py, scripts/golden_gaps.py, tests/test_golden_gaps.py, docs/N3_REPORT_2026-11-10.md
forbid: src/rag_research_agent/observe/tracing.py, data/**, profiles/**, .env*
effort: low
coder: codex

# N3: 골든셋 v2 빈틈 진단과 작성용 빈 양식 (데이터는 건드리지 않는다)

## 배경
현재 골든셋 v2는 작아서(근거 없음 9개 등) 임계값·설정 비교의 차이가 잡음인지 구분하기 어렵다.
골든셋 파일은 보호 대상이라 Codex가 만들거나 수정하지 않는다. 대표가 문항을 늘릴 때 쓸 진단 도구와 빈 양식만 만든다.
AGENTS.md를 먼저 읽는다.

## 할 일
`observe/golden_gaps.py`와 `scripts/golden_gaps.py --set data/golden_retrieval/terms_v2.json --out .runs/golden-gaps`:
1. 읽기 전용 진단: 유형(type)×split(compare/confirm)×근거 있음/없음 문항 수, 등급 분포, 문항당 정답 근거 수.
   기존 `observe/golden_v2.py`의 검증·로더를 재사용한다 (새 검증 규칙을 만들지 않는다).
2. 최소 목표 대비 부족분: 기본 목표를 인자로 받는다 (`--min-per-cell`, 기본 15).
   "표본이 이 정도면 오수용 0건이라도 Wilson 95% 상한이 약 X%"를 부족한 칸마다 함께 표시한다 (n=9일 때 약 29.9%).
3. 작성용 빈 양식 생성: 부족한 칸마다 `.runs/golden-gaps/drafts/` 아래 JSONL로 빈 문항 틀을 만든다.
   모든 틀에 `SYNTHETIC` 표시 필드를 넣고, 질문·근거 quote는 비워 둔다 (내용을 만들어 채우지 않는다).
   양식은 golden_v2 검증기의 필수 필드를 따르며, 빈 상태에서는 검증이 "미완성"으로 보고하도록 한다.
4. 출력은 `.runs/golden-gaps/` 에만 쓴다. `data/`에는 어떤 경로로도 쓰지 않는다 (시험으로 확인).

## 시험 `tests/test_golden_gaps.py`
작은 합성 골든셋으로: 칸별 개수·부족분 손계산 일치, Wilson 상한 값, data/ 쓰기 시도 거절, 양식에 SYNTHETIC 필드,
빈 양식이 검증기에서 미완성으로 보고. 기존 시험 수정 금지.

## 보고서 docs/N3_REPORT_2026-11-10.md
구현 / 시험 / 현재 골든셋 진단 결과(실제 terms_v2.json 읽기 결과 수치) / 입증하지 못하는 것.
문항 내용이나 정답을 제안·생성하지 않는다.

## 공통 규칙
데이터(`data/**`), `profiles/**`, 보호 파일, 기존 시험 기대값 수정·skip 금지, `KNOWN_DEBT` 증가 금지,
LangChain·LangGraph·LangSmith import는 `rag/` 어댑터 파일에만, 네트워크·모델 다운로드·실제 모델 실행·LLM 호출 금지.
전체 시험을 `n passed / failed / error / skipped`로 그대로 기록. **끝나면 반드시 커밋.** 막히면 원인만 보고서에 적고 커밋 후 멈춤.
