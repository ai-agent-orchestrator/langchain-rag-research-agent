files: docs/CLI_REFERENCE.md, docs/N18_REPORT_2026-11-10.md
forbid: src/rag_research_agent/observe/tracing.py, src/rag_research_agent/store/memvid_store.py, data/**, profiles/**, .env*
effort: low
coder: codex
status: ready
order: 180
repo: research

# N18: 스크립트 명령 참조 문서

## 할 일 (문서만)
`docs/CLI_REFERENCE.md`: `scripts/*.py`의 argparse 정의를 소스에서 읽어(실행하지 않음) 스크립트별로
목적 한 줄, 옵션(이름, 기본값, 설명), 출력 위치, 실제 모델 필요 여부, 예시 명령(PowerShell, `.\.venv\Scripts\python.exe` 형식)을 정리한다.
E4~E8 실행 순서(E4 → E6 → E5 → E7 → E8)와 각 단계의 입력 파일 의존 관계를 별도 절로.
docs/LEARNING_E*.md·MODELS.ko.md의 명령과 다르면 소스를 기준으로 쓰고 차이를 표시한다.

## 보고서 docs/N18_REPORT_2026-11-10.md
다룬 스크립트 수, 소스와 문서가 달랐던 곳.

## 공통 규칙
AGENTS.md를 먼저 읽고 따른다(개발 저장소는 Chroma, memvid 제외, 5절 NightCoder 레인 규칙).
데이터(`data/**`), `profiles/**`, 보호 파일, 기존 시험 기대값 수정·skip 금지, `KNOWN_DEBT` 증가 금지.
새 모듈은 기존 구조 시험(`tests/test_structure.py`)의 배치·성숙도 규칙을 따른다(같은 폴더의 기존 모듈 선언을 참고).
LangChain·LangGraph·LangSmith import는 `rag/` 어댑터 파일에만. 네트워크·모델 다운로드·실제 모델 실행·LLM 호출 금지.
`files:`에 없는 기존 파일은 수정하지 않는다(필요하면 보고서에 "후속 연결 필요"로 적는다).
시험 이름과 내용은 실제 동작을 검증해야 하며, 가짜 통과(무조건 참)를 만들지 않는다.
보고서: 구현 / 시험 / 입증하지 못한 것(미검증)을 구분한다. **끝나면 반드시 커밋.** 막히면 원인만 보고서에 적고 커밋 후 멈춤.
