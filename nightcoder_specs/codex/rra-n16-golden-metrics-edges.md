files: tests/test_golden_v2_metric_edges.py, docs/N16_REPORT_2026-11-10.md
forbid: src/rag_research_agent/observe/tracing.py, src/rag_research_agent/store/memvid_store.py, data/**, profiles/**, .env*
effort: low
coder: codex
status: ready
order: 160
repo: research

# N16: 골든셋 v2 지표 경계 시험 (손계산 대조)

## 배경
`observe/golden_v2.py`는 Hit/Recall@k, MRR, nDCG@k, 오수용/오거절, 부트스트랩 구간을 계산한다. 경계 사례 시험이 적다.

## 할 일
`tests/test_golden_v2_metric_edges.py` (생산 코드 수정 금지):
- k가 결과 수보다 클 때, 결과 0개, 정답 0개(근거 없음 문항), 정답이 여러 조각에 나뉜 quote
- nDCG: 같은 등급 동점, 한 조각에 여러 quote(가장 높은 새 등급 하나로 계산한다는 기존 규칙), 이상적 순위와 동일하면 1.0
- MRR: 첫 정답이 k 밖에 있을 때(전달 순위 전체 기준이라는 기존 규칙)
- 부트스트랩: 같은 시드 같은 결과, 표본 1개
각 기대값은 시험 안에 손계산 과정을 주석으로 적는다. 기존 정의와 다르게 보이는 결과는 보고서에 적는다.

## 공통 규칙
AGENTS.md를 먼저 읽고 따른다(개발 저장소는 Chroma, memvid 제외, 5절 NightCoder 레인 규칙).
데이터(`data/**`), `profiles/**`, 보호 파일, 기존 시험 기대값 수정·skip 금지, `KNOWN_DEBT` 증가 금지.
새 모듈은 기존 구조 시험(`tests/test_structure.py`)의 배치·성숙도 규칙을 따른다(같은 폴더의 기존 모듈 선언을 참고).
LangChain·LangGraph·LangSmith import는 `rag/` 어댑터 파일에만. 네트워크·모델 다운로드·실제 모델 실행·LLM 호출 금지.
`files:`에 없는 기존 파일은 수정하지 않는다(필요하면 보고서에 "후속 연결 필요"로 적는다).
시험 이름과 내용은 실제 동작을 검증해야 하며, 가짜 통과(무조건 참)를 만들지 않는다.
보고서: 구현 / 시험 / 입증하지 못한 것(미검증)을 구분한다. **끝나면 반드시 커밋.** 막히면 원인만 보고서에 적고 커밋 후 멈춤.
