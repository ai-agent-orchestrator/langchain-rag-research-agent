files: docs/INDEX.md, docs/MIGRATION_CHECKLIST.md, docs/N10_REPORT_2026-11-10.md
forbid: src/rag_research_agent/observe/tracing.py, src/rag_research_agent/store/memvid_store.py, data/**, profiles/**, .env*
effort: low
coder: codex
status: ready
order: 100
repo: research

# N10: 문서 색인과 이전(마이그레이션) 체크리스트

## 할 일 (문서만)
1. `docs/INDEX.md`: docs/의 보고서·설계·가이드를 종류별(설계, 단계 보고서 P/C/E/X/N, 학습 실험, 운영, 결정 기록)로 한 줄 요약과 함께 색인.
   각 보고서의 시험 결과 수치는 원문에서 그대로 옮기고, 해석을 덧붙이지 않는다.
2. `docs/MIGRATION_CHECKLIST.md`: 이 저장소를 다른 PC(또는 WSL)로 옮길 때의 체크리스트.
   git에 들어가는 것/안 들어가는 것(.gitignore 기준: .venv, .runs, data 일부, *.mv2, .env), 모델 재준비(scripts/prepare_models.py,
   .runs/models.json의 리비전), uv 환경 재구성, 비밀값은 파일 복사 대신 재설정, data에 실제 자료가 있으면 올리지 않기.
   Windows 전용 가정(경로, 파일 잠금)과 WSL에서 달라질 점을 확인 가능한 범위에서 적는다.
코드·시험 변경 없음.

## 보고서 docs/N10_REPORT_2026-11-10.md
작성 범위와 확인하지 못한 항목.

## 공통 규칙
AGENTS.md를 먼저 읽고 따른다(개발 저장소는 Chroma, memvid 제외, 5절 NightCoder 레인 규칙).
데이터(`data/**`), `profiles/**`, 보호 파일, 기존 시험 기대값 수정·skip 금지, `KNOWN_DEBT` 증가 금지.
새 모듈은 기존 구조 시험(`tests/test_structure.py`)의 배치·성숙도 규칙을 따른다(같은 폴더의 기존 모듈 선언을 참고).
LangChain·LangGraph·LangSmith import는 `rag/` 어댑터 파일에만. 네트워크·모델 다운로드·실제 모델 실행·LLM 호출 금지.
`files:`에 없는 기존 파일은 수정하지 않는다(필요하면 보고서에 "후속 연결 필요"로 적는다).
시험 이름과 내용은 실제 동작을 검증해야 하며, 가짜 통과(무조건 참)를 만들지 않는다.
보고서: 구현 / 시험 / 입증하지 못한 것(미검증)을 구분한다. **끝나면 반드시 커밋.** 막히면 원인만 보고서에 적고 커밋 후 멈춤.
