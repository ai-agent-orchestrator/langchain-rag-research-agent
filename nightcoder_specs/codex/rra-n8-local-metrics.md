files: src/rag_research_agent/observe/metrics.py, tests/test_local_metrics.py, docs/N8_REPORT_2026-11-10.md
forbid: src/rag_research_agent/observe/tracing.py, src/rag_research_agent/store/memvid_store.py, data/**, profiles/**, .env*
effort: medium
coder: codex
status: ready
order: 80
repo: research

# N8: 비식별 로컬 메트릭 기록기 (원문 없이 길이·지연·판정만)

## 배경
원격 tracing은 차단했다(`observe/tracing.py`, serving_trace_guard). 운영 관측용으로 원문 없이 수치만 남기는 로컬 기록기가 없다.

## 할 일
`observe/metrics.py`:
- 이벤트 기록: 단계(retrieve/grade/generate/answer), 지연(ms), 판정(ANSWERED/EMPTY/BELOW_THRESHOLD/BLOCKED/UNAVAILABLE 등 기존 상태명 재사용),
  입력·출력 길이, 슬롯 점유 수. **문자열 원문, 질의, 문서 본문, 사람 이름 같은 필드는 받지 않는다**(허용 키 목록으로 강제, 그 외 키는 오류).
- JSONL 파일(.runs 아래 경로 인자) 또는 메모리에 기록. 기존 `observe/local_log.py`와 겹치면 그 구조를 재사용하고 보고서에 관계를 적는다.
- 요약 함수: 단계별 지연 p50/p95, 판정 분포, timeout 비율.
- `observe/tracing.py`는 수정하지 않는다. 기존 파이프라인에 연결하지 않는다(연결 위치는 보고서에 제안).

## 시험 `tests/test_local_metrics.py`
허용 외 키 거절(원문 유입 차단), 요약 수치 손계산 일치, 빈 기록 요약, JSONL 왕복.

## 공통 규칙
AGENTS.md를 먼저 읽고 따른다(개발 저장소는 Chroma, memvid 제외, 5절 NightCoder 레인 규칙).
데이터(`data/**`), `profiles/**`, 보호 파일, 기존 시험 기대값 수정·skip 금지, `KNOWN_DEBT` 증가 금지.
새 모듈은 기존 구조 시험(`tests/test_structure.py`)의 배치·성숙도 규칙을 따른다(같은 폴더의 기존 모듈 선언을 참고).
LangChain·LangGraph·LangSmith import는 `rag/` 어댑터 파일에만. 네트워크·모델 다운로드·실제 모델 실행·LLM 호출 금지.
`files:`에 없는 기존 파일은 수정하지 않는다(필요하면 보고서에 "후속 연결 필요"로 적는다).
시험 이름과 내용은 실제 동작을 검증해야 하며, 가짜 통과(무조건 참)를 만들지 않는다.
보고서: 구현 / 시험 / 입증하지 못한 것(미검증)을 구분한다. **끝나면 반드시 커밋.** 막히면 원인만 보고서에 적고 커밋 후 멈춤.
