files: src/rag_research_agent/rag/lint.py, src/rag_research_agent/rag/cli.py, schemas/profile.schema.json, schemas/golden_rules.schema.json, tests/test_lint.py, docs/P3_REPORT_2026-11-09.md
forbid: data/golden_rules/**, profiles/*.json, data/equalizer/**, data/golden_sets/**, .env*
effort: medium
coder: codex
after: rra-p1-cli-inputs

# P3: 프로필·골든룰 검사기 (교체 부분 보호)

## 목표
대표나 다른 사람이 `profiles/*.json`이나 `data/golden_rules/*.json`을 고쳤을 때 **실행 전에** 실수를 잡는다. 명령: `rra check <파일...>` (파일을 안 주면 제공 파일 전부).

## 공통 규칙 (반드시 지킬 것)
- 저장소 `langchain-rag-research-agent`, main 최신에서 시작. 전체 맥락은 `docs/HANDOFF_CODEX_PROTOTYPE_2026-11-09.md`.
- 데이터 내용 수정 금지: `data/golden_rules/**`, `profiles/*.json`, `data/equalizer/**`, `data/golden_sets/**` (대표가 피드백 루프로 고치는 부분).
- `tests/test_structure.py` 통과 유지. `core` 외 모듈끼리 직접 import 금지, 조립은 `rag/`에서만. `KNOWN_DEBT`를 늘리지 않음.
- 기존 시험의 기대값 수정·skip·삭제 금지. 막히면 원인을 보고서에 적고 멈춤.
- 시험에서 외부 네트워크 접속 금지(가짜 fetcher 주입). LLM·외부 API 호출 금지. `.env` 접근 금지. push 금지(NightCoder가 패치로 회수).
- 합성 자료만 커밋. 실제 문서·결과물은 `.runs/`(git 무시)에만.
- 보고서: 구현·연결·시험 통과를 구분, 전체 시험 `n passed` 기록, "저장소 전체 통과" 같은 과장 금지, 열린 질문·미검증 항목 목록.

## 검사 (`rag/lint.py`, 표준 라이브러리만)
- **오류(종료 코드 1):** JSON 문법, 필수 항목 누락, 정규식 컴파일 실패, 중복 ID, `diet_order`·`never_remove`에 정의 안 된 분류, 없는 묶음 이름, 집중 키워드 6개 이상, 가중치 음수·숫자 아님, 알 수 없는 노브 수준.
- **경고(종료 코드 0):** 같은 cue가 여러 분류·규칙에 겹침(어느 쪽이 먼저 걸리는지 표시), 한 글자 cue, `diet_order`에 없는 분류(맨 뒤로 감), cue가 클리셰 규칙과 다른 규칙에 동시에 있음, cue/패턴 둘 다 없는 규칙.
- 파일 종류는 내용으로 판별(`causal_types` 있으면 골든룰, `ontology` 있으면 프로필).
- 출력: 사람이 읽는 표(파일·종류·위치·메시지) + 요약 줄.
- `schemas/*.json`: 두 형식의 JSON Schema 초안(문서 겸용). 검사기는 `jsonschema` 없이 동작.
- 기존 로더(`edge/rules.py`, `rag/profile.py`)의 검증과 메시지가 충돌하지 않게 하고, 로더는 수정하지 않는다(필요하면 보고서에 제안).

## 시험 `tests/test_lint.py`
- 제공 파일 전부 **오류 0**(경고는 허용, 개수만 확인).
- `tmp_path`에 일부러 깨뜨린 합성 파일을 만들어 오류 항목마다 1개 이상, 경고 항목마다 1개 이상.

## 완료 기준
위 시험 통과, 기존 시험 기준선 이상, 구조 시험 통과, `docs/P3_REPORT_2026-11-09.md`에 제공 파일의 경고 목록 첨부(대표가 피드백 루프에서 참고).

## 멈춤 조건
데이터 파일 내용을 고쳐야만 오류 0이 되는 경우: 고치지 말고 해당 오류를 보고서에 적고 멈춤.
