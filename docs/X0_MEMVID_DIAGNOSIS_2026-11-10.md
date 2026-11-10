# X0 memvid 쓰기 실패 진단

수정 없이 SDK 직접 호출로 재현했다. 기존 시험, memvid_store/retry, 데이터, 프로필은 변경하지 않았다.

환경: Windows 11 build 26200, Python 3.12.10 x64, memvid-sdk 2.0.160.
실행: `.\.venv\Scripts\python.exe scripts/diagnose_memvid_writes.py --trials 3`
원본 결과: `.runs/x0/95f2a394243547129c5a0f4da9e5edf1/diagnosis.json` (로컬 전용).

| 합성 벡터 경로 시험 조건 | 성공 | 실패 |
| --- | --- | --- |
| ASCII, lex on, batch 8 | 3 | 0 |
| 한글, lex on, batch 8 | 3 | 0 |
| ASCII, lex off, batch 8 | 1 | 2 |
| ASCII, lex on, batch 1 | 3 | 0 |

두 실패 모두 첫 `put:0`에서 `MemvidError: MV999: Tantivy error: An IO error occurred: 액세스가 거부되었습니다. (os error 5)`였다. 명시적 동시 reader 없이 새 파일에서도 발생했다. lex off도 Tantivy를 경유한다. 3회씩의 작은 표본이므로 옵션 효과나 성공 보장을 주장하지 않는다. 모델은 사용하지 않았다.

잠금 대조군: 읽기 핸들이 열린 합성 파일을 os.replace하면 PermissionError WinError 5가 발생했다. 증상은 같은 접근 거부 계열이지만 SDK 내부 핸들, 외부 보안 프로그램, Windows 파일 교체 의미 중 어느 것이 직접 원인인지는 미확정이다. SDK의 네이티브 Tantivy 쓰기 계층으로 범위는 좁혀졌고, 한글 경로만의 문제는 배제했다. OS/SDK 버전의 인과관계는 Linux 및 다른 SDK 버전 대조 실행 전에는 판정할 수 없다. 별도 설치나 설정 변경은 하지 않았다.

기존 retry_io는 같은 writer에 재호출한다. 따라서 과거 마지막 예외 `tantivy index writer unavailable`만으로 최초 원인을 판정하면 안 된다. 새 스크립트는 재시도하지 않고 최초 오류와 close 오류를 구분한다. 생산 코드의 재시도 정책은 변경하지 않았다.

memvid 버전 발행과 해당 시험을 막을 수 있으나, 기본 연구 Library는 Chroma이며 키워드 검색도 그 경로를 사용한다. E7 전체가 memvid 때문에 막힌다는 가설은 현재 근거로 입증되지 않는다.

후속 진단은 동일 스크립트를 별도 OS/SDK 환경에서 실행하고 native IO trace에서 실패 파일과 핸들을 확인하는 것이다. 본 단계에서는 수정하지 않는다.

전체 시험: `235 passed, 1 failed, 5 skipped` (27.06s). 실패는 `tests/test_index_lifecycle.py::test_versions_rollback_and_prune`: memvid 쓰기 MemvidError를 RetrievalUnavailable로 감싼 기존 실패다. 재시험/수정하지 않았다. 진단 harness 새 시험은 통과했다. 보호 파일 18개 SHA-256은 기준과 모두 동일하다.
