files: src/rag_research_agent/store/memvid_store.py, src/rag_research_agent/store/retry.py, tests/test_memvid_writer_isolation.py, docs/F2_REPORT_2026-11-10.md
forbid: data/**, profiles/**, tests/test_memvid_store.py, tests/test_index_lifecycle.py, .env*
effort: high
coder: codex

# F2: memvid 쓰기 오류의 원인 찾기와 해결 (Windows)

## 배경
Windows에서 memvid 쓰기 시험이 가끔 실패한다(`docs/E3_REPORT_2026-11-10.md`, C5 보고서의 "writer 오류"). 재실행하면 대개 통과. NightCoder 게이트는 이런 간헐 실패로 명세 전체를 롤백한다.

## 할 일
1. **재현:** `scripts/store_stress.py --store memvid --runs 30`으로 실패율과 오류 메시지·위치(어느 호출, 어떤 파일)를 기록. 같은 조건에서 Chroma도 30회.
2. **원인 가설 검증(하나씩):** (a) 같은 임시 폴더 재사용·이전 핸들 미해제 (b) 백신·색인기 잠금 (c) memvid writer가 닫히기 전에 다음 열기 (d) 경로 길이·공백. 각 가설을 시험 코드로 확인하고 결과를 표로.
3. **해결:** 원인에 맞게 `memvid_store.py` 수정(예: writer를 명시적으로 닫고 파일 핸들 해제 확인 후 다음 단계, 시험·실행마다 고유 폴더, `retry_io` 범위 조정). 기존 시험 파일은 수정 금지 — 새 시험 `tests/test_memvid_writer_isolation.py`로 해결을 증명.
4. 원인을 특정하지 못하면 그 사실과 측정값만 보고하고, 재시도 범위만 넓히는 우회는 하지 않는다.

## 완료 기준
stress 30회 실패율 전후 비교표, 새 시험 통과, 기존 memvid 시험 기대값 그대로 통과.

## 공통 규칙
데이터(`data/**`, `profiles/*.json`) 내용 수정 금지, 구조 시험 통과(`KNOWN_DEBT` 증가 금지, LangChain·LangGraph·LangSmith import는 `rag/` 어댑터 파일에만), 기존 시험 기대값 수정·skip 금지, 네트워크·모델 다운로드·LLM 호출 금지, 모든 새 기능은 순수 Python 공개 함수 + 얇은 CLI. **끝나면 반드시 커밋.** 막히면 원인만 보고서에 적고 커밋 후 멈춤. 보고서: 구현·시험 통과 구분, 전체 시험 `n passed`.
