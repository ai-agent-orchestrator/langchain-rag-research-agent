files: src/rag_research_agent/core/settings.py, tests/test_runtime_settings.py, docs/N7_REPORT_2026-11-10.md
forbid: src/rag_research_agent/observe/tracing.py, src/rag_research_agent/store/memvid_store.py, data/**, profiles/**, .env*
effort: low
coder: codex
status: hold   # 2026-11-10: Claude가 claude/n6-n7-n11 브랜치에서 개발
order: 70
repo: research

# N7: 실행 설정 분리 (timeout, 슬롯, 근거 임계값) 로더와 검증

## 배경
timeout·동시 슬롯 수·근거 임계값(tau_abs, tau_gap) 등이 코드 인자로 흩어져 있다. 설정 파일·환경변수로 읽고 검증하는 부품이 없다.

## 할 일
`core/settings.py` (표준 라이브러리, frozen dataclass):
- 필드: request_timeout_s, worker_slots, queue_limit, tau_abs, tau_gap, rule_version, index_version. 기존 코드의 기본값을 읽어
  같은 기본값을 쓰고, 어디서 가져왔는지 보고서에 적는다(찾지 못한 값은 "기본값 미정"으로 두고 필수 입력으로 만든다).
- 로드 순서: 기본값 < JSON 파일 < 환경변수(`RRA_` 접두어). 알 수 없는 키는 오류. 범위 검증(timeout>0, slots>=1, 0<=tau_abs<=1 등).
- tau 값은 "모델·검색 모드·버전별로 보정된 값"이어야 한다는 경고 문구를 docstring과 오류 메시지에 남긴다.
- 비밀값 필드는 만들지 않는다. `.env` 파일을 읽지 않는다.
기존 모듈에는 연결하지 않는다.

## 시험 `tests/test_runtime_settings.py`
우선순위, 알 수 없는 키 거절, 범위 오류 메시지, 환경변수 형 변환, frozen.

## 공통 규칙
AGENTS.md를 먼저 읽고 따른다(개발 저장소는 Chroma, memvid 제외, 5절 NightCoder 레인 규칙).
데이터(`data/**`), `profiles/**`, 보호 파일, 기존 시험 기대값 수정·skip 금지, `KNOWN_DEBT` 증가 금지.
새 모듈은 기존 구조 시험(`tests/test_structure.py`)의 배치·성숙도 규칙을 따른다(같은 폴더의 기존 모듈 선언을 참고).
LangChain·LangGraph·LangSmith import는 `rag/` 어댑터 파일에만. 네트워크·모델 다운로드·실제 모델 실행·LLM 호출 금지.
`files:`에 없는 기존 파일은 수정하지 않는다(필요하면 보고서에 "후속 연결 필요"로 적는다).
시험 이름과 내용은 실제 동작을 검증해야 하며, 가짜 통과(무조건 참)를 만들지 않는다.
보고서: 구현 / 시험 / 입증하지 못한 것(미검증)을 구분한다. **끝나면 반드시 커밋.** 막히면 원인만 보고서에 적고 커밋 후 멈춤.
