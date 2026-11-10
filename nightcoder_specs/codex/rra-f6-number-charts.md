files: src/rag_research_agent/compose/number_chart.py, scripts/brief_demo.py, src/rag_research_agent/rag/research.py, tests/test_number_chart.py, docs/F6_REPORT_2026-11-10.md
forbid: data/**, profiles/**, .env*
effort: medium
coder: codex

# F6: 수치표 → 작은 차트 (대표: 차트를 많이 본다, X축 기간 · Y축 값)

## 내용
- `compose/number_chart.py` (표준 라이브러리, 인라인 SVG 문자열): C7 `NumberRow` 목록에서 같은 지표·같은 단위의 행을 기간 순으로 묶어 지표마다 작은 선/막대 차트. 기간을 해석 못 한 행은 차트에서 빼고 표에만. %와 %p는 다른 축. 값 라벨, 출처 구간 ID 툴팁(title).
- 점이 2개 미만인 지표는 차트 없이 표만. 어두운 배경에 맞는 색(파랑 #5ba7db, 청록 #4cc3a8), 폭은 부모에 맞춤.
- `rag/research.py`(F1이 있으면)의 `report.html`과 `brief_demo.py` 출력에 차트 추가. F1이 없으면 brief_demo만.

## 시험
합성 행으로 지표별 묶음·정렬, %/%p 분리, 점 1개면 차트 없음, SVG에 원문 값만 존재.

## 공통 규칙
데이터(`data/**`, `profiles/*.json`) 내용 수정 금지, 구조 시험 통과(`KNOWN_DEBT` 증가 금지, LangChain·LangGraph·LangSmith import는 `rag/` 어댑터 파일에만), 기존 시험 기대값 수정·skip 금지, 네트워크·모델 다운로드·LLM 호출 금지, 모든 새 기능은 순수 Python 공개 함수 + 얇은 CLI. **끝나면 반드시 커밋.** 막히면 원인만 보고서에 적고 커밋 후 멈춤. 보고서: 구현·시험 통과 구분, 전체 시험 `n passed`.
