files: src/rag_research_agent/rag/http_mapping.py, tests/test_http_mapping.py, docs/N11_REPORT_2026-11-10.md
forbid: src/rag_research_agent/observe/tracing.py, src/rag_research_agent/store/memvid_store.py, data/**, profiles/**, .env*
effort: medium
coder: codex
status: hold   # 2026-11-10: Claude가 claude/n6-n7-n11 브랜치에서 개발
order: 110
repo: research

# N11: 파이프라인 결과 → HTTP 응답 매핑 (웹 프레임워크 없이 순수 함수)

## 배경
docs/RAG_REVIEW_FOLLOWUP_2026-11-10.md: 검색 장애는 RetrievalUnavailable로 올라가며 "HTTP 503 매핑은 이후 서비스 어댑터 책임"으로 남아 있다.
BLOCKED, EMPTY/BELOW_THRESHOLD, BACKBONE_NOT_CONFIGURED 등 결과 상태가 있다.

## 할 일
`rag/http_mapping.py`: FastAPI 등 프레임워크를 import하지 않는 순수 함수.
- 입력: GuidancePipeline의 결과 객체 또는 예외. 출력: (status_code, body dict, headers dict).
- 매핑 표를 코드 상수로 두고 보고서에 그대로 싣는다. 예: 정상 200, 근거 없음/임계값 미만 200 + 고정 안내(오류 아님),
  입력 정책 차단 422 또는 400(기존 정책 문서에 맞춰 근거와 함께 선택), 검색 장애 503 + Retry-After, 모델 미설정 503,
  예상하지 못한 예외 500(내부 메시지·원문 노출 금지).
- 응답 본문에는 기존 DTO 검사·마스킹을 통과한 필드만. 예외 메시지 원문, 질의 원문, 스택을 넣지 않는다.
- 결과 상태 이름은 기존 코드에서 확인해 그대로 쓴다(새 상태를 만들지 않는다).

## 시험 `tests/test_http_mapping.py`
상태별 코드·본문, 503의 Retry-After, 500 본문에 원문 없음, 매핑 표의 모든 상태가 처리되는지(누락 시 실패).

## 공통 규칙
AGENTS.md를 먼저 읽고 따른다(개발 저장소는 Chroma, memvid 제외, 5절 NightCoder 레인 규칙).
데이터(`data/**`), `profiles/**`, 보호 파일, 기존 시험 기대값 수정·skip 금지, `KNOWN_DEBT` 증가 금지.
새 모듈은 기존 구조 시험(`tests/test_structure.py`)의 배치·성숙도 규칙을 따른다(같은 폴더의 기존 모듈 선언을 참고).
LangChain·LangGraph·LangSmith import는 `rag/` 어댑터 파일에만. 네트워크·모델 다운로드·실제 모델 실행·LLM 호출 금지.
`files:`에 없는 기존 파일은 수정하지 않는다(필요하면 보고서에 "후속 연결 필요"로 적는다).
시험 이름과 내용은 실제 동작을 검증해야 하며, 가짜 통과(무조건 참)를 만들지 않는다.
보고서: 구현 / 시험 / 입증하지 못한 것(미검증)을 구분한다. **끝나면 반드시 커밋.** 막히면 원인만 보고서에 적고 커밋 후 멈춤.
