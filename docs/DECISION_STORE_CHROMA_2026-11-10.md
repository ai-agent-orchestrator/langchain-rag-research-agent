# 결정: 개발 기본 저장소를 Chroma로 고정, memvid는 개발 경로에서 제외

날짜: 2026-11-10 KST · 결정자: 대표 · 상태: 채택(재검토 조건 있음)

## 결정
- 모든 신규 개발·실험·평가(E4~E8 포함)는 Chroma 서재 기준으로 한다.
- memvid는 개발 기본 경로에서 쓰지 않는다. 기존 코드와 시험은 삭제하지 않고
  "알려진 불안정" 상태로 보존한다.
- 11월 말 본 개발 시작 전에 memvid 안정화 가능성을 별도 spike로 시험할 수 있다
  (docs/FUTURE_MEMVID_BUFFER_SPIKE_2026-11-10.md). 시험 결과와 무관하게
  개발 기본값은 대표가 다시 결정하기 전까지 Chroma다.

## 이유 (관찰 사실만)
- 같은 코드가 실행마다 통과/실패가 갈린다. 실패한 시험이 실행마다 달랐다:
  test_versions_rollback_and_prune, test_activate_refuses_tampered_or_mismatched_versions,
  test_tampered_file_and_wrong_embedder_are_refused, test_versions_are_immutable,
  test_gate_statuses (setup).
- 증상: MemvidError MV999, Tantivy IO 오류 "액세스가 거부되었습니다 (os error 5)",
  또는 "index writer unavailable".
- X0 진단(docs/X0_MEMVID_DIAGNOSIS_2026-11-10.md): 동일 조건 3회 중 1~3회 성공.
  한글 경로만의 문제는 배제. 네이티브 Tantivy 쓰기 계층으로 범위가 좁혀졌으나
  직접 원인(SDK 내부 핸들, 보안 프로그램, Windows 파일 교체 의미)은 미확정.
- 기존 retry는 같은 writer에 재호출하므로 복구 수단이 아니다.
- 환경: Windows 11 build 26200, Python 3.12.10, memvid-sdk 2.0.160.

## 이 결정이 주장하지 않는 것
- memvid 자체가 결함이라는 결론이 아니다. 이 환경·버전·소표본의 관찰이다.
- Linux나 다른 SDK 버전에서의 동작은 검증하지 않았다.
- legal-intake 쪽 memvid 사용(B02a/B02b)에 대한 결정이 아니다. 그 범위는 별도 결정.

## 영향
- 버전 발행/무결성 manifest 기능이 memvid에 묶여 있다면 Chroma 경로에서 같은 계약을
  제공하는지 확인이 필요하다 (조사 항목, 아직 미조사).
- 전체 시험의 간헐 실패(memvid)는 개발 판단의 신호로 쓰지 않되, 숨기지 않고 기록한다.

## 재검토 조건
- 다른 OS/SDK 버전에서 X0 진단이 30회 이상 안정 통과하거나,
- 원인이 환경 요인(예: 보안 프로그램 제외로 해소)으로 확정되거나,
- 버퍼 spike가 합격선을 넘으면 재검토한다.
