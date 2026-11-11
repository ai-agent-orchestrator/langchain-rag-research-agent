files: src/rag_research_agent/rag/hub.py, scripts/hub.py, tests/test_hub.py, docs/F3_REPORT_2026-11-10.md
forbid: data/**, profiles/**, scripts/filter_board.py, scripts/board_diff.py, scripts/library_board.py, .env*
effort: medium
coder: codex

# F3: 보드 모음 첫 화면 `.runs/index.html` (수치화된 보드 한곳에)

## 목표
흩어진 보드(필터 보드, 차이 보드, 서재 보드, 검색 평가 v2, 리서치 보고서, NightCoder 실행 요약)를 한 화면에서 고른다. 각 보드 파일은 그대로 두고 **링크와 핵심 숫자만** 모은다.

## 내용
- `rag/hub.py`: `.runs/` 아래를 훑어 종류별 최신 N개(기본 5)를 찾고, 각 파일에서 핵심 숫자를 읽어 카드로: 필터 보드(보존 적중 최고·최저), 평가 v2(Hit@3, 근거 없음 오수용률), 리서치(상태, 남긴 문장 수), NightCoder 요약(`--nightcoder-runs <경로>` 주면 성공·실패 수). 숫자를 못 읽으면 링크만.
- `scripts/hub.py [--runs .runs] [--nightcoder-runs C:/Users/Codelab/nc2-rra-codex/runs]` → `.runs/index.html`(어두운 카드, 폰 폭, 외부 파일 없음).
- 시각은 KST로 표시.

## 시험
가짜 산출물 파일들로 카드 생성·숫자 추출·없는 종류는 생략·링크 상대 경로.

## 공통 규칙
데이터(`data/**`, `profiles/*.json`) 내용 수정 금지, 구조 시험 통과(`KNOWN_DEBT` 증가 금지, LangChain·LangGraph·LangSmith import는 `rag/` 어댑터 파일에만), 기존 시험 기대값 수정·skip 금지, 네트워크·모델 다운로드·LLM 호출 금지, 모든 새 기능은 순수 Python 공개 함수 + 얇은 CLI. **끝나면 반드시 커밋.** 막히면 원인만 보고서에 적고 커밋 후 멈춤. 보고서: 구현·시험 통과 구분, 전체 시험 `n passed`.
