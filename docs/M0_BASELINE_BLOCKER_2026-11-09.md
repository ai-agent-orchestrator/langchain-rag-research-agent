# M0 착수 전 기준선 실패 — 개발 중단

2026-11-09 KST · 브랜치 `feat/m0-skeleton` · 기준 HEAD `e0cd68955001aabd13ea288f84b47bd82306350d`.

M0 완료 아님. 사용자의 “시험이 막히면 시험을 고치지 말고 원인만 기록하고 멈춘다” 지시에 따라 **변경 전 전체 시험의 실패 원인만 기록하고 개발을 중단**했다. 시험 기대값·skip·기본 이벤트 루프·네트워크 차단 코드를 수정하거나 재실행하지 않았다.

## 준비와 결과

저장소를 로컬 `C:\myLectureWs\python-memvid-guardrail`에 클론하고 지정 브랜치를 만들었다. 이어진 대표 지시로 `origin`의 fetch/push URL만 `https://github.com/ai-agent-orchestrator/langchain-rag-research-agent.git`로 변경했다. 로컬 폴더명은 그대로다.

Python 3.12.10, 별도 `.venv`에 `uv sync --extra all --python 3.12`로 기존 선택 의존성을 설치했다. 주요 버전: pytest 9.2.0, memvid-sdk 2.0.160, langchain-core 1.7.6, langgraph 1.2.20, langsmith 0.14.17, pydantic 2.14.3. 실제 E5/Llama/Qwen 모델이나 OpenAI 유료 API는 호출하지 않았다. 환경 준비 중 생성된 `uv.lock`은 미커밋으로 남긴다.

```powershell
$env:HF_HUB_OFFLINE='1'
$env:MEMVID_TELEMETRY='0'
$env:LANGSMITH_TRACING='false'
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

결과: **1 failed, 51 passed, 2 warnings in 22.62s**. Windows Python 3.12 접근을 위해 승인된 sandbox 밖 실행을 사용했다. [실제 기준선 로그](evidence/M0/pytest_baseline.txt).

## 확인한 실패 원인

실패 시험: `tests/test_rag.py::test_serving_guard_blocks_tracing_even_when_env_enables_it`.

시험은 `armed_tracing` fixture로 `socket.socket.connect`를 전역 차단한다. 그런데 Windows의 `asyncio.run()`이 Proactor 이벤트 루프를 만들 때 `socket.socketpair()`의 fallback으로 내부 `127.0.0.1:<임시 포트>` 연결을 사용한다. 이 내부 연결도 fixture의 `refuse()`가 막아 `OSError("blocked")`가 발생했다.

호출 순서: `asyncio.run → new_event_loop → ProactorEventLoop → _make_self_pipe → socket.socketpair → _fallback_socketpair → csock.connect → tests/test_rag.py:172 refuse`.

**그래프 coroutine 실행 전 이벤트 루프 초기화 단계에서 실패**했다. 이를 실제 LangSmith 외부 전송 발생이나 serving guard 통과로 해석할 수 없다. 부수 경고는 실행되지 못한 `Pregel.ainvoke` coroutine과 초기화되지 못한 이벤트 루프 정리 경고다. fixture의 대조군은 로컬 `127.0.0.1:9`를 사용하며 종료 시 접속 거부 경고도 출력됐다. 실제 원격 trace 업로드의 성공 증거는 없다.

## 구현·연결·시험 상태

| 항목 | 구현 | 연결 | 시험 |
|---|---|---|---|
| 새 원격 URL | 설정 완료 | fetch/push 모두 새 URL | `git remote -v` 확인 |
| 패키지/import 이름 변경 | 미시작 | 미시작 | 미실행 |
| core/guard/ontology/edge/knobs/diet/compose 골격 | 미시작 | 미시작 | 미실행 |
| P0-1~7 구조 시험 | 미작성 | 해당 없음 | 기존 약한 구조 시험만 기존 회귀에 포함 |
| 기존 전체 회귀 | 기존 코드 유지 | 기존 코드 유지 | 51 통과, 1 실패 |

읽기 점검에서 기존 `ingest/chunking.py → guard/masking.py`, `store/memvid_store.py → retrieve/keyword.py`의 직접 import도 확인했다. P0 경계 조정이 필요한 기존 구조이지만 이번에 수정하지 않았다. 단순 이름 변경이나 골격 추가만으로 P0 충족을 주장할 수 없다.

`src/`, `tests/`, `scripts/`, `pyproject.toml`은 기준 HEAD에서 변경 0개다. legal-intake RAG 코드·시험 이전/수정/삭제, Equalizer 점수·Diet 구현, 외부 모델 호출, main 병합은 하지 않았다. 다음 작업은 이 실패의 처리 방침을 별도로 정한 뒤 재개한다.
