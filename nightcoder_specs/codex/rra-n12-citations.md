files: src/rag_research_agent/rag/citations.py, tests/test_citations.py, docs/N12_REPORT_2026-11-10.md
forbid: src/rag_research_agent/observe/tracing.py, src/rag_research_agent/store/memvid_store.py, data/**, profiles/**, .env*
effort: medium
coder: codex
status: ready
order: 120
repo: research

# N12: 답변 인용 표시 포매터

## 배경
GuidancePipeline은 실제 검색 근거의 부분집합만 인용하도록 검사한다. 사용자가 볼 답변에 "어느 근거에서 나왔는지" 표시하는 부품이 없다.

## 할 일
`rag/citations.py`:
- 입력: 최종 answer와 인용 목록(기존 DTO 형태를 소스에서 확인해 그대로 사용). 출력: 본문 + 번호 각주([1], [2]) + 참고자료 목록(제목, 출처 ID, 문서 hash 앞자리).
- 같은 출처는 한 번호로 합친다. 인용되지 않은 검색 결과는 목록에 넣지 않는다.
- 출처 제목·본문은 이미 마스킹된 값만 받는다(이 모듈이 원문을 다시 읽지 않는다).
- Markdown과 일반 텍스트 두 형식.
기존 answer 조립 코드는 수정하지 않는다(연결 위치는 보고서에 제안).

## 시험 `tests/test_citations.py`
번호 부여 순서, 중복 출처 병합, 인용 없는 답변, 두 형식, 존재하지 않는 출처 ID 거절.

## 공통 규칙
AGENTS.md를 먼저 읽고 따른다(개발 저장소는 Chroma, memvid 제외, 5절 NightCoder 레인 규칙).
데이터(`data/**`), `profiles/**`, 보호 파일, 기존 시험 기대값 수정·skip 금지, `KNOWN_DEBT` 증가 금지.
새 모듈은 기존 구조 시험(`tests/test_structure.py`)의 배치·성숙도 규칙을 따른다(같은 폴더의 기존 모듈 선언을 참고).
LangChain·LangGraph·LangSmith import는 `rag/` 어댑터 파일에만. 네트워크·모델 다운로드·실제 모델 실행·LLM 호출 금지.
`files:`에 없는 기존 파일은 수정하지 않는다(필요하면 보고서에 "후속 연결 필요"로 적는다).
시험 이름과 내용은 실제 동작을 검증해야 하며, 가짜 통과(무조건 참)를 만들지 않는다.
보고서: 구현 / 시험 / 입증하지 못한 것(미검증)을 구분한다. **끝나면 반드시 커밋.** 막히면 원인만 보고서에 적고 커밋 후 멈춤.
