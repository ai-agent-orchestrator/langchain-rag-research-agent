files: docs/ENCODING_PATH_AUDIT_2026-11-10.md, docs/N17_REPORT_2026-11-10.md
forbid: src/rag_research_agent/observe/tracing.py, src/rag_research_agent/store/memvid_store.py, data/**, profiles/**, .env*
effort: low
coder: codex
status: ready
order: 170
repo: research

# N17: 인코딩·경로 이식성 점검 문서 (코드 수정 없음)

## 배경
Windows에서 `models.json`의 한글이 PowerShell 기본 인코딩으로 깨져 보였다. PC 이전·WSL 사용을 앞두고 플랫폼 가정을 점검한다.

## 할 일 (문서만, 소스 읽기로 확인)
`docs/ENCODING_PATH_AUDIT_2026-11-10.md`:
1. `src/`, `scripts/`에서 `open(`, `read_text(`, `write_text(`, `json.dump` 중 encoding 미지정 위치 목록(파일:행).
2. 하드코딩된 Windows 경로·역슬래시, `os.replace`/삭제 등 Windows 잠금에 민감한 위치 목록.
3. 각 항목의 위험(읽기/쓰기, 한글 포함 가능성)과 권장 수정. 수정은 하지 않는다.
4. 우선순위 상위 10개를 별도 표로.

## 보고서 docs/N17_REPORT_2026-11-10.md
점검 범위, 방법, 확인하지 못한 것.

## 공통 규칙
AGENTS.md를 먼저 읽고 따른다(개발 저장소는 Chroma, memvid 제외, 5절 NightCoder 레인 규칙).
데이터(`data/**`), `profiles/**`, 보호 파일, 기존 시험 기대값 수정·skip 금지, `KNOWN_DEBT` 증가 금지.
새 모듈은 기존 구조 시험(`tests/test_structure.py`)의 배치·성숙도 규칙을 따른다(같은 폴더의 기존 모듈 선언을 참고).
LangChain·LangGraph·LangSmith import는 `rag/` 어댑터 파일에만. 네트워크·모델 다운로드·실제 모델 실행·LLM 호출 금지.
`files:`에 없는 기존 파일은 수정하지 않는다(필요하면 보고서에 "후속 연결 필요"로 적는다).
시험 이름과 내용은 실제 동작을 검증해야 하며, 가짜 통과(무조건 참)를 만들지 않는다.
보고서: 구현 / 시험 / 입증하지 못한 것(미검증)을 구분한다. **끝나면 반드시 커밋.** 막히면 원인만 보고서에 적고 커밋 후 멈춤.
