files: tests/test_bounded_worker_stress.py, docs/N5_REPORT_2026-11-10.md
forbid: src/rag_research_agent/observe/tracing.py, src/rag_research_agent/store/memvid_store.py, data/**, profiles/**, .env*
effort: medium
coder: codex
status: ready
order: 50
repo: research

# N5: BoundedWorker 부하·취소 시험 (슬롯 누수 확인)

## 배경
`rag/execution.py`의 BoundedWorker는 대기열/동시성 한도, timeout·취소 후 실제 작업 종료까지 슬롯 유지를 구현했고 기본 시험 3개가 있다
(`tests/test_bounded_worker.py`). 부하와 취소가 섞인 상황에서 슬롯이 새는지는 시험하지 않았다.

## 할 일
`tests/test_bounded_worker_stress.py` (생산 코드 수정 금지, 시험 전체가 수 초 안에 끝나게 작은 시간값 사용):
1. 동시 요청 폭주: 한도의 수 배 요청을 넣고 대기열 초과 거절 수, 끝난 뒤 사용 중 슬롯 0.
2. 느린 작업 + 응답 timeout: 응답은 timeout으로 끝나도 실제 작업이 끝날 때까지 슬롯이 유지되고, 끝난 뒤 반환되는지.
3. 대량 취소: 시작 직후 취소가 섞여도 슬롯 0으로 복귀, 늦게 끝난 작업의 예외가 회수되는지(경고 누락 없음).
4. aclose 중 진행 중 작업이 있을 때의 동작을 기록.
불안정한 시간 의존 단언은 피하고(이벤트·Barrier 사용), 시험을 10회 반복해도 결과가 같도록 만든다.
발견된 누수나 이상 동작은 시험을 맞추지 말고 보고서에 적는다.

## 보고서 docs/N5_REPORT_2026-11-10.md
시나리오별 결과, 반복 안정성(같은 시험 10회 실행 결과를 보고서에 적되, 샌드박스에서 실행할 수 없으면 "미실행"), 발견 사항.

## 공통 규칙
AGENTS.md를 먼저 읽고 따른다(개발 저장소는 Chroma, memvid 제외, 5절 NightCoder 레인 규칙).
데이터(`data/**`), `profiles/**`, 보호 파일, 기존 시험 기대값 수정·skip 금지, `KNOWN_DEBT` 증가 금지.
새 모듈은 기존 구조 시험(`tests/test_structure.py`)의 배치·성숙도 규칙을 따른다(같은 폴더의 기존 모듈 선언을 참고).
LangChain·LangGraph·LangSmith import는 `rag/` 어댑터 파일에만. 네트워크·모델 다운로드·실제 모델 실행·LLM 호출 금지.
`files:`에 없는 기존 파일은 수정하지 않는다(필요하면 보고서에 "후속 연결 필요"로 적는다).
시험 이름과 내용은 실제 동작을 검증해야 하며, 가짜 통과(무조건 참)를 만들지 않는다.
보고서: 구현 / 시험 / 입증하지 못한 것(미검증)을 구분한다. **끝나면 반드시 커밋.** 막히면 원인만 보고서에 적고 커밋 후 멈춤.
