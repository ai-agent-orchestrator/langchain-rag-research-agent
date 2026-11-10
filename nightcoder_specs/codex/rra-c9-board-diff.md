files: scripts/board_diff.py, tests/test_board_diff.py, docs/C9_REPORT_2026-11-10.md
forbid: data/**, profiles/**, src/**, scripts/filter_board.py, .env*
effort: medium
coder: codex

# C9: 필터 차이 보드 (문장 단위 비교 + 실행 기록 추이)

## 목표
대표가 "두 필터가 무엇을 다르게 남겼는지"와 "규칙을 고칠 때마다 수치가 어떻게 변했는지"를 한눈에 본다.

## 내용 `scripts/board_diff.py` (기존 `filter_board.py`는 수정하지 않고 그 함수를 import해 사용)
- `--a litigation --b research --set data/golden_sets/legal_synthetic_v1.json --budget 200`: 문장마다 A·B에서 남았는지(●/○), 분류 라벨, 최종 점수, 보존 목록·클리셰 표시. 차이 나는 문장을 위로.
- `--history .runs/board_history.jsonl`: 설정별 보존 적중·클리셰 남음의 실행별 추이(작은 막대/스파크라인, 인라인 SVG). 기록이 없으면 안내만.
- 출력: `.runs/board_diff.html`(기존 보드와 같은 어두운 스타일, 폰 폭에서 가로 스크롤) + 같은 내용의 Markdown.

## 시험
합성 골든셋 2개로 차이 표 생성, 같은 필터끼리는 차이 0, 기록 파일 없을 때·있을 때 HTML 생성.

## 공통 규칙
- 저장소 `langchain-rag-research-agent`, 레인 브랜치에서 이전 명세 결과 위에 이어서 작업. 맥락: `docs/EQUALIZER_V0.ko.md`, `docs/HANDOFF_CODEX_PROTOTYPE_2026-11-09.md` 3절.
- 데이터 내용 수정 금지: `data/golden_rules/**`, `profiles/*.json`, `data/equalizer/**`, `data/golden_sets/**`.
- `tests/test_structure.py` 통과 유지(모듈 간 직접 import 금지, 조립은 `rag/`·`scripts/`에서). `KNOWN_DEBT` 증가 금지.
- 기존 시험 기대값 수정·skip·삭제 금지. 네트워크·LLM·`.env` 금지. push 금지.
- **작업이 끝나면 반드시 `git add`와 `git commit`으로 커밋한다**(커밋이 없으면 실패로 처리됨). 막히면 원인만 보고서에 적고, 그 보고서도 커밋한 뒤 멈춘다.
- 보고서: 구현·시험 통과 구분, 전체 시험 `n passed`, 한계·열린 질문.
