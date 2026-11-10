files: src/rag_research_agent/rag/library.py, scripts/library_board.py, tests/test_library_incremental.py, docs/C6_REPORT_2026-11-10.md
forbid: data/**, profiles/**, src/rag_research_agent/store/**, .env*
effort: high
coder: codex

# C6: 자료 서재 증분 추가·삭제

## 배경
`rag/library.py`의 `Library.build`는 매번 컬렉션 전체를 다시 만든다. 대표가 기사를 하나씩 추가하며 쓰려면 증분이 필요하다.

## 내용
- `Library.add(docs)`: 문서별 내용 해시를 manifest에 기록. 같은 `doc_id`에 같은 해시면 건너뜀, 내용이 바뀌면 그 문서의 조각만 교체, 새 문서는 추가. 반환: 추가·교체·건너뜀 개수.
- `Library.remove(doc_id)`, `Library.documents()`(문서 ID, 제목, 조각 수, 해시, 추가 시각).
- Chroma 컬렉션에 직접 `add`/`delete`를 하되 `store/chroma_store.py`는 수정하지 않는다(필요하면 `ChromaIndex`의 공개 속성만 사용하고, 부족하면 보고서에 제안). manifest와 컬렉션이 어긋나면 `verify()`가 잡는다.
- `scripts/library_board.py`: `--add`가 증분으로 동작(`--rebuild` 옵션으로 전체 재구성), 보드에 문서 목록 표 추가.

## 시험
추가 → 같은 문서 재추가는 건너뜀 → 내용 변경 시 교체 → 삭제 → 재오픈 후 검색 결과 일치. Chroma 미설치면 명시적 skip(기존 방식).

## 공통 규칙
- 저장소 `langchain-rag-research-agent`, 레인 브랜치에서 이전 명세 결과 위에 이어서 작업. 맥락: `docs/EQUALIZER_V0.ko.md`, `docs/HANDOFF_CODEX_PROTOTYPE_2026-11-09.md` 3절.
- 데이터 내용 수정 금지: `data/golden_rules/**`, `profiles/*.json`, `data/equalizer/**`, `data/golden_sets/**`.
- `tests/test_structure.py` 통과 유지(모듈 간 직접 import 금지, 조립은 `rag/`·`scripts/`에서). `KNOWN_DEBT` 증가 금지.
- 기존 시험 기대값 수정·skip·삭제 금지. 네트워크·LLM·`.env` 금지. push 금지.
- **작업이 끝나면 반드시 `git add`와 `git commit`으로 커밋한다**(커밋이 없으면 실패로 처리됨). 막히면 원인만 보고서에 적고, 그 보고서도 커밋한 뒤 멈춘다.
- 보고서: 구현·시험 통과 구분, 전체 시험 `n passed`, 한계·열린 질문.
