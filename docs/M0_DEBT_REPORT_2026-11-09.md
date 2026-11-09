# R2 M0 경계 부채 재개 결과

2026-11-09 KST. fetch로 확인한 최신 main은 `9a17b17`이다. `refactor/m0-debt`는 해당 main을 조상으로 포함하며 착수 전 src/tests/pyproject.toml이 최신 main과 동일한 것을 확인했다. 앞선 커밋들은 R1 증거와 중단 보고서만 담고 있었다. main 또는 tracing 수정 브랜치를 병합하지 않았다.

## 승인 범위와 보류

대표가 A안을 승인하여 기존 구조 시험의 core 허용 집합에 stdlib `re` 하나를 추가했다. 그 외 허용 모듈·assertion·skip·기존 기대값은 바꾸지 않았다.

추가 확인에 대한 대표 답변은 **"frozen 유지, 해당 변경 보류"**다. 따라서 Masker 주입 및 ingest→guard 의존 제거는 보류했고, 해당 KNOWN_DEBT를 남겼다. store→retrieve 항목만 실제 의존을 제거한 뒤 삭제했다. 두 부채가 모두 해소됐다고 표시하지 않는다.

## 구현·연결·시험

| 구분 | 결과 |
|---|---|
| 구현 | lex_terms와 기존 caseType 상수를 core/lexical.py로 이동. 표준 라이브러리 re만 사용 |
| 연결 | store/memvid_store.py는 core.lexical에서 직접 import. retrieve.keyword는 같은 함수 객체를 다시 내보내 기존 공개 import 경로 보존 |
| 동작 보존 | 이동한 함수 및 caseType 상수의 AST가 최신 main의 기존 구현과 완전히 동일함을 확인 |
| 구조 시험 | 기존 구조 시험 8개와 새 import 호환성 시험 1개: **9 passed in 8.35s** |
| 전체 시험 | 실제 memvid 환경에서 **65 passed, 1 failed, 2 warnings in 25.66s**. R1의 64 passed보다 1개 많고 기존 tracing 실패 1개 유지 |
| KNOWN_DEBT | 기존 2개 → 1개. 남은 항목은 대표가 보류한 ingest→guard |
| Masker | 주입 미구현. 기존 기본 마스킹 동작과 frozen 파일을 그대로 유지 |

새 tests/test_lexical_compatibility.py는 기존 retrieve.keyword의 함수와 저장소가 사용하는 함수가 core의 동일한 객체인지 확인한다. 통과 개수를 늘리기 위한 규칙 사례 복제는 하지 않았다. 기존 lex 쿼리 동작과 실제 SDK 검색·색인·롤백은 기존 시험을 그대로 실행했다.

## 전체 시험의 실패·재실행

기존 실패는 tests/test_rag.py::test_serving_guard_blocks_tracing_even_when_env_enables_it이며 Windows asyncio ProactorEventLoop의 내부 socketpair 생성이 fixture의 전역 connect 차단에 걸리는 **OSError: blocked**다. R1과 같은 시험·실패 원인이다. 이번 브랜치의 tests/test_rag.py는 수정하지 않았다.

최초 전체 실행은 **64 passed, 1 failed, 1 error, 2 warnings in 26.51s**였다. tests/test_memvid_store.py::test_versions_are_immutable의 fixture가 실제 SDK put_many 중 Tantivy IO 오류 / Windows 접근 거부(os error 5)를 냈다. 해당 시험은 코드·기대값 변경 없는 단독 재실행에서 **1 passed in 1.76s**, 동일 전체 명령의 재실행에서 위 최종 65 passed/1 failed가 됐다. 근본적인 IO 오류 원인은 확정하지 않았고 SDK 안정성 문제를 해결했다고 주장하지 않는다. 최초 오류 로그도 보존했다.

- [최종 전체 시험](evidence/M0/pytest_debt_after_2026-11-09.txt)
- [최초 IO 오류 포함 실행](evidence/M0/pytest_debt_after_2026-11-09_initial_io_error.txt)
- R1 비교 기록: docs/evidence/M1/pytest_main_after_m0.txt

두 경고는 기존 실패 이후 미await coroutine 및 불완전 loop 정리에서 나온다. 전체 시험 통과로 보고하지 않는다.

## 별도 tracing 브랜치 Windows 검증

요청한 `fix/tracing-fixture-loopback-pair`의 `6ddbcf6`을 별도로 checkout하여 tests/test_rag.py만 실행했다. 결과는 **15 passed in 0.64s**, 종료 코드 0이다.

- 이전 실패 시험 test_serving_guard_blocks_tracing_even_when_env_enables_it: **통과로 변경**.
- 새 test_fixture_allows_internal_loopback_pair_but_blocks_uploads: **통과**.
- tracing 활성화 대조군 test_control_environment_alone_would_trace: **통과**.

해당 브랜치에서 코드를 수정하거나 커밋하지 않았다. 검증 후 refactor/m0-debt로 돌아왔으며 tracing 패치를 가져오지 않았다. 따라서 R2 전체 시험의 기존 실패 유지와 별도 tracing 브랜치 15개 통과는 서로 다른 코드 기준의 결과다.

[Windows tracing 시험 로그](evidence/M0/pytest_tracing_fixture_windows_2026-11-09.txt)

시험 종료 후 fake endpoint 127.0.0.1:9에 대한 LangSmith background 접속 거절 경고가 기록됐다. 실제 키·외부 서비스 전송은 없었으며 네트워크 시도 0회라고 보고하지 않는다. 이 검증은 해당 파일 15개만 대상으로 했고 tracing 브랜치 전체 시험 통과를 뜻하지 않는다.

## 재현

실제 SDK가 있는 기존 Python 3.12.10 환경(memvid-sdk 2.0.160, pytest 9.2.0, langchain-core 1.7.6, langgraph 1.2.20, langsmith 0.14.17)을 사용했다. 승인된 권한에서 실행했으며 모델 다운로드나 패키지 설치는 하지 않았다.

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:MEMVID_TELEMETRY='0'
$env:HF_HUB_OFFLINE='1'
$env:TRANSFORMERS_OFFLINE='1'
foreach ($taskKey in @('OPENAI_API_KEY','MEMVID_API_KEY','LANGSMITH_API_KEY','LANGCHAIN_API_KEY','LANGSMITH_TRACING','LANGCHAIN_TRACING_V2')) {
  Remove-Item -LiteralPath "Env:$taskKey" -ErrorAction SilentlyContinue
}
# refactor/m0-debt: 구조 8개 + import 호환성 1개
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_structure.py tests/test_lexical_compatibility.py
# refactor/m0-debt 전체: 65 passed, 1 failed
.\.venv\Scripts\python.exe -m pytest -q -rA --tb=short -p no:cacheprovider
# 별도 fix/tracing-fixture-loopback-pair / 6ddbcf6: 15 passed
.\.venv\Scripts\python.exe -m pytest -q -rA --tb=short -p no:cacheprovider tests/test_rag.py
```

마지막 명령은 해당 tracing 브랜치를 checkout한 상태에서만 재현한다. 집계는 서로 겹치며 합산하지 않는다.

## 보존·한계

다음 파일은 내용 해시가 착수 전후 같다.

- guard/masking.py: `7fd84b5bf7cd2afd88b78176303d9bc583580086`
- ingest/chunking.py: `813fc2b7c9161a9677215bfd3a5731d93ffb471d`
- guard/protocols.py: `fc4e08c00e39819d19eb6f1e1ee6e1779102be4d`

기존 tests/test_rag.py 및 그 밖의 기존 시험은 수정하지 않았고, tests/test_structure.py의 diff는 re 추가와 해소한 store→retrieve 항목 삭제뿐이다. 기존 미추적 uv.lock은 그대로 두고 커밋하지 않는다. 합성 데이터·fake 모델과 실제 로컬 memvid만 사용했다. `.env` 접근, 실제 외부 공급자 호출, main 병합은 하지 않았다.

승인 범위의 lex_terms 이동은 완료했고, Masker 주입과 두 번째 부채 해소는 대표 결정으로 보류 상태다. frozen 예외를 임의 적용하거나 규칙 복사·동적 import로 의존을 숨기지 않았다.
