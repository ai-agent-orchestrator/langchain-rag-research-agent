files: src/rag_research_agent/compose/numbers.py, scripts/brief_demo.py, scripts/library_board.py, tests/test_number_table.py, docs/C7_REPORT_2026-11-10.md
forbid: data/**, profiles/**, src/rag_research_agent/rag/**, src/rag_research_agent/edge/**, .env*
effort: medium
coder: codex

# C7: 수치 추출표 (골든룰 5-1절)

## 목표
브리프에 남은 문장에서 수치를 표로 뽑아, 대표가 차트로 옮기기 쉽게 한다. 값은 원문 그대로, 출처 구간 ID를 붙인다(추출식 원칙).

## 내용 `compose/numbers.py` (표준 라이브러리, `core`만 import)
- `extract_numbers(segments, source_text) -> list[NumberRow]`: `NumberRow(segment_id, indicator, value, unit, period, base, raw)`.
  - 값·단위: %, %p, 배, 원/달러/억/조/만, 명·건 등. `%p`와 `%`는 구분.
  - 기간: 연도·분기·월·"최근 N개월". 비교 기준: "전년 동기 대비", "전기 대비", "전월 대비", "목표 대비" 등.
  - 지표 이름: 수치 앞 명사구(간단한 규칙: 수치 직전 "은/는/이/가" 앞의 어절 1~3개). 모르면 빈칸.
  - 한 문장에 수치가 여럿이면 여러 행. 원문에 없는 값은 절대 만들지 않음.
- `to_markdown(rows)`, `to_csv(rows)`.
- `scripts/brief_demo.py`·`scripts/library_board.py`에 "수치 추출표" 출력 추가(기존 출력은 유지).

## 시험
매크로 합성 문장들(%, %p, 전년 동기 대비, 속보치→확정치 두 값, 금액)로 행·단위·기간·기준 확인, 모든 `raw`가 원문 부분 문자열, 수치 없는 문장은 행 없음.

## 공통 규칙
- 저장소 `langchain-rag-research-agent`, 레인 브랜치에서 이전 명세 결과 위에 이어서 작업. 맥락: `docs/EQUALIZER_V0.ko.md`, `docs/HANDOFF_CODEX_PROTOTYPE_2026-11-09.md` 3절.
- 데이터 내용 수정 금지: `data/golden_rules/**`, `profiles/*.json`, `data/equalizer/**`, `data/golden_sets/**`.
- `tests/test_structure.py` 통과 유지(모듈 간 직접 import 금지, 조립은 `rag/`·`scripts/`에서). `KNOWN_DEBT` 증가 금지.
- 기존 시험 기대값 수정·skip·삭제 금지. 네트워크·LLM·`.env` 금지. push 금지.
- **작업이 끝나면 반드시 `git add`와 `git commit`으로 커밋한다**(커밋이 없으면 실패로 처리됨). 막히면 원인만 보고서에 적고, 그 보고서도 커밋한 뒤 멈춘다.
- 보고서: 구현·시험 통과 구분, 전체 시험 `n passed`, 한계·열린 질문.
