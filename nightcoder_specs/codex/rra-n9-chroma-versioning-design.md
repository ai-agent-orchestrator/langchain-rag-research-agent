files: docs/CHROMA_VERSIONING_DESIGN_2026-11-10.md, docs/N9_REPORT_2026-11-10.md
forbid: src/rag_research_agent/observe/tracing.py, src/rag_research_agent/store/memvid_store.py, data/**, profiles/**, .env*
effort: low
coder: codex
status: ready
order: 90
repo: research

# N9: Chroma 경로의 버전 발행·롤백 설계 문서 (구현 없음)

## 배경
docs/MEMVID_DEPENDENCY_INVENTORY_2026-11-10.md: 불변 버전 발행, active/previous 포인터, 전체 파일 해시 manifest, 롤백, prune,
변조 거절이 Chroma 경로에 없다. 필요 여부는 대표가 결정한다. 결정에 필요한 설계 비교만 만든다.

## 할 일 (문서만, 코드 변경 없음)
`docs/CHROMA_VERSIONING_DESIGN_2026-11-10.md`:
1. memvid 경로의 기존 계약을 소스에서 확인해 요약(publish_index, open_active, activate, list_versions, prune, IndexManifest).
2. Chroma에서 같은 계약을 만드는 방안 2~3개 비교: (a) 버전별 persist 디렉터리 + 포인터 파일 + 디렉터리 해시 manifest,
   (b) 컬렉션 이름에 버전 부여, (c) 기타. 각 방안의 원자성(Windows 파일 교체·잠금 포함, CHROMA_CLEANUP_FIX 보고서의 WinError 32 관찰 반영),
   디스크 비용, 롤백 시간, 변조 탐지 범위, 구현 크기.
3. 권장안과 단계별 구현 계획(명세 크기로 나눔), 그리고 "하지 않을 경우의 위험".
추정과 확인을 구분한다. Chroma SDK 동작은 설치된 버전(1.5.9) 소스에서 확인한 것만 사실로 쓴다.

## 보고서 docs/N9_REPORT_2026-11-10.md
문서 요약, 확인한 소스 위치, 미확인 사항.

## 공통 규칙
AGENTS.md를 먼저 읽고 따른다(개발 저장소는 Chroma, memvid 제외, 5절 NightCoder 레인 규칙).
데이터(`data/**`), `profiles/**`, 보호 파일, 기존 시험 기대값 수정·skip 금지, `KNOWN_DEBT` 증가 금지.
새 모듈은 기존 구조 시험(`tests/test_structure.py`)의 배치·성숙도 규칙을 따른다(같은 폴더의 기존 모듈 선언을 참고).
LangChain·LangGraph·LangSmith import는 `rag/` 어댑터 파일에만. 네트워크·모델 다운로드·실제 모델 실행·LLM 호출 금지.
`files:`에 없는 기존 파일은 수정하지 않는다(필요하면 보고서에 "후속 연결 필요"로 적는다).
시험 이름과 내용은 실제 동작을 검증해야 하며, 가짜 통과(무조건 참)를 만들지 않는다.
보고서: 구현 / 시험 / 입증하지 못한 것(미검증)을 구분한다. **끝나면 반드시 커밋.** 막히면 원인만 보고서에 적고 커밋 후 멈춤.
