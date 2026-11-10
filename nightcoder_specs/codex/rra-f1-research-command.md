files: src/rag_research_agent/rag/research.py, src/rag_research_agent/rag/cli.py, tests/test_research_command.py, docs/RESEARCH_COMMAND.ko.md, docs/F1_REPORT_2026-11-10.md
forbid: data/**, profiles/**, .env*
effort: high
coder: codex

# F1: 한 줄 리서치 명령 `rra research` (대표가 매일 쓰는 흐름)

## 목표
자료를 넣고 질문하면 **브리프 + 수치표 + 근거 목록**이 한 페이지로 나온다. 지금 따로 있는 부품(P1 입력, C6 서재, 검색, Equalizer, C7 수치표)을 하나로 잇는다. 새 로직은 최소, 조립 위주.

## 내용
- `rag/research.py`: `run_research(question, inputs, profile, library_path, budget, k, embedder="fake", allow_network=False, focus=None) -> ResearchResult`. 순서: 입력 적재(`ingest/sources.load_source`) → 서재 증분 추가(`Library.add`) → 하이브리드 검색 → 프로필 Equalizer 브리프(`Library.brief`) → 남은 문장의 수치표(`compose.numbers`) → 결과 묶음(브리프, 남긴/생략 구간과 사유, 근거 조각 ID·출처 문서, 수치표, 버전들).
- `rra research "질문" --profile macro [--file a.pdf ...] [--url ...] [--text ...] [--library .runs/library] [--budget 800] [--focus 금리:2]`: 결과를 `.runs/research/<UTC시각>/`에 `report.md`·`report.html`(어두운 스타일, 폰 폭)·`result.json`으로. 마지막 줄에 경로.
- 자료 없이 질문만 주면 기존 서재에서 검색.
- `docs/RESEARCH_COMMAND.ko.md`: 대표용 1쪽(명령 예 5개, 결과 읽는 법).

## 시험
합성 텍스트 파일 2개로 전체 흐름(가짜 임베더), 자료 없이 기존 서재 검색, 차단 입력 시 생성 0회·보고서에 BLOCKED, 결과 파일 3개 생성, 수치표에 원문에 없는 값 없음.

## 공통 규칙
데이터(`data/**`, `profiles/*.json`) 내용 수정 금지, 구조 시험 통과(`KNOWN_DEBT` 증가 금지, LangChain·LangGraph·LangSmith import는 `rag/` 어댑터 파일에만), 기존 시험 기대값 수정·skip 금지, 네트워크·모델 다운로드·LLM 호출 금지, 모든 새 기능은 순수 Python 공개 함수 + 얇은 CLI. **끝나면 반드시 커밋.** 막히면 원인만 보고서에 적고 커밋 후 멈춤. 보고서: 구현·시험 통과 구분, 전체 시험 `n passed`.
