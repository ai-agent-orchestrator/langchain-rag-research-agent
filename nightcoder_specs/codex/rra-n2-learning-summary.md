files: src/rag_research_agent/lab/learning_summary.py, scripts/summarize_learning.py, tests/test_learning_summary.py, docs/N2_REPORT_2026-11-10.md
forbid: src/rag_research_agent/observe/tracing.py, data/**, profiles/**, .env*
effort: medium
coder: codex

# N2: E4~E8 실제 모델 결과 종합 도구 (판정 기준을 코드에 고정)

## 배경
E4(지시문), E5(청크), E6(근거 없음 경계), E7(융합), E8(응용)의 도구는 있고, 실제 모델 결과는 `.runs/e4`~`.runs/e8`에
대표가 직접 만든다. 결과를 본 뒤 기준을 바꾸지 못하도록 종합 규칙을 먼저 코드와 시험으로 고정한다.
AGENTS.md를 먼저 읽는다. 실제 모델은 실행하지 않는다.

## 할 일
`lab/learning_summary.py`와 `scripts/summarize_learning.py --runs .runs --out .runs/summary`:
- `.runs/e4`~`e8`의 기존 출력 파일(JSON)을 읽기만 한다. 출력 스키마는 기존 쓰기 코드
  (scripts/eval_retrieval_v2.py, compare_embedders.py, sweep_retrieval_gates.py, compare_retrieval_fusion.py,
  learning_applications.py, lab/*)를 읽어 확인하고, 없는 파일·없는 필드는 "미실행"으로 표시한다. 추정으로 채우지 않는다.
- 고정 판정 기준(코드 상수와 시험으로 못 박는다):
  1. 선택은 compare 문항만 사용. confirm은 선택된 1개 설정에 한 번만 보고하고 선택에 반영하지 않는다.
  2. E4·E5·E7은 Recall@3 → MRR → 오수용 낮음 순으로 비교. 비교 지표의 구간이 겹치면 "차이 불확실"로 쓰고 승자를 선언하지 않는다.
  3. E6은 오수용률 최소 → 오거절률 최소 → 높은 임계값 순. 모든 비율에 표본 수 n과 Wilson 95% 구간. 0건을 "보장"이라 쓰지 않는다.
  4. fake 경로 시험 수치와 실제 모델 수치를 같은 표·열에 섞지 않는다. fake만 있으면 "실제 모델 결과 없음"이라고 쓴다.
  5. injection은 검색 품질 분모에서 제외. E8 유사도 신호는 보조 정보로 표기한다.
- 산출: 항목(E4~E8)별 요약 Markdown + 어두운 HTML 한 장. 권장 설정은 "후보"로만 표기하고, 근거가 약하면 "추가 데이터 필요".
  표본이 작아 결론이 약한 항목을 별도 목록으로 낸다. "이 요약이 입증하지 못하는 것" 절을 항상 넣는다.
- 출력은 `.runs/summary/`에만 쓴다. 입력 폴더를 수정하지 않는다.

## 시험 `tests/test_learning_summary.py`
합성 입력 파일로: 구간이 겹치면 승자 미선언, confirm 점수를 바꿔도 선택이 같음, fake/실제 분리, 파일 없으면 "미실행",
Wilson 구간 손계산 일치, 입력 폴더 불변. 기존 시험 수정 금지.

## 보고서 docs/N2_REPORT_2026-11-10.md
구현 / 시험 / 고정한 기준 목록 / 입증하지 못하는 것. 실제 결과 해석은 하지 않는다.

## 공통 규칙
데이터(`data/**`), `profiles/**`, 보호 파일, 기존 시험 기대값 수정·skip 금지, `KNOWN_DEBT` 증가 금지,
LangChain·LangGraph·LangSmith import는 `rag/` 어댑터 파일에만, 네트워크·모델 다운로드·실제 모델 실행·LLM 호출 금지.
전체 시험을 `n passed / failed / error / skipped`로 그대로 기록. **끝나면 반드시 커밋.** 막히면 원인만 보고서에 적고 커밋 후 멈춤.
