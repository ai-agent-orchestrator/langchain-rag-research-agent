# 문서 색인

2026-11-10 KST. 현재 체크아웃의 docs/ 문서를 종류별로 연결한다. 개발 기본값은 [Chroma 결정](DECISION_STORE_CHROMA_2026-11-10.md)을 따른다. 과거 문서의 상태·명령은 작성 당시 기록이며 현재 결정과 함께 읽는다.

시험 기록은 원문의 수치가 있는 줄을 그대로 인용한다. 여러 실행은 합치거나 최신 수치로 덮어쓰지 않는다. fake 경로 시험과 실제 모델 결과는 각 원문에서 별도로 확인한다. 수치가 없는 문서는 원문을 연결하며 시험 결과를 추정하지 않는다.

## 설계

- [DESIGN.ko.md](DESIGN.ko.md) — 설계 정본 v1.0 — langchain-rag-research-agent (Edge Equalizer).
- [DESIGN_REVIEW.ko.md](DESIGN_REVIEW.ko.md) — 설계 검수·보완 보고서 — langchain-rag-research-agent (엣지 보존 인풋 아키텍처).
- [MODULE_DESIGN.ko.md](MODULE_DESIGN.ko.md) — 모듈 설계안 v0.2 — 법률 검색·리서치에서 재사용하는 RAG·보안 백엔드 모듈.
- [MODULE_STRUCTURE.md](MODULE_STRUCTURE.md) — Module structure (M0).

  > Before rename (main 051dc47): 44 passed, 4 failed, 4 errors. After M0: 57 passed, same 4 failed, same 4 errors. All 8 are in `test_memvid_store.py` / `test_index_lifecycle.py` and fail with `ModuleNotFoundError: memvid_sdk`; they need the `memvid` extra and were not run against the real SDK here.

- [EQUALIZER_V0.ko.md](EQUALIZER_V0.ko.md) — Equalizer v0 — 갈아 끼우는 부품 구조.
- [CHROMA_VERSIONING_DESIGN_2026-11-10.md](CHROMA_VERSIONING_DESIGN_2026-11-10.md) — Chroma 버전 발행·롤백 설계 비교 — 2026-11-10.
- [GOLDEN_RULES.ko.md](GOLDEN_RULES.ko.md) — 리서치 골든룰 v1 (초안).
- [GOLDEN_RULES_CATALOG.ko.md](GOLDEN_RULES_CATALOG.ko.md) — 골든룰 카탈로그: research-v1-150-draft.
- [GOLDEN_SET_GUIDE.ko.md](GOLDEN_SET_GUIDE.ko.md) — RAG 골든셋 가이드 (공부 + 설계 v2).

## 단계 보고서 P / C / E / X / N

- [C1_REPORT_2026-11-09.md](C1_REPORT_2026-11-09.md) — C1 인과 쌍 링크.

  > 요청한 전체 시험: **150 passed, 1 failed, 1 error, 2 skipped in 23.32s**.

- [C10_REPORT_2026-11-10.md](C10_REPORT_2026-11-10.md) — C10 예측 기록장.

  > 전체 시험: **181 passed, 1 failed, 3 skipped in 28.17s**.

- [C11_REPORT_2026-11-10.md](C11_REPORT_2026-11-10.md) — C11 신호 표현 추천 도우미.

  > → **183 passed, 1 failed, 3 skipped in 25.55s** (종료 코드 1).

- [C12_REPORT_2026-11-10.md](C12_REPORT_2026-11-10.md) — C12 로컬 임베딩 레지스트리.

  > 전체 시험: **186 passed, 1 failed, 3 skipped in 25.83s**.

- [C13_REPORT_2026-11-10.md](C13_REPORT_2026-11-10.md) — C13 임베딩 비교·보정 도구.

  > 전체 시험: **186 passed, 2 failed, 1 error, 3 skipped in 23.50s**.

- [C14_REPORT_2026-11-10.md](C14_REPORT_2026-11-10.md) — C14 Kiwi lab 실험.

  > 전체 시험: **188 passed, 3 failed, 4 skipped in 20.91s**.

- [C16_REPORT_2026-11-10.md](C16_REPORT_2026-11-10.md) — C16 보안 패키지 연결.

  > 전체 시험: **208 passed, 4 skipped in 27.85s**, 종료 코드 0.

- [C17_REPORT_2026-11-10.md](C17_REPORT_2026-11-10.md) — C17 검색 골든셋 v2 도구.

  > 전체 시험: **191 passed, 3 failed, 4 skipped in 25.61s**.

- [C2_REPORT_2026-11-09.md](C2_REPORT_2026-11-09.md) — C2 골든셋 만들기 도구.

  > 전체 시험: **152 passed, 3 failed, 2 skipped in 20.21s**.

- [C3_REPORT_2026-11-09.md](C3_REPORT_2026-11-09.md) — C3 한국어 문장 분할 (미완료).

  > 요청한 전체 시험: **160 passed, 2 failed, 2 errors, 2 skipped in 18.18s**.

- [C4_REPORT_2026-11-09.md](C4_REPORT_2026-11-09.md) — C4 의미 관련도 부품 (보정 전).

  > 전체 시험: **165 passed, 2 failed, 2 skipped in 23.50s**.

- [C5_REPORT_2026-11-10.md](C5_REPORT_2026-11-10.md) — C5 쓰기 재시도·반복 점검 도구.

  > 전체 시험: **169 passed, 1 failed, 2 skipped in 24.80s**.

- [C6_REPORT_2026-11-10.md](C6_REPORT_2026-11-10.md) — C6 증분 서재.

  > 전체 시험: **171 passed, 1 failed, 3 skipped in 24.55s**.

- [C7_REPORT_2026-11-10.md](C7_REPORT_2026-11-10.md) — C7 원문 수치 추출표.

  > 전체 시험: **172 passed, 1 failed, 1 error, 3 skipped in 24.32s**.

- [C8_REPORT_2026-11-10.md](C8_REPORT_2026-11-10.md) — C8 C1·C4 조립 연결.

  > 전체 시험: **174 passed, 1 failed, 1 error, 3 skipped in 31.10s**.

- [C9_REPORT_2026-11-10.md](C9_REPORT_2026-11-10.md) — C9 필터 차이·실행 추이 보드.

  > 전체 시험: **178 passed, 1 failed, 3 skipped in 27.09s**.

- [E1_REPORT_2026-11-10.md](E1_REPORT_2026-11-10.md) — E1 LangChain 출구.

  > 전체 시험: **212 passed, 5 skipped in 28.17s**, 종료 코드 0.

- [E2_REPORT_2026-11-10.md](E2_REPORT_2026-11-10.md) — E2 근거 부족 재검색 루프.

  > 전체 시험: **216 passed, 5 skipped in 26.10s**, 종료 코드 0.

- [E3_REPORT_2026-11-10.md](E3_REPORT_2026-11-10.md) — E3 LangSmith 로컬 내보내기.

  > 전체 시험: **218 passed, 1 failed, 1 error, 5 skipped in 25.09s**, 종료 코드 1.

- [N5_REPORT_2026-11-10.md](N5_REPORT_2026-11-10.md) — N5: BoundedWorker 부하·취소 시험.
- [N8_REPORT_2026-11-10.md](N8_REPORT_2026-11-10.md) — N8: 비식별 로컬 메트릭 기록기.
- [N9_REPORT_2026-11-10.md](N9_REPORT_2026-11-10.md) — N9 보고서 — Chroma 버전 발행·롤백 설계.
- [P1_REPORT_2026-11-09.md](P1_REPORT_2026-11-09.md) — P1 명령줄·입력 구현 보고.

  >   → **124 passed, 1 failed, 1 error, 2 skipped in 23.25s** (종료 코드 1).

- [P2_REPORT_2026-11-09.md](P2_REPORT_2026-11-09.md) — P2 단계 추출 전제 차단.

  > **136 passed, 3 failed, 1 error, 2 skipped in 20.11s**. 신규 시험 0.

- [P2B_REPORT_2026-11-10.md](P2B_REPORT_2026-11-10.md) — P2b 공유 단계·LangGraph.

  > 확인한 기준 시험을 다시 실행했다: 193 passed, 1 failed, 4 skipped(기존 memvid IO).


  > 전체 시험: **205 passed, 4 skipped in 26.51s**, 종료 코드 0.

- [P3_REPORT_2026-11-09.md](P3_REPORT_2026-11-09.md) — P3 프로필·규칙 검사기 보고.

  > - 시험: 요청한 전체 명령으로 **140 passed, 2 skipped in 27.24s**, 종료 코드 0.

- [X0_MEMVID_DIAGNOSIS_2026-11-10.md](X0_MEMVID_DIAGNOSIS_2026-11-10.md) — X0 memvid 쓰기 실패 진단.

  > 전체 시험: `235 passed, 1 failed, 5 skipped` (27.06s). 실패는 `tests/test_index_lifecycle.py::test_versions_rollback_and_prune`: memvid 쓰기 MemvidError를 RetrievalUnavailable로 감싼 기존 실패다. 재시험/수정하지 않았다. 진단 harness 새 시험은 통과했다. 보호 파일 18개 SHA-256은 기준과 모두 동일하다.

- [X0_MEMVID_DIAGNOSIS_FOLLOWUP_2026-11-10.md](X0_MEMVID_DIAGNOSIS_FOLLOWUP_2026-11-10.md) — X0 확장 진단 — 2026-11-10 KST.

  > 새 진단 harness 사전 시험은 fake SDK로 `3 passed`였다. 최종 전체 시험(필터 없음)은 `260 passed, 0 failed, 0 error, 1 skipped` (39.06s), `.runs/x0/followup-pytest.txt`다. 기존 memvid 시험이 이번 전체 시험에서는 실패하지 않았지만, 별도 SDK 진단에서 발생한 31건은 위에 그대로 기록했다. 재시험/skip/기대값 변경은 하지 않았다. 환경 변화로 선택 의존성 시험 수가 이전 단계와 달라졌다.


## 기준선·이전 보고서 M

- [M0_BASELINE_BLOCKER_2026-11-09.md](M0_BASELINE_BLOCKER_2026-11-09.md) — M0 착수 전 기준선 실패 — 개발 중단.

  > 결과: **1 failed, 51 passed, 2 warnings in 22.62s**. Windows Python 3.12 접근을 위해 승인된 sandbox 밖 실행을 사용했다. [실제 기준선 로그](evidence/M0/pytest_baseline.txt).

- [M0_DEBT_REPORT_2026-11-09.md](M0_DEBT_REPORT_2026-11-09.md) — R2 M0 경계 부채 재개 결과.

  > | 구조 시험 | 기존 구조 시험 8개와 새 import 호환성 시험 1개: **9 passed in 8.35s** |


  > | 전체 시험 | 실제 memvid 환경에서 **65 passed, 1 failed, 2 warnings in 25.66s**. R1의 64 passed보다 1개 많고 기존 tracing 실패 1개 유지 |


  > 최초 전체 실행은 **64 passed, 1 failed, 1 error, 2 warnings in 26.51s**였다. tests/test_memvid_store.py::test_versions_are_immutable의 fixture가 실제 SDK put_many 중 Tantivy IO 오류 / Windows 접근 거부(os error 5)를 냈다. 해당 시험은 코드·기대값 변경 없는 단독 재실행에서 **1 passed in 1.76s**, 동일 전체 명령의 재실행에서 위 최종 65 passed/1 failed가 됐다. 근본적인 IO 오류 원인은 확정하지 않았고 SDK 안정성 문제를 해결했다고 주장하지 않는다. 최초 오류 로그도 보존했다.


  > 요청한 `fix/tracing-fixture-loopback-pair`의 `6ddbcf6`을 별도로 checkout하여 tests/test_rag.py만 실행했다. 결과는 **15 passed in 0.64s**, 종료 코드 0이다.


  > # refactor/m0-debt 전체: 65 passed, 1 failed


  > # 별도 fix/tracing-fixture-loopback-pair / 6ddbcf6: 15 passed

- [M1_REAL_MEMVID_BASELINE_REPORT_2026-11-09.md](M1_REAL_MEMVID_BASELINE_REPORT_2026-11-09.md) — R1 실제 memvid 기준선.

  > | 시험 통과 | 전체 시험 **64 passed, 1 failed, 2 warnings in 25.44s**, 종료 코드 1. skip·기대값 변경 없음 |


  > 최초 실행은 실행용 LANGCHAIN_TRACING_V2=false가 시험의 tracing 활성화 대조군까지 억제해 **63 passed, 2 failed**였다. 코드·시험 변경 없이 tracing 환경 변수를 제거한 뒤 위 최종 기준선을 얻었다. [최초 실행 로그](evidence/M1/pytest_main_after_m0_initial_env.txt)도 보존했다. 최종 로그에는 fake endpoint 127.0.0.1:9에 대한 background client 접속 거절 경고가 있다. 실제 외부 서비스나 실제 키로 전송한 것이 아니며, 이를 네트워크 시도 0회라고 보고하지 않는다.

- [HANDOFF_CODEX_PROTOTYPE_2026-11-09.md](HANDOFF_CODEX_PROTOTYPE_2026-11-09.md) — Codex 인수인계: Equalizer 프로토타입 (2026-11-09 야간).

  > - 시험: 클라우드 86 passed (memvid-sdk 미설치로 8건 실패). Windows 실제 memvid 기준은 Codex가 확인.

- [RAG_REVIEW_FOLLOWUP_2026-11-10.md](RAG_REVIEW_FOLLOWUP_2026-11-10.md) — RAG 검수 후속: 기존 구현과 검색→생성 연결.

  > **234 passed, 1 failed, 5 skipped in 25.52s**, 종료 코드 1.


## 학습 실험

- [LEARNING_E4_2026-11-10.md](LEARNING_E4_2026-11-10.md) — E4 질의 지시문 효과.

  > 전체 시험 최종: `238 passed, 5 skipped` (26.99s). 첫 실행은 새 observe 모듈의 maturity 선언이 배치 규칙과 맞지 않아 `1 failed, 237 passed`였다. 선언을 기존 observe 모듈과 같은 incubating으로 맞췄다. 기존 시험은 변경하지 않았으며 실제 모델은 실행하지 않았다.

- [LEARNING_E5_2026-11-10.md](LEARNING_E5_2026-11-10.md) — E5 청크 크기 실험.

  > 전체 시험: `239 passed, 5 skipped` (26.99s). 추가 fake CLI 연결 실행은 `RetrievalUnavailable: chromadb is not installed: pip install -e .[chroma]`로 서재 생성 전에 중단됐다. 설치하거나 기존 시험을 바꾸지 않았다. 로그: `.runs/e5-smoke.txt`. 따라서 Chroma를 포함한 새 옵션의 실제 서재 통합 동작은 이번 환경에서 검증하지 못했다. 새 시험은 원문 quote 경계 손실, overlap으로 복원, 한도 초과 집계를 검증한다. 실제 모델 결과는 없다.

- [LEARNING_E6_2026-11-10.md](LEARNING_E6_2026-11-10.md) — E6 근거 없음 판정 경계.

  > 전체 시험: `240 passed, 1 failed, 5 skipped` (25.98s). 기존 `tests/test_index_lifecycle.py::test_versions_rollback_and_prune`가 memvid 쓰기 MemvidError → RetrievalUnavailable로 실패했다. 수정/재시도하지 않았다. 새 Wilson/격자/보고서 시험은 통과했다. confirm 점수를 바꿔도 선택 임계값이 같음을 확인했다. 실제 모델 결과는 없다.

- [LEARNING_E7_2026-11-10.md](LEARNING_E7_2026-11-10.md) — E7 키워드·벡터 결합 비교.

  > 전체 시험: `243 passed, 5 skipped` (27.69s). 실제 모델 결과는 없다. 출력 표의 기존 bootstrap 구간은 검색 지표 요약용이며, 판정 경계의 소표본 오수용/오거절 추론에는 E6 Wilson 보고서를 사용해야 한다.

- [LEARNING_E8_2026-11-10.md](LEARNING_E8_2026-11-10.md) — E8 작은 응용.

  > 첫 전체 시험: `247 passed, 5 skipped` (28.86s). fake CLI 실행은 `.runs/e8/fake-path/`에 보고서를 생성했다. 보호 18개 SHA-256 동일, 기존 시험/데이터/프로필/frozen masking 수정 없음. 최종 출력 형식 점검 후 전체 시험 결과를 추가한다.


  > 최종 전체 시험: `245 passed, 1 failed, 1 error, 5 skipped` (24.76s). 기존 `tests/test_index_lifecycle.py::test_versions_rollback_and_prune` 실패, `tests/test_memvid_store.py::test_versions_are_immutable`의 published fixture 오류다. 두 건 모두 `MemvidError: MV999: Tantivy error: tantivy index writer unavailable`이 `RetrievalUnavailable`로 전달됐다. 기존 시험·저장소 구현은 수정하거나 재시도하지 않았다. 로그: `.runs/e8-pytest-final.txt`.

- [LEARNING_SUMMARY_2026-11-10.md](LEARNING_SUMMARY_2026-11-10.md) — E4~E8 실제 모델 결과 종합 — 2026-11-10 KST.

  > 전체 시험(필터 없음): `247 passed, 0 failed, 0 error, 5 skipped` (27.25s), `.runs/chroma-inventory-summary-pytest.txt`. 이번 실행에서는 기존 memvid 시험도 실패하지 않았으며 간헐 실패가 해소됐다는 뜻은 아니다. 기존 시험/기대값/skip을 변경하지 않았다. 보호 파일 18개 SHA-256은 기준 스냅샷과 모두 동일하다. README 미커밋 변경은 보존하고 커밋에 포함하지 않는다.


## 운영·가이드·점검

- [ATTACH.ko.md](ATTACH.ko.md) — 다른 프로젝트에 붙이기.
- [PROTOTYPE_CLI.ko.md](PROTOTYPE_CLI.ko.md) — rra 명령줄 사용법.
- [MODELS.ko.md](MODELS.ko.md) — 로컬 임베딩 모델.
- [FEEDBACK_LOOP.ko.md](FEEDBACK_LOOP.ko.md) — 골든룰 피드백 루프 사용법 (v0).
- [GOLDEN_SET_MAKER.ko.md](GOLDEN_SET_MAKER.ko.md) — 골든셋 만들기.
- [LANGSMITH_EVAL.ko.md](LANGSMITH_EVAL.ko.md) — LangSmith 평가와 로컬 평가.
- [PREDICTION_LOG.ko.md](PREDICTION_LOG.ko.md) — 예측 기록장.
- [CHROMA_INTEGRATION_RECHECK_2026-11-10.md](CHROMA_INTEGRATION_RECHECK_2026-11-10.md) — Chroma 통합 경로 재확인 — 2026-11-10 KST.

  > 필터 없는 전체 시험을 한 번 실행했다. **257 passed, 2 failed, 1 error, 1 skipped (26.97s)**. JUnit 총 261개. 로그: `pytest.log`, `pytest.xml`, `pytest-summary.json`.


  > tracing 대조 시험 하나만 LANGCHAIN_TRACING_V2를 제거한 뒤 단독 실행: **1 passed (0.72s)** (`tracing-control.log`). 해당 기존 시험은 가짜 키/localhost:9를 사용하고 업로드 메서드와 외부 소켓을 차단한다. 이후 localhost:9 `/info` 접속 거부 로그가 있었으며 원격 LangSmith 업로드는 하지 않았다. 이 단독 결과로 위 전체 시험 결과를 덮어쓰지 않는다. memvid 실패·error는 재시험·skip·기대값 변경 없이 그대로 유지했다.

- [CHROMA_CLEANUP_FIX_2026-11-10.md](CHROMA_CLEANUP_FIX_2026-11-10.md) — Chroma 임시 서재 정리 실패 처리 — 2026-11-10 KST.

  > 새 시험: **6 passed (1.52s)**. 실제 Chroma 1.5.9 + fake 임베더, 기존 네트워크·모델 import 차단 wrapper로 6개 경로를 각각 10회 실행했다. 각 반복은 별도 CLI 프로세스/결과 디렉터리를 사용했다. 종료 코드 0뿐 아니라 보고서 JSON, fake/실모델 분리, compare 문항, 옵션, E3의 ID·metric 전달을 확인했다. E3는 같은 반복의 실제 E7-vector report.json을 이어서 입력했다. 아래 성공률은 **평가·내보내기 경로 성공률**이며 삭제 성공률이 아니다.


  > 전체 시험 한 번: **266 passed, 0 failed, 0 error, 1 skipped (31.95s)**. memvid 기존 시험도 이번 실행에서는 통과했으나 안정화의 증거는 아니다. 실패를 지우기 위한 재시험은 없었다. 기존 skip은 `tests/test_kiwi_lab.py::test_real_kiwi_particles_when_available`의 선택 Kiwi 의존성 미설치다. tracing 환경변수는 전체 시험 실행 명령에서 설정·삭제하지 않았다. 로그와 JUnit: `cleanup-fix/full-pytest.log`, `full-pytest.xml`.

- [MEMVID_DEPENDENCY_INVENTORY_2026-11-10.md](MEMVID_DEPENDENCY_INVENTORY_2026-11-10.md) — memvid 의존 조사 — 2026-11-10 KST.

  > 전체 시험(필터 없음): `247 passed, 0 failed, 0 error, 5 skipped` (27.25s). 로그 `.runs/chroma-inventory-summary-pytest.txt`. 이번 실행에서 memvid 실패가 없었다는 관찰이며 안정화 증거는 아니다. 보호 18개 기준 `C:/myLectureWs/rra-p1-stage/merged-protected-before.json`과 SHA-256 모두 동일하다. 신규 설치, legal-intake 수정, main 병합은 하지 않았다.


  > 후속 환경 관찰: 초기 import 감사의 chromadb 미설치 관찰은 그 시점의 스냅샷이다. X0 확장 진단 이후 전체 시험에서는 Chroma가 사용 가능해졌고 `260 passed, 0 failed, 0 error, 1 skipped`였다. 본 작업에서 설치 명령은 실행하지 않았다. 상세 환경 혼입 한계는 X0 후속 보고서에 기록한다. 기존의 생명주기 기능 부재는 그대로다.


  > 앞의 미설치/import 감사/247 passed 및 후속 260 passed 기록은 이전 실행 이력이다. 이번 재조사는 SDK를 새로 실행하지 않고 현재 소스·시험·스크립트·문서의 참조를 읽었다. 실제 Chroma 1.5.9 + fake 임베더 경로 재확인 결과는 CHROMA_INTEGRATION_RECHECK_2026-11-10.md를 따른다. SDK 안정성 개선·동등성 완전 입증은 미검증이다.


  > 이번 전체 시험: **257 passed, 2 failed, 1 error, 1 skipped** (26.97s). memvid MV999 쓰기 실패 1개 + setup error 1개와 실행 환경이 유발한 tracing 대조 실패 1개를 숨기지 않았다. tracing 단독 대조는 환경변수 충돌 제거 후 1 passed이며 전체 시험 수치를 대체하지 않는다. memvid 재시험 없음. 보호 18개 SHA-256 기준·작업 전후 모두 동일. 증거는 `.runs/chroma-recheck-20261110/pytest-summary.json`, `pytest.log`, `protected-sha256.json`.


## 결정 기록·보류

- [DECISION_STORE_CHROMA_2026-11-10.md](DECISION_STORE_CHROMA_2026-11-10.md) — 결정: 개발 기본 저장소를 Chroma로 고정, memvid는 개발 경로에서 제외.
- [FUTURE_MEMVID_BUFFER_SPIKE_2026-11-10.md](FUTURE_MEMVID_BUFFER_SPIKE_2026-11-10.md) — 보류 과제: memvid 안정화 버퍼 spike (11월 말, 본 개발 시작 전).

## 운영: 이전 및 이번 작업

- [MIGRATION_CHECKLIST.md](MIGRATION_CHECKLIST.md) — Git 포함 범위, uv 환경·모델 리비전 재준비와 PC/WSL 이전 점검.
- [N10_REPORT_2026-11-10.md](N10_REPORT_2026-11-10.md) — 문서 색인·이전 체크리스트 작성 범위, 시험 시작 결과 및 미검증 항목.

## 학습·설계 부록과 증거

- [study/equalizer-study.html](study/equalizer-study.html) — Equalizer 학습용 HTML 자료.
- [EQUALIZER_STUDY_DARK.pdf](EQUALIZER_STUDY_DARK.pdf) — 어두운 테마 학습 PDF.
- [diagrams/README.md](diagrams/README.md) — 구조·흐름·노브·검색·저장소·활용 다이어그램의 한영 목록과 재렌더 명령. 같은 폴더의 `.mmd`는 원본, `.png`는 렌더 결과이며 `mermaid-config.json`·`puppeteer.json`은 렌더 설정이다.
- [evidence/README.md](evidence/README.md), [한국어](evidence/README.ko.md), [English](evidence/README.en.md) — 아키텍처 주장별 증거 계획과 NOT_RUN 상태.
- [evidence/golden/README.md](evidence/golden/README.md) — 합성 골든셋의 fake 임베더 두 축 경로 시험 설명. [JSON](evidence/golden/fake_two_axis.json), [pytest 로그](evidence/golden/pytest.txt)를 연결한다.
- M0 시험 증거: [기준선](evidence/M0/pytest_baseline.txt), [부채 정리](evidence/M0/pytest_debt_after_2026-11-09.txt), [최초 IO 오류](evidence/M0/pytest_debt_after_2026-11-09_initial_io_error.txt), [Windows tracing](evidence/M0/pytest_tracing_fixture_windows_2026-11-09.txt).
- M1 시험 증거: [기준선](evidence/M1/pytest_main_after_m0.txt), [최초 환경](evidence/M1/pytest_main_after_m0_initial_env.txt).

현재 존재하는 문서만 열거한다. 단계 번호의 빈자리에 결과를 보충하지 않는다. N5/N8/N9의 시험 미실행 사유와 이번 N10 결과는 각 보고서에서 확인한다.
