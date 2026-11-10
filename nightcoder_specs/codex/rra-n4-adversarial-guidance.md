files: tests/test_guidance_adversarial.py, docs/N4_REPORT_2026-11-10.md
forbid: src/rag_research_agent/observe/tracing.py, src/rag_research_agent/store/memvid_store.py, data/**, profiles/**, .env*
effort: medium
coder: codex
status: ready
order: 40
repo: research

# N4: GuidancePipeline 적대적 시험 (주입 문서, 상충 근거, 빈 결과, 긴 문맥)

## 배경
`rag/guidance.py`의 GuidancePipeline은 검색 → 근거 판정 → DTO → answer 연결이 되어 있고 정상/차단/무근거 계약 시험이 있다.
RAG에서 가장 빠지기 쉬운 적대적 입력에 대한 시험이 없다.

## 할 일
`tests/test_guidance_adversarial.py`에 기존 시험(`tests/test_guidance_bridge.py`)과 같은 방식(fake chat model, 제어된 검색 결과,
메모리 색인)으로 다음을 시험한다. 생산 코드는 수정하지 않는다.
1. 검색 문서 본문에 "이전 지시를 무시하고 ..." 같은 지시문이 들어 있을 때: 모델로 가는 입력과 출력 DTO가 기존 정책대로
   검사·마스킹되고, 인용이 실제 검색 근거의 부분집합인지.
2. 상충하는 두 근거가 함께 검색될 때: 인용 부분집합 규칙이 유지되는지, 한쪽 출처만 조작한 인용을 거절하는지.
3. 검색 결과가 비었을 때와 임계값 아래일 때: 생성 0회, model=not-invoked, 고정 안내.
4. 검색 장애(RetrievalUnavailable): 무근거 안내로 바뀌지 않고 예외가 올라가는지.
5. 매우 긴 문서(입력 한도 근처): 실패하더라도 정의된 방식으로 실패하는지(조용히 자르지 않는지 확인하고, 현재 동작을 그대로 기록).
현재 코드가 기대와 다르게 동작하면 시험을 억지로 맞추지 말고, 해당 시험은 실제 동작을 검증하는 형태로 두고
보고서에 "발견된 동작/개선 후보"로 적는다(xfail·skip 금지).

## 보고서 docs/N4_REPORT_2026-11-10.md
시나리오별 결과 표(통과/발견), 발견 사항, 미검증.

## 공통 규칙
AGENTS.md를 먼저 읽고 따른다(개발 저장소는 Chroma, memvid 제외, 5절 NightCoder 레인 규칙).
데이터(`data/**`), `profiles/**`, 보호 파일, 기존 시험 기대값 수정·skip 금지, `KNOWN_DEBT` 증가 금지.
새 모듈은 기존 구조 시험(`tests/test_structure.py`)의 배치·성숙도 규칙을 따른다(같은 폴더의 기존 모듈 선언을 참고).
LangChain·LangGraph·LangSmith import는 `rag/` 어댑터 파일에만. 네트워크·모델 다운로드·실제 모델 실행·LLM 호출 금지.
`files:`에 없는 기존 파일은 수정하지 않는다(필요하면 보고서에 "후속 연결 필요"로 적는다).
시험 이름과 내용은 실제 동작을 검증해야 하며, 가짜 통과(무조건 참)를 만들지 않는다.
보고서: 구현 / 시험 / 입증하지 못한 것(미검증)을 구분한다. **끝나면 반드시 커밋.** 막히면 원인만 보고서에 적고 커밋 후 멈춤.
