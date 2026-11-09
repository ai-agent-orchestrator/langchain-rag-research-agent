# R1 실제 memvid 기준선

2026-11-09 KST. 원격 main을 fetch하여 확인한 `9a17b17`에서 `chore/baseline-real-memvid`를 만들었다. 기존 미추적 uv.lock은 수정·커밋하지 않는다.

| 구분 | 결과 |
|---|---|
| 구현 | 코드 변경 없음. 증거·보고서만 추가 |
| 연결 | 기존 로컬 Python 3.12.10과 실제 memvid-sdk 2.0.160 사용. fake 임베더·fake chat model·합성 자료로 기존 시험 실행 |
| 시험 통과 | 전체 시험 **64 passed, 1 failed, 2 warnings in 25.44s**, 종료 코드 1. skip·기대값 변경 없음 |

환경: pytest 9.2.0, langchain-core 1.7.6, langgraph 1.2.20, langsmith 0.14.17. 실제 memvid 색인의 쓰기·seal·재열기·벡터 자기 검색·롤백을 실행했다. 실제 E5 또는 공급자 생성 품질을 검증한 것은 아니다.

## 핵심 질문: SDK 부재 8건

아래 8개가 실제 SDK로 모두 통과했다. cloud의 상세 실패 로그는 이 작업에 제공되지 않았으므로, 8건의 node ID가 cloud 로그와 정확히 일치하는지는 독립적으로 대조하지 못했다. 아래는 SDK가 필요한 로컬 통과 사례이다.

- tests/test_memvid_store.py::test_telemetry_is_forced_off
- tests/test_memvid_store.py::test_publish_verifies_every_chunk_and_activates_pointer
- tests/test_memvid_store.py::test_many_chunks_survive_batched_writes
- tests/test_memvid_store.py::test_versions_are_immutable
- tests/test_memvid_store.py::test_tampered_file_and_wrong_embedder_are_refused
- tests/test_memvid_store.py::test_gate_statuses
- tests/test_index_lifecycle.py::test_versions_rollback_and_prune
- tests/test_index_lifecycle.py::test_activate_refuses_tampered_or_mismatched_versions

## 기존 Windows 실패

tests/test_rag.py::test_serving_guard_blocks_tracing_even_when_env_enables_it가 실패한다. armed_tracing fixture가 socket.connect를 전역 거절한 상태에서 Windows asyncio ProactorEventLoop가 내부 socketpair/loopback을 생성하다 OSError: blocked를 받는다. LangGraph의 ainvoke 본문 전에 실패하며, 후속 미await coroutine 및 불완전 loop 정리 경고 2개가 나온다. 처리 방침 미정이므로 수정하지 않았다.

증거: [최종 전체 시험 로그](evidence/M1/pytest_main_after_m0.txt).

최초 실행은 실행용 LANGCHAIN_TRACING_V2=false가 시험의 tracing 활성화 대조군까지 억제해 **63 passed, 2 failed**였다. 코드·시험 변경 없이 tracing 환경 변수를 제거한 뒤 위 최종 기준선을 얻었다. [최초 실행 로그](evidence/M1/pytest_main_after_m0_initial_env.txt)도 보존했다. 최종 로그에는 fake endpoint 127.0.0.1:9에 대한 background client 접속 거절 경고가 있다. 실제 외부 서비스나 실제 키로 전송한 것이 아니며, 이를 네트워크 시도 0회라고 보고하지 않는다.

## 재현

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:MEMVID_TELEMETRY='0'
$env:HF_HUB_OFFLINE='1'
$env:TRANSFORMERS_OFFLINE='1'
foreach ($taskKey in @('OPENAI_API_KEY','LANGSMITH_API_KEY','LANGCHAIN_API_KEY','LANGSMITH_TRACING','LANGCHAIN_TRACING_V2')) {
  Remove-Item -LiteralPath "Env:$taskKey" -ErrorAction SilentlyContinue
}
.\.venv\Scripts\python.exe -m pytest -q -rA --tb=short -p no:cacheprovider
```

실행 대상 Python 3.12가 sandbox 밖에 있어 승인된 권한으로 실행했다. `.env` 접근, 모델 다운로드, 실제 외부 공급자 호출, main 병합은 하지 않았다. 전체 통과로 보고하지 않는다.
