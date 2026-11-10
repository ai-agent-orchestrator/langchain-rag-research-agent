files: src/rag_research_agent/store/chroma_store.py, src/rag_research_agent/rag/library.py, tests/test_chroma_owners.py, docs/N1_REPORT_2026-11-10.md
forbid: src/rag_research_agent/store/memvid_store.py, src/rag_research_agent/store/retry.py, src/rag_research_agent/observe/tracing.py, data/**, profiles/**, .env*
effort: medium
coder: codex

# N1: Chroma 클라이언트 소유권 정리 (남은 WinError 32 경고 줄이기)

## 배경
docs/CHROMA_CLEANUP_FIX_2026-11-10.md: 평가 중단은 해결됐지만 E5/E7 임시 폴더 삭제는 10/10회 경고로 남았다.
원인 후보로 확인된 것: `publish_chroma`의 별도 쓰기 클라이언트에 close가 없고, `Library._collection` 등
다른 클라이언트 수명이 미정리. SDK refcount가 4→2로만 줄었다. 정확한 핸들 소유자는 미확정이다.
AGENTS.md를 먼저 읽는다 (개발 기본 저장소는 Chroma, memvid 제외).

## 할 일
1. 재현: fake 임베더로 Library를 build→search→close한 뒤 같은 프로세스에서 서재 폴더 삭제를 시도하는
   최소 스크립트를 `.runs/n1/`에 만들고, 클라이언트·컬렉션을 만드는 모든 지점을 목록화한다
   (chroma_store.py와 library.py). 소스를 읽고 확인한 것만 적는다.
2. 수정: 만든 클라이언트를 닫는 책임이 명확하도록 한다. 공개 API(`client.close()`)만 사용하고
   Chroma 비공개 속성·공유 캐시 조작, 강제 종료는 하지 않는다. 점수·검색 로직은 바꾸지 않는다.
3. 시험 `tests/test_chroma_owners.py` 추가 (기존 시험 수정·skip 금지):
   Library build/close 후 같은 경로 삭제 성공 여부, close 두 번 호출 안전, publish 후 쓰기 클라이언트 해제.
   삭제 성공 여부가 환경(Windows)에 달렸다면 결과를 단정하지 말고 관찰값을 보고서에 적는다.
   시험이 환경 의존으로 불안정하면 시험은 "close가 호출되었는가"(참조·호출 검증)로 한정한다.
4. 효과 측정: 수정 전·후로 fake 임베더 E5/E7(vector) 경로를 각각 5회 실행해 임시 폴더 삭제 경고 수를 비교한다.
   개선이 없으면 개선이 없다고 쓴다.

## 보고서 docs/N1_REPORT_2026-11-10.md
확인된 것 / 수정한 것 / 효과(수정 전·후 경고 횟수, 표본 수 명시) / 미해결·미검증.
핸들 소유자를 단정하지 않는다.

## 공통 규칙
데이터(`data/**`), `profiles/**`, 보호 파일, 기존 시험 기대값 수정·skip 금지, `KNOWN_DEBT` 증가 금지,
LangChain·LangGraph·LangSmith import는 `rag/` 어댑터 파일에만, 네트워크·모델 다운로드·실제 모델 실행·LLM 호출 금지.
memvid 코드·retry 정책 변경 금지. 전체 시험을 `n passed / failed / error / skipped`로 그대로 기록한다
(기존 memvid 간헐 실패는 숨기지 않고 기록). **끝나면 반드시 커밋.** 막히면 원인만 보고서에 적고 커밋 후 멈춤.
