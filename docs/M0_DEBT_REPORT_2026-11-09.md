# R2 M0 경계 부채 — 기존 시험 기대값 변경 필요로 중단

2026-11-09 KST. R1 브랜치의 기록 커밋 `ac7965b`에서 `refactor/m0-debt`를 만들었다. 소스 기준은 최신 main `9a17b17`과 동일하다. R1은 코드 변경 없이 증거·보고서만 추가했다.

## 구현·연결·시험

| 구분 | 결과 |
|---|---|
| 구현 | 시작 전 정적 검토에서 멈춤 조건 확인. 소스·기존 시험 변경 없음 |
| 연결 | ingest/guard 및 store/retrieve 기존 연결 유지. 주입·이동 미완료 |
| 구조 시험 | 변경 없이 `tests/test_structure.py`: **8 passed in 8.56s**. KNOWN_DEBT 2개를 허용하는 현재 기준의 통과이며 부채 해소를 뜻하지 않음 |
| 전체 시험 | R1의 동일한 코드 기준선 **64 passed, 1 failed, 2 warnings**. R2에서 전체 시험을 다시 실행했다고 주장하지 않음 |
| 완료 기준 | 미충족. KNOWN_DEBT 항목은 삭제하지 않았고, 2건 모두 남아 있음 |

## 중단 근거

요청은 동작 변경 없는 이동·주입이며, 이동 때문에 기존 시험 기대값을 바꿔야 하면 중단하도록 했다. 구조 시험의 KNOWN_DEBT 삭제는 명시적으로 허용됐지만, 다른 기존 기대값 변경은 허용되지 않았다.

1. `retrieve/keyword.py`의 기존 lex_terms는 `import re`와 `re.sub(r"[^\\w가-힣]", "", raw)`를 사용한다. 이 구현을 core로 그대로 이동하면 core 파일도 re를 import해야 한다.
2. 기존 `tests/test_structure.py::test_core_has_no_third_party_imports`의 허용 집합은 `__future__`, `dataclasses`, `enum`, `hashlib`, `typing`뿐이다. stdlib인 re도 이 기존 집합에는 없어, 그대로 이동하면 해당 시험이 실패한다.
3. re를 허용하도록 집합을 수정하는 것은 KNOWN_DEBT 삭제와 별개의 기존 시험 기대값 변경이다. 규칙을 다른 문자 필터로 다시 작성하는 것도 요청한 단순 이동 범위를 벗어난다. 따라서 실제 파일 이동·기대값 수정 전에 중단했다. 예상되는 assertion의 근거를 소스로 확인했으며, 실패를 만들기 위해 코드를 임시로 옮기지는 않았다.

첫 번째 Masker 주입도 전체 변경의 일부이므로 반쪽 구현을 남기지 않았다. 현재 Masker protocol은 guard/protocols.py에 있고, 기존 build_chunks는 guard/masking.py의 mask_pii와 MASKING_VERSION을 직접 사용한다. ingest가 protocol을 다시 guard에서 import하거나, 의존을 dynamic import로 숨기거나, 마스킹 규칙을 복사하여 KNOWN_DEBT만 비우는 방법은 적용하지 않았다. 기존 호출의 기본 동작을 보존하는 공용 protocol/default adapter 경계는 후속 설계에서 정해야 한다.

## 보존 확인

- frozen `src/rag_research_agent/guard/masking.py` 미수정. Git blob hash: `7fd84b5bf7cd2afd88b78176303d9bc583580086`.
- 소스·tests·pyproject.toml의 main 대비 diff 없음. 기존 미추적 uv.lock도 보존.
- 기존 Windows 실패는 `test_serving_guard_blocks_tracing_even_when_env_enables_it`: 전역 socket.connect 차단이 asyncio ProactorEventLoop의 내부 loopback 생성까지 막는 `OSError: blocked`. 고치거나 skip하지 않음.
- `.env` 접근, 실제 외부 공급자 호출, main 병합 없음.

## 재개에 필요한 결정

- core가 모든 stdlib 모듈을 쓸 수 있도록 기존 구조 시험의 좁은 허용 집합을 보완하는 것을 이번 작업의 명시적 예외로 허용할지 결정해야 한다. 해당 허용이 있으면 lex_terms의 re 기반 구현을 그대로 이동할 수 있다.
- frozen masking.py를 유지하면서 기존 기본값과 모듈 제거 가능성을 함께 보존할 Masker protocol 및 기본 구현의 공용 경계를 정해야 한다. 규칙 복사나 숨겨진 모듈 의존으로 우회하지 않는다.

R2 완료 또는 경계 위반 해소로 표시하지 않는다.
