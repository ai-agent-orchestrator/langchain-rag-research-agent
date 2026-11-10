# memvid 의존 조사 — 2026-11-10 KST

## 범위와 결론

결정 문서와 AGENTS.md를 먼저 읽었다. 개발 기본값은 Chroma다. 이 조사는 읽기 전용이며 생산 코드, 의존성 선언, 기존 시험/marker를 변경하지 않았다. 보류된 버퍼 spike는 시작하지 않았다. 별도로 명시 요청된 X0 진단 확장은 개발 경로와 구분한다.

검색 범위는 숨김 설정을 포함한 저장소 텍스트 파일이다. `.git/`, `.venv/`, `.runs/`, egg-info는 생성물/외부 의존성이므로 제외했다. README는 읽기만 했으며 미커밋 내용을 보존한다. `memvid`, `.mv2`, memvid_store의 import/call을 검색했다. 작업 폴더 옛 이름 때문에 일치한 문서도 아래 부록에 보존했다. `.runs` 기존 결과는 학습 종합 보고서에서 별도 조사한다. 본 보고서와 새 학습/진단 보고서는 조사 결과 문서이며 스스로를 다시 목록화하지 않는다.

기본 import 검증: CLI, Library, LC 어댑터, guidance 및 E4~E8 평가 진입점 등 9개 모듈을 새 프로세스에서 memvid 이름의 모든 import를 차단하고 import했다. 9개 모두 성공, 차단 시도 0건. 모델 생성/인코딩/서재 쓰기는 실행하지 않았다. 근거: `.runs/store-import-audit.json`. 런타임 전체 경로의 완전한 증명은 아니지만 정적 조사에서도 memvid SDK는 명시 진단/어댑터 경로에만 있다. chromadb는 이 환경에 미설치여서 실제 Chroma 쓰기/재열기 검증은 **미검증**이다. 새 설치는 하지 않았다.

## 기능·공개 계약 대조

| 공개 계약/기능 | memvid 경로 | Chroma에 동일 기능이 이미 있는가 |
| --- | --- | --- |
| search_vector / search_lex / close, Chunk/score/rank | MemvidIndex, VectorStore | 있음: ChromaIndex. lexical term-match count, cosine 검색. SDK 점수 척도 동등성은 미검증 |
| 실패를 RetrievalUnavailable로 전달 | 어댑터 open/write/search | Chroma open/vector search 등에도 있음. 모든 예외 경계의 완전한 동등성은 미검증 |
| 외부 임베딩·차원 검사·텔레메트리 off | publish_index / load_memvid | 있음: publish_chroma / _client. 실제 실행은 chromadb 미설치로 미검증 |
| 불변 버전 발행 / list_versions | 버전별 .mv2와 manifest | **Chroma 경로에 없음**. publish_chroma는 같은 collection을 삭제/재생성함 |
| active/previous 원자 포인터 | active.json, os.replace | **Chroma 경로에 없음**. Library manifest 임시 파일 교체는 버전 포인터가 아님 |
| 파일 전체 SHA-256 manifest | IndexManifest.file/sha256, open_active 검증 | **같은 계약은 Chroma 경로에 없음**. Library에는 청크 content_hash·문서 hash·임베더 ID가 있지만 DB 전체 파일 해시/봉인과 다름 |
| activate/rollback 및 이전 버전 검증 | activate, previous, list_versions | **Chroma 경로에 없음** |
| prune, active/previous 보호 | prune | **Chroma 경로에 없음** |
| Library CRUD/문서 hash/임베더 identity | memvid 직접 대응 API 없음 | Chroma Library에 있음. memvid 생명주기 API의 호환 대체물은 아님 |

VectorStore Protocol에는 검색/close만 있고 버전 발행·rollback은 들어 있지 않다. 검색 인터페이스 호환이 생명주기 호환을 의미하지 않는다. Chroma의 내용 hash metadata 비교는 DB 바이트 위변조 검증과 같지 않다. 동일성 검증용 기능을 임의로 추가하지 않았다.

## 직접 의존과 기본 경로

| 항목 | (a) 개발 기본 경로 | (b) 영향 받는 공개 계약 | (c) Chroma 대응 |
| --- | --- | --- | --- |
| src/rag_research_agent/store/memvid_store.py | 아니오. SDK import는 load_memvid 내부, SDK use/put_many/seal/find/close는 이 어댑터 | publish_index/open_active/MemvidIndex/activate/list_versions/prune, IndexManifest | 검색만 대응. 버전/포인터/전체 파일 해시/rollback/prune 없음 |
| scripts/probe_memvid.py | 아니오. 명시 B02a 조사 | SDK 기능 probe, 합성 벡터·score·lex·seal/reopen | 개발 대체 대상 아님. 기존 out 예시는 docs/evidence이며 향후 실행 시 결과 .runs 원칙 필요(미수정) |
| scripts/diagnose_memvid_writes.py | 아니오. 명시 X0 조사 | 진단 JSON/SDK 쓰기 재현 | SDK 직접 진단이므로 Chroma 대체 의미 없음 |
| scripts/store_stress.py | --store 필수. chroma 분기에는 memvid import 없음 | publish→reopen→self retrieval, 실패/재시도 집계 | chroma 분기 있음. memvid 분기는 명시 opt-in |
| tests/test_memvid_store.py | 전체 시험에서는 실행. 앱 기본 경로 아님 | SDK publish/immutability/tamper/dimension/gate | 검색 외 생명주기 계약 Chroma 없음. 이미 모듈 memvid marker, 8개 시험 |
| tests/test_index_lifecycle.py | 전체 시험에서는 실행 | version/rollback/prune/tampered activation | Chroma 경로에 없음. 이미 모듈 memvid marker, 2개 시험 |
| tests/test_lexical_compatibility.py | 전체 시험 수집 시 memvid_store 모듈 import, SDK 로드는 안 함 | 과거 lex_terms import identity | 공용 core.lexical은 Chroma도 사용. 기존 import 호환 유지. marker 추가 안 함 |
| tests/test_memvid_diagnostics.py | 전체 시험 실행, fake SDK만 주입 | X0 최초 오류·close 오류 분리 / 재시도 없음 | SDK 미요구. memvid marker를 붙일 필요가 있다고 단정하지 않음 |
| pyproject.toml | base pydantic만. 그러나 all extra는 memvid 포함 | 설치 extra memvid/all, pytest marker 선언 | chroma extra 이미 있음. all 사용시 개발 설치가 SDK를 요구하는 결합 지점 |

## 격리·시험 처리 제안 — 구현하지 않음

1. 앱 기본 진입점은 이미 Chroma를 선택하며 memvid로 자동 fallback하지 않는다. import 경로 변경안은 현재 필요하지 않다. 실제 Chroma 실행은 의존성 미설치로 미검증이다.
2. 설치의 all extra는 memvid를 요구한다. 별도 개발 extra 또는 all의 구성 변경은 승인 후 별도 변경으로 제안한다. 이번에는 pyproject.toml을 바꾸지 않았다.
3. 이미 memvid marker가 있는 10개 시험을 활용해, 승인 후 개발용 명령을 `python -m pytest -q -p no:cacheprovider -m "not memvid"`로 구분하고 전체 시험은 별도 보존하는 방안을 제안한다. pytest addopts/CI/시험 marker/기대값/skip은 변경하지 않았고 이 필터를 기본 실행으로 적용하지 않았다. pure compatibility/진단 fake 시험은 SDK 쓰기 시험과 구분해야 한다.
4. 버전 발행/포인터/파일 해시/rollback/prune은 Chroma 경로에 없음으로 기록한다. 이전·대체 구현은 승인 전 진행하지 않는다.
5. README.ko, 설계의 일부 예전 표/다이어그램/학습 HTML에는 memvid를 기본 저장소처럼 설명하는 문구가 남아 있다. 채택된 결정 문서를 우선한다. 문구 정리는 별도 제안이며 이번에는 기존 문서를 수정하지 않는다.

## 전체 시험·보호 파일

전체 시험(필터 없음): `247 passed, 0 failed, 0 error, 5 skipped` (27.25s). 로그 `.runs/chroma-inventory-summary-pytest.txt`. 이번 실행에서 memvid 실패가 없었다는 관찰이며 안정화 증거는 아니다. 보호 18개 기준 `C:/myLectureWs/rra-p1-stage/merged-protected-before.json`과 SHA-256 모두 동일하다. 신규 설치, legal-intake 수정, main 병합은 하지 않았다.

추가 공용 경유점: `src/rag_research_agent/store/retry.py`는 memvid 어댑터와 Chroma가 함께 사용하는 IO 재시도 코드이며 SDK import는 없다. 공개 계약 retry_io/transient_write_error에 영향을 주는 정책 변경은 하지 않았다.

후속 진단에서 추가한 `tests/test_memvid_diagnostics_followup.py`는 진단 harness에 fake SDK를 주입하는 신규 시험이며 개발 앱 경로나 memvid SDK를 요구하지 않는다. 기존 marker/시험은 변경하지 않았다.

후속 환경 관찰: 초기 import 감사의 chromadb 미설치 관찰은 그 시점의 스냅샷이다. X0 확장 진단 이후 전체 시험에서는 Chroma가 사용 가능해졌고 `260 passed, 0 failed, 0 error, 1 skipped`였다. 본 작업에서 설치 명령은 실행하지 않았다. 상세 환경 혼입 한계는 X0 후속 보고서에 기록한다. 기존의 생명주기 기능 부재는 그대로다.

## 텍스트 참조 전체 부록

아래는 조사 시점 검색에 잡힌 각 파일의 (a) 기본 경로, (b) 계약, (c) Chroma 대응이다. 직접 의존 표와 중복되는 항목은 그 표를 따른다. 문서 참조는 실행 의존이 아니다.

| 파일 | (a) 기본 경로 | (b) 계약/참조 성격 | (c) Chroma 대응 |
| --- | --- | --- | --- |
| `.gitignore` | 런타임 없음 | *.mv2 생성 파일 제외 | 해당 없음(설정) |
| `AGENTS.md` | 런타임 없음(문서/명세/경로 문자열) | 설명·이력 참조, 실행 공개 계약 없음 | 해당 없음(문서); 현재 결정/기능 대조 표 우선 |
| `docs/C1_REPORT_2026-11-09.md` | 런타임 없음(문서/명세/경로 문자열) | 설명·이력 참조, 실행 공개 계약 없음 | 해당 없음(문서); 현재 결정/기능 대조 표 우선 |
| `docs/C11_REPORT_2026-11-10.md` | 런타임 없음(문서/명세/경로 문자열) | 설명·이력 참조, 실행 공개 계약 없음 | 해당 없음(문서); 현재 결정/기능 대조 표 우선 |
| `docs/C13_REPORT_2026-11-10.md` | 런타임 없음(문서/명세/경로 문자열) | 설명·이력 참조, 실행 공개 계약 없음 | 해당 없음(문서); 현재 결정/기능 대조 표 우선 |
| `docs/C14_REPORT_2026-11-10.md` | 런타임 없음(문서/명세/경로 문자열) | 설명·이력 참조, 실행 공개 계약 없음 | 해당 없음(문서); 현재 결정/기능 대조 표 우선 |
| `docs/C17_REPORT_2026-11-10.md` | 런타임 없음(문서/명세/경로 문자열) | 설명·이력 참조, 실행 공개 계약 없음 | 해당 없음(문서); 현재 결정/기능 대조 표 우선 |
| `docs/C2_REPORT_2026-11-09.md` | 런타임 없음(문서/명세/경로 문자열) | 설명·이력 참조, 실행 공개 계약 없음 | 해당 없음(문서); 현재 결정/기능 대조 표 우선 |
| `docs/C3_REPORT_2026-11-09.md` | 런타임 없음(문서/명세/경로 문자열) | 설명·이력 참조, 실행 공개 계약 없음 | 해당 없음(문서); 현재 결정/기능 대조 표 우선 |
| `docs/C4_REPORT_2026-11-09.md` | 런타임 없음(문서/명세/경로 문자열) | 설명·이력 참조, 실행 공개 계약 없음 | 해당 없음(문서); 현재 결정/기능 대조 표 우선 |
| `docs/C5_REPORT_2026-11-10.md` | 런타임 없음(문서/명세/경로 문자열) | 설명·이력 참조, 실행 공개 계약 없음 | 해당 없음(문서); 현재 결정/기능 대조 표 우선 |
| `docs/C7_REPORT_2026-11-10.md` | 런타임 없음(문서/명세/경로 문자열) | 설명·이력 참조, 실행 공개 계약 없음 | 해당 없음(문서); 현재 결정/기능 대조 표 우선 |
| `docs/C8_REPORT_2026-11-10.md` | 런타임 없음(문서/명세/경로 문자열) | 설명·이력 참조, 실행 공개 계약 없음 | 해당 없음(문서); 현재 결정/기능 대조 표 우선 |
| `docs/DECISION_STORE_CHROMA_2026-11-10.md` | 런타임 없음(문서/명세/경로 문자열) | 설명·이력 참조, 실행 공개 계약 없음 | 해당 없음(문서); 현재 결정/기능 대조 표 우선 |
| `docs/DESIGN_REVIEW.ko.md` | 런타임 없음(문서/명세/경로 문자열) | 설명·이력 참조, 실행 공개 계약 없음 | 해당 없음(문서); 현재 결정/기능 대조 표 우선 |
| `docs/DESIGN.ko.md` | 런타임 없음(문서/명세/경로 문자열) | 설명·이력 참조, 실행 공개 계약 없음 | 해당 없음(문서); 현재 결정/기능 대조 표 우선 |
| `docs/diagrams/01-architecture-overview.en.mmd` | 런타임 없음(문서/명세/경로 문자열) | 설명·이력 참조, 실행 공개 계약 없음 | 해당 없음(문서); 현재 결정/기능 대조 표 우선 |
| `docs/diagrams/01-architecture-overview.mmd` | 런타임 없음(문서/명세/경로 문자열) | 설명·이력 참조, 실행 공개 계약 없음 | 해당 없음(문서); 현재 결정/기능 대조 표 우선 |
| `docs/diagrams/05-repository-split.en.mmd` | 런타임 없음(문서/명세/경로 문자열) | 설명·이력 참조, 실행 공개 계약 없음 | 해당 없음(문서); 현재 결정/기능 대조 표 우선 |
| `docs/diagrams/05-repository-split.mmd` | 런타임 없음(문서/명세/경로 문자열) | 설명·이력 참조, 실행 공개 계약 없음 | 해당 없음(문서); 현재 결정/기능 대조 표 우선 |
| `docs/diagrams/06-concept-map.en.mmd` | 런타임 없음(문서/명세/경로 문자열) | 설명·이력 참조, 실행 공개 계약 없음 | 해당 없음(문서); 현재 결정/기능 대조 표 우선 |
| `docs/diagrams/06-concept-map.mmd` | 런타임 없음(문서/명세/경로 문자열) | 설명·이력 참조, 실행 공개 계약 없음 | 해당 없음(문서); 현재 결정/기능 대조 표 우선 |
| `docs/E3_REPORT_2026-11-10.md` | 런타임 없음(문서/명세/경로 문자열) | 설명·이력 참조, 실행 공개 계약 없음 | 해당 없음(문서); 현재 결정/기능 대조 표 우선 |
| `docs/evidence/M0/pytest_baseline.txt` | 런타임 없음(문서/명세/경로 문자열) | 설명·이력 참조, 실행 공개 계약 없음 | 해당 없음(문서); 현재 결정/기능 대조 표 우선 |
| `docs/evidence/M0/pytest_debt_after_2026-11-09_initial_io_error.txt` | 런타임 없음(문서/명세/경로 문자열) | 설명·이력 참조, 실행 공개 계약 없음 | 해당 없음(문서); 현재 결정/기능 대조 표 우선 |
| `docs/evidence/M0/pytest_debt_after_2026-11-09.txt` | 런타임 없음(문서/명세/경로 문자열) | 설명·이력 참조, 실행 공개 계약 없음 | 해당 없음(문서); 현재 결정/기능 대조 표 우선 |
| `docs/evidence/M1/pytest_main_after_m0_initial_env.txt` | 런타임 없음(문서/명세/경로 문자열) | 설명·이력 참조, 실행 공개 계약 없음 | 해당 없음(문서); 현재 결정/기능 대조 표 우선 |
| `docs/evidence/M1/pytest_main_after_m0.txt` | 런타임 없음(문서/명세/경로 문자열) | 설명·이력 참조, 실행 공개 계약 없음 | 해당 없음(문서); 현재 결정/기능 대조 표 우선 |
| `docs/FUTURE_MEMVID_BUFFER_SPIKE_2026-11-10.md` | 런타임 없음(문서/명세/경로 문자열) | 설명·이력 참조, 실행 공개 계약 없음 | 해당 없음(문서); 현재 결정/기능 대조 표 우선 |
| `docs/HANDOFF_CODEX_PROTOTYPE_2026-11-09.md` | 런타임 없음(문서/명세/경로 문자열) | 설명·이력 참조, 실행 공개 계약 없음 | 해당 없음(문서); 현재 결정/기능 대조 표 우선 |
| `docs/LEARNING_E6_2026-11-10.md` | 런타임 없음(문서/명세/경로 문자열) | 설명·이력 참조, 실행 공개 계약 없음 | 해당 없음(문서); 현재 결정/기능 대조 표 우선 |
| `docs/LEARNING_E8_2026-11-10.md` | 런타임 없음(문서/명세/경로 문자열) | 설명·이력 참조, 실행 공개 계약 없음 | 해당 없음(문서); 현재 결정/기능 대조 표 우선 |
| `docs/M0_BASELINE_BLOCKER_2026-11-09.md` | 런타임 없음(문서/명세/경로 문자열) | 설명·이력 참조, 실행 공개 계약 없음 | 해당 없음(문서); 현재 결정/기능 대조 표 우선 |
| `docs/M0_DEBT_REPORT_2026-11-09.md` | 런타임 없음(문서/명세/경로 문자열) | 설명·이력 참조, 실행 공개 계약 없음 | 해당 없음(문서); 현재 결정/기능 대조 표 우선 |
| `docs/M1_REAL_MEMVID_BASELINE_REPORT_2026-11-09.md` | 런타임 없음(문서/명세/경로 문자열) | 설명·이력 참조, 실행 공개 계약 없음 | 해당 없음(문서); 현재 결정/기능 대조 표 우선 |
| `docs/MODULE_DESIGN.ko.md` | 런타임 없음(문서/명세/경로 문자열) | 설명·이력 참조, 실행 공개 계약 없음 | 해당 없음(문서); 현재 결정/기능 대조 표 우선 |
| `docs/MODULE_STRUCTURE.md` | 런타임 없음(문서/명세/경로 문자열) | 설명·이력 참조, 실행 공개 계약 없음 | 해당 없음(문서); 현재 결정/기능 대조 표 우선 |
| `docs/P1_REPORT_2026-11-09.md` | 런타임 없음(문서/명세/경로 문자열) | 설명·이력 참조, 실행 공개 계약 없음 | 해당 없음(문서); 현재 결정/기능 대조 표 우선 |
| `docs/P2_REPORT_2026-11-09.md` | 런타임 없음(문서/명세/경로 문자열) | 설명·이력 참조, 실행 공개 계약 없음 | 해당 없음(문서); 현재 결정/기능 대조 표 우선 |
| `docs/P2B_REPORT_2026-11-10.md` | 런타임 없음(문서/명세/경로 문자열) | 설명·이력 참조, 실행 공개 계약 없음 | 해당 없음(문서); 현재 결정/기능 대조 표 우선 |
| `docs/P3_REPORT_2026-11-09.md` | 런타임 없음(문서/명세/경로 문자열) | 설명·이력 참조, 실행 공개 계약 없음 | 해당 없음(문서); 현재 결정/기능 대조 표 우선 |
| `docs/RAG_REVIEW_FOLLOWUP_2026-11-10.md` | 런타임 없음(문서/명세/경로 문자열) | 설명·이력 참조, 실행 공개 계약 없음 | 해당 없음(문서); 현재 결정/기능 대조 표 우선 |
| `docs/study/equalizer-study.html` | 런타임 없음(문서/명세/경로 문자열) | 설명·이력 참조, 실행 공개 계약 없음 | 해당 없음(문서); 현재 결정/기능 대조 표 우선 |
| `docs/X0_MEMVID_DIAGNOSIS_2026-11-10.md` | 런타임 없음(문서/명세/경로 문자열) | 설명·이력 참조, 실행 공개 계약 없음 | 해당 없음(문서); 현재 결정/기능 대조 표 우선 |
| `nightcoder_specs/codex/rra-c5-store-stability.md` | 런타임 없음(문서/명세/경로 문자열) | 설명·이력 참조, 실행 공개 계약 없음 | 해당 없음(문서); 현재 결정/기능 대조 표 우선 |
| `nightcoder_specs/README.md` | 런타임 없음(문서/명세/경로 문자열) | 설명·이력 참조, 실행 공개 계약 없음 | 해당 없음(문서); 현재 결정/기능 대조 표 우선 |
| `nightcoder_specs/start_night.ps1` | 런타임 없음(문서/명세/경로 문자열) | 설명·이력 참조, 실행 공개 계약 없음 | 해당 없음(문서); 현재 결정/기능 대조 표 우선 |
| `pyproject.toml` | 직접 의존 표 참조 | 위 직접 의존 표의 계약 | 위 계약별 대조 참조 |
| `README.ko.md` | 런타임 없음(문서/명세/경로 문자열) | 설명·이력 참조, 실행 공개 계약 없음 | 해당 없음(문서); 현재 결정/기능 대조 표 우선 |
| `README.md` | 런타임 없음(문서/명세/경로 문자열) | 설명·이력 참조, 실행 공개 계약 없음 | 해당 없음(문서); 현재 결정/기능 대조 표 우선 |
| `scripts/diagnose_memvid_writes.py` | 직접 의존 표 참조 | 위 직접 의존 표의 계약 | 위 계약별 대조 참조 |
| `scripts/probe_memvid.py` | 직접 의존 표 참조 | 위 직접 의존 표의 계약 | 위 계약별 대조 참조 |
| `scripts/store_stress.py` | 직접 의존 표 참조 | 위 직접 의존 표의 계약 | 위 계약별 대조 참조 |
| `src/rag_research_agent/core/contracts.py` | SDK 호출 없음(공용 코드/주석/구조 시험) | 문자열 참조 또는 공용 계약; SDK 의존 아님 | 검색/lexical 공용; 버전 계약은 기능 대조 표 참조 |
| `src/rag_research_agent/core/lexical.py` | SDK 호출 없음(공용 코드/주석/구조 시험) | 문자열 참조 또는 공용 계약; SDK 의존 아님 | 검색/lexical 공용; 버전 계약은 기능 대조 표 참조 |
| `src/rag_research_agent/guard/network.py` | SDK 호출 없음(공용 코드/주석/구조 시험) | 문자열 참조 또는 공용 계약; SDK 의존 아님 | 검색/lexical 공용; 버전 계약은 기능 대조 표 참조 |
| `src/rag_research_agent/lab/hybrid.py` | SDK 호출 없음(공용 코드/주석/구조 시험) | 문자열 참조 또는 공용 계약; SDK 의존 아님 | 검색/lexical 공용; 버전 계약은 기능 대조 표 참조 |
| `src/rag_research_agent/rag/library.py` | SDK 호출 없음(공용 코드/주석/구조 시험) | 문자열 참조 또는 공용 계약; SDK 의존 아님 | 검색/lexical 공용; 버전 계약은 기능 대조 표 참조 |
| `src/rag_research_agent/store/chroma_store.py` | SDK 호출 없음(공용 코드/주석/구조 시험) | 문자열 참조 또는 공용 계약; SDK 의존 아님 | 검색/lexical 공용; 버전 계약은 기능 대조 표 참조 |
| `src/rag_research_agent/store/memvid_store.py` | 직접 의존 표 참조 | 위 직접 의존 표의 계약 | 위 계약별 대조 참조 |
| `src/rag_research_agent/store/protocols.py` | SDK 호출 없음(공용 코드/주석/구조 시험) | 문자열 참조 또는 공용 계약; SDK 의존 아님 | 검색/lexical 공용; 버전 계약은 기능 대조 표 참조 |
| `tests/fixtures/synthetic_guides/README.md` | SDK 호출 없음(공용 코드/주석/구조 시험) | 문자열 참조 또는 공용 계약; SDK 의존 아님 | 검색/lexical 공용; 버전 계약은 기능 대조 표 참조 |
| `tests/test_chroma_store.py` | SDK 호출 없음(공용 코드/주석/구조 시험) | 문자열 참조 또는 공용 계약; SDK 의존 아님 | 검색/lexical 공용; 버전 계약은 기능 대조 표 참조 |
| `tests/test_contracts.py` | SDK 호출 없음(공용 코드/주석/구조 시험) | 문자열 참조 또는 공용 계약; SDK 의존 아님 | 검색/lexical 공용; 버전 계약은 기능 대조 표 참조 |
| `tests/test_index_lifecycle.py` | 직접 의존 표 참조 | 위 직접 의존 표의 계약 | 위 계약별 대조 참조 |
| `tests/test_lexical_compatibility.py` | 직접 의존 표 참조 | 위 직접 의존 표의 계약 | 위 계약별 대조 참조 |
| `tests/test_memvid_diagnostics.py` | 직접 의존 표 참조 | 위 직접 의존 표의 계약 | 위 계약별 대조 참조 |
| `tests/test_memvid_store.py` | 직접 의존 표 참조 | 위 직접 의존 표의 계약 | 위 계약별 대조 참조 |
| `tests/test_structure.py` | SDK 호출 없음(공용 코드/주석/구조 시험) | 문자열 참조 또는 공용 계약; SDK 의존 아님 | 검색/lexical 공용; 버전 계약은 기능 대조 표 참조 |

## 2026-11-10 설치 후 재조사 (현재 코드 기준)

앞의 미설치/import 감사/247 passed 및 후속 260 passed 기록은 이전 실행 이력이다. 이번 재조사는 SDK를 새로 실행하지 않고 현재 소스·시험·스크립트·문서의 참조를 읽었다. 실제 Chroma 1.5.9 + fake 임베더 경로 재확인 결과는 CHROMA_INTEGRATION_RECHECK_2026-11-10.md를 따른다. SDK 안정성 개선·동등성 완전 입증은 미검증이다.

| 기능/공개 계약 | 현재 Chroma 경로 |
| --- | --- |
| 불변 버전 발행 / list_versions | Chroma 경로에 없음 |
| active/previous 원자 활성화 포인터 | Chroma 경로에 없음 |
| DB 전체 SHA-256 해시 manifest | Chroma 경로에 없음 |
| activate에 의한 롤백/roll forward | Chroma 경로에 없음 |
| 신뢰 manifest 대비 파일 전체 변조 거절 | Chroma 경로에 없음 |
| IDs·metadata content_hash 불일치 및 임베더 identity/차원 거절 | 일부 있음: Library.open/verify, ChromaIndex.verify/search_vector. 전체 파일 해시와 동일 계약 아님 |

Chroma publish_chroma는 같은 collection을 삭제 후 재생성한다. Library의 manifest 임시 파일 replace는 활성화 버전 포인터가 아니다. verify는 저장된 metadata hash와 manifest hash를 비교하며 문서·벡터의 모든 실제 바이트를 재해싱하지 않는다. metadata를 유지한 채 본문/벡터만 바꾼 모든 변조 거절은 미검증이다. VectorStore Protocol은 search_vector/search_lex/close만 규정한다. 따라서 검색 어댑터 대체 가능성과 버전 생명주기 호환은 별개다. 대체 구현·retry 변경은 하지 않았다.

검색 명령은 `.runs/chroma-recheck-20261110/memvid-references.txt`의 원시 일치 목록으로 보존했다. `rg -n -i --hidden --no-ignore 'memvid|\.mv2'`로 저장소를 검색하고 .git/.venv*/.runs/**/__pycache__/**/egg-info 생성물을 제외했다. 문서의 실행 예시, 경로 문자열, 역사적 참조도 포함했다. 아래 파일별 (c)의 생명주기 계약은 위 다섯 기능을 뜻한다. 문서만 참조하는 항목의 생명주기 실행 계약은 없다. 이 보고서와 새 재확인 보고서는 자체 참조 목록에서 제외한다. 우회한 문자열 조립·외부 저장소/외부 패키지 내부의 동적 호출 전체는 미검증이다.

| 파일 | (a) 개발 기본 경로에 걸리는가 | (b) 대체 시 영향 받는 공개 계약/참조 | (c) 현재 Chroma 대응 |
| --- | --- | --- | --- |
| `.gitignore` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `AGENTS.md` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `README.ko.md` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `README.md` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `docs/C11_REPORT_2026-11-10.md` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `docs/C13_REPORT_2026-11-10.md` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `docs/C14_REPORT_2026-11-10.md` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `docs/C17_REPORT_2026-11-10.md` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `docs/C1_REPORT_2026-11-09.md` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `docs/C2_REPORT_2026-11-09.md` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `docs/C3_REPORT_2026-11-09.md` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `docs/C4_REPORT_2026-11-09.md` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `docs/C5_REPORT_2026-11-10.md` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `docs/C7_REPORT_2026-11-10.md` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `docs/C8_REPORT_2026-11-10.md` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `docs/DECISION_STORE_CHROMA_2026-11-10.md` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `docs/DESIGN.ko.md` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `docs/DESIGN_REVIEW.ko.md` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `docs/E3_REPORT_2026-11-10.md` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `docs/FUTURE_MEMVID_BUFFER_SPIKE_2026-11-10.md` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `docs/HANDOFF_CODEX_PROTOTYPE_2026-11-09.md` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `docs/LEARNING_E6_2026-11-10.md` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `docs/LEARNING_E8_2026-11-10.md` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `docs/LEARNING_SUMMARY_2026-11-10.md` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `docs/M0_BASELINE_BLOCKER_2026-11-09.md` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `docs/M0_DEBT_REPORT_2026-11-09.md` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `docs/M1_REAL_MEMVID_BASELINE_REPORT_2026-11-09.md` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `docs/MODULE_DESIGN.ko.md` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `docs/MODULE_STRUCTURE.md` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `docs/P1_REPORT_2026-11-09.md` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `docs/P2B_REPORT_2026-11-10.md` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `docs/P2_REPORT_2026-11-09.md` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `docs/P3_REPORT_2026-11-09.md` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `docs/RAG_REVIEW_FOLLOWUP_2026-11-10.md` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `docs/X0_MEMVID_DIAGNOSIS_2026-11-10.md` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `docs/X0_MEMVID_DIAGNOSIS_FOLLOWUP_2026-11-10.md` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `docs/diagrams/01-architecture-overview.en.mmd` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `docs/diagrams/01-architecture-overview.mmd` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `docs/diagrams/05-repository-split.en.mmd` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `docs/diagrams/05-repository-split.mmd` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `docs/diagrams/06-concept-map.en.mmd` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `docs/diagrams/06-concept-map.mmd` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `docs/evidence/M0/pytest_baseline.txt` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `docs/evidence/M0/pytest_debt_after_2026-11-09.txt` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `docs/evidence/M0/pytest_debt_after_2026-11-09_initial_io_error.txt` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `docs/evidence/M1/pytest_main_after_m0.txt` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `docs/evidence/M1/pytest_main_after_m0_initial_env.txt` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `docs/study/equalizer-study.html` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `nightcoder_specs/README.md` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `nightcoder_specs/codex/rra-c5-store-stability.md` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `nightcoder_specs/start_night.ps1` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `pyproject.toml` | base 아님; memvid/all extra 설치 시 결합 | memvid-sdk==2.0.160, memvid/all extra, pytest marker | chroma extra 있음; 생명주기 Chroma 경로에 없음 |
| `scripts/diagnose_memvid_writes.py` | 아니오; 명시 진단 | load_memvid → SDK 쓰기/핸들 조건; rra-memvid-write-diagnostics/2 | SDK 진단 대체 해당 없음; 생명주기 Chroma 경로에 없음 |
| `scripts/probe_memvid.py` | 아니오; 명시 진단 | load_memvid → SDK use/put_many/seal/find/close; capability JSON | SDK 진단 대체 해당 없음; 생명주기 Chroma 경로에 없음 |
| `scripts/store_stress.py` | --store memvid에만 걸림; chroma 분기 SDK import 없음 | publish_index/open_active; publish/reopen/self-search/집계 | Chroma 분기 검색 있음; 버전 계약 Chroma 경로에 없음 |
| `src/rag_research_agent/core/contracts.py` | 예; SDK import 없음 | Chunk/IndexManifest/Query/Evidence/Outcome/오류 계약 | Chunk/검색 공용; IndexManifest 생명주기 Chroma 경로에 없음 |
| `src/rag_research_agent/core/lexical.py` | 예; SDK import 없음 | lex_terms 공용 토큰 규칙; memvid는 주석 | 공용 함수 사용; 생명주기 Chroma 경로에 없음 |
| `src/rag_research_agent/guard/network.py` | 공용 보안 경유; SDK import 없음 | memvid 자동 임베딩 방지와 MEMVID_TELEMETRY 설정 | Chroma는 자체 telemetry off; 생명주기 Chroma 경로에 없음 |
| `src/rag_research_agent/lab/hybrid.py` | 선택 lab; SDK import 없음 | RRF; memvid는 예시 주석 | 융합은 저장소 외부 공용; 생명주기 Chroma 경로에 없음 |
| `src/rag_research_agent/rag/library.py` | 예; SDK import/호출 없음 | Library build/open/CRUD/search/brief; Chroma 명시 선택 | Chroma Library 있음; 버전/포인터/파일 해시/롤백 Chroma 경로에 없음 |
| `src/rag_research_agent/store/chroma_store.py` | 예; memvid는 비교 주석만 | publish_chroma/ChromaIndex search/verify/count/close | Chroma 구현; 버전/포인터/파일 해시/롤백 Chroma 경로에 없음 |
| `src/rag_research_agent/store/memvid_store.py` | 아니오; 명시 memvid 어댑터 | load_memvid, publish_index, open_active, MemvidIndex, activate, list_versions, prune; IndexManifest | 검색 대응; 버전/포인터/파일 해시/롤백/동일 변조 거절은 Chroma 경로에 없음 |
| `src/rag_research_agent/store/protocols.py` | 공용 계약; SDK import 없음 | VectorStore search_vector/search_lex/close | 동일 검색 표면 있음; 생명주기 Chroma 경로에 없음 |
| `tests/fixtures/synthetic_guides/README.md` | 런타임 없음; 문서·명세·증거·설정 참조 | memvid 언급/실행 예시/과거 작업 경로; 실행 공개 API 계약 없음 | 문서 자체는 대체 대상 아님; 생명주기 Chroma 경로에 없음 |
| `tests/test_chroma_store.py` | 전체 시험; 실제 Chroma | publish/verify/vector/lex/metadata tamper/dimension/telemetry | 검색과 부분 불일치 거절 있음; 파일 전체 해시 계약 Chroma 경로에 없음 |
| `tests/test_contracts.py` | 전체 시험; SDK 실행 없음 | IndexManifest 값/모델 identity/중복 계약; .mv2 문자열 | 공용 값 계약; 파일 버전 생명주기 Chroma 경로에 없음 |
| `tests/test_index_lifecycle.py` | 앱 기본 아니오; 전체 시험 실행 | activate/list_versions/prune/open_active/publish_index; rollback, tampered activation | Chroma 경로에 없음 |
| `tests/test_lexical_compatibility.py` | SDK 실행 없음; 전체 시험에서 호환 import | memvid_store.lex_terms와 core.lexical.lex_terms 함수 identity | 공용 lex_terms를 Chroma도 사용; 생명주기 Chroma 경로에 없음 |
| `tests/test_memvid_diagnostics.py` | 앱 기본 아니오; fake SDK 시험 | 진단 trial의 최초 오류/close 처리; 동적 모듈 import | 진단 fake 시험 대체 해당 없음; 생명주기 Chroma 경로에 없음 |
| `tests/test_memvid_diagnostics_followup.py` | 앱 기본 아니오; fake SDK 시험 | 진단 trial delay/inspection/close-only/Wilson/schema; 동적 모듈 import | 진단 fake 시험 대체 해당 없음; 생명주기 Chroma 경로에 없음 |
| `tests/test_memvid_store.py` | 앱 기본 아니오; 전체 시험 실행 | publish/open, 불변 버전, hash/identity/dimension 거절, 게이트, batch | 검색·차원 대응; 생명주기/파일 변조 계약 Chroma 경로에 없음 |
| `tests/test_structure.py` | 전체 시험; SDK 실행 없음 | 선택 의존성 import 격리 AST 검사 | Chroma 대체 구현 대상 아님; 생명주기 Chroma 경로에 없음 |
| `uv.lock` | 앱 런타임 아님; 로컬 비추적 lock의 설치 해석 시 결합 | 옛 memvid-guardrail 프로젝트명과 memvid/all extra, SDK 2.0.160 잠금. 현 pyproject와 동기화 여부 미검증; 수정/설치하지 않음 | 현 pyproject에는 chroma extra 있음; 생명주기 Chroma 경로에 없음 |

공용 비직접 경유: `src/rag_research_agent/store/retry.py`의 retry_io/transient_write_error는 두 어댑터가 사용한다. SDK import 없음. 정책을 변경하지 않았다. 개발 기본 Library 및 E1/E5/E7 실행에서 memvid_sdk import는 차단했으며 통과한 E1·E3 경로와 실패한 E5/E7 모두 차단 위반은 없었다. 실패가 정리 단계에서 발생했으므로 E5/E7 전체 성공을 입증하지 않는다.

이번 전체 시험: **257 passed, 2 failed, 1 error, 1 skipped** (26.97s). memvid MV999 쓰기 실패 1개 + setup error 1개와 실행 환경이 유발한 tracing 대조 실패 1개를 숨기지 않았다. tracing 단독 대조는 환경변수 충돌 제거 후 1 passed이며 전체 시험 수치를 대체하지 않는다. memvid 재시험 없음. 보호 18개 SHA-256 기준·작업 전후 모두 동일. 증거는 `.runs/chroma-recheck-20261110/pytest-summary.json`, `pytest.log`, `protected-sha256.json`.
