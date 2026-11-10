files: src/rag_research_agent/store/retry.py, src/rag_research_agent/store/chroma_store.py, src/rag_research_agent/store/memvid_store.py, scripts/store_stress.py, tests/test_store_retry.py, docs/C5_REPORT_2026-11-10.md
forbid: data/**, profiles/**, src/rag_research_agent/rag/**, .env*
effort: medium
coder: codex

# C5: 저장소 쓰기 안정화 (Windows 접근 거부 대응)

## 배경
Windows에서 memvid 쓰기 중 가끔 `PermissionError`/`OSError`(winerror 5, 32) 또는 색인 IO 오류가 났다. 다시 실행하면 대개 통과한다. 백신·검색 색인기의 순간적인 파일 잠금으로 추정.

## 내용
- `store/retry.py`: `retry_io(fn, attempts=4, base_delay=0.2, retry_on=(PermissionError, OSError), sleep=time.sleep)` — 지수 대기, 마지막 실패는 원래 예외를 그대로 올림. 재시도 횟수를 반환값/로그로 남길 수 있게.
- `chroma_store.py`의 쓰기(`create_collection`, `add`, `delete_collection`)와 `memvid_store.py`의 쓰기(색인 생성·put·포인터 기록)를 `retry_io`로 감싼다. 읽기·검색은 감싸지 않는다. 동작·반환값은 그대로.
- `scripts/store_stress.py --store chroma|memvid --runs 10`: 임시 폴더에서 publish → reopen → search를 N번 반복하고 성공·재시도·실패 횟수를 표로 출력(대표가 Windows에서 두 저장소를 비교하는 용도).

## 시험 `tests/test_store_retry.py`
가짜 함수로: 2번 실패 후 성공, 재시도 소진 시 원래 예외, 재시도 대상이 아닌 예외는 즉시 올림, 대기 시간이 늘어남(sleep 주입). Chroma 쓰기 경로가 retry를 거치는지(가짜 실패 주입) 시험.

## 공통 규칙
- 저장소 `langchain-rag-research-agent`, 레인 브랜치에서 이전 명세 결과 위에 이어서 작업. 맥락: `docs/EQUALIZER_V0.ko.md`, `docs/HANDOFF_CODEX_PROTOTYPE_2026-11-09.md` 3절.
- 데이터 내용 수정 금지: `data/golden_rules/**`, `profiles/*.json`, `data/equalizer/**`, `data/golden_sets/**`.
- `tests/test_structure.py` 통과 유지(모듈 간 직접 import 금지, 조립은 `rag/`·`scripts/`에서). `KNOWN_DEBT` 증가 금지.
- 기존 시험 기대값 수정·skip·삭제 금지. 네트워크·LLM·`.env` 금지. push 금지.
- **작업이 끝나면 반드시 `git add`와 `git commit`으로 커밋한다**(커밋이 없으면 실패로 처리됨). 막히면 원인만 보고서에 적고, 그 보고서도 커밋한 뒤 멈춘다.
- 보고서: 구현·시험 통과 구분, 전체 시험 `n passed`, 한계·열린 질문.
