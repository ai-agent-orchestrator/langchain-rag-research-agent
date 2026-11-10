files: packages/intake_guard/pyproject.toml, packages/intake_guard/src/intake_guard/__init__.py, packages/intake_guard/src/intake_guard/policy_core.py, packages/intake_guard/src/intake_guard/marketing_core.py, packages/intake_guard/tests/test_intake_guard.py, packages/intake_guard/README.md, app/security/policy_core.py, app/security/marketing_core.py, docs/GUARD_PACKAGE_2026-11-10.md
forbid: app/rag/**, rag-runtime/**, tests/rag/**, tests/test_rag_b03_b05.py, docs/evidence/**, app/routers/**, app/main.py, .env*
effort: high
coder: codex

# C15: legal-intake 보안 코어를 설치 가능한 패키지로 분리 — 결정 D3·D11 (저장소: legal-intake-fastapi-lab)

**이 명세는 리서치 저장소가 아니라 `legal-intake-fastapi-lab`에서 실행한다.** 대표 PC의 기존 폴더에는 RAG 미커밋 변경이 있으므로 **새 클론**(`C:\work\legal-intake-guard`)에서 작업한다.

## 목표
표준 라이브러리만 쓰는 `app/security/policy_core.py`(입력 정책·마스킹·출력 정책)와 `marketing_core.py`를 `packages/intake_guard/` 하위 패키지로 옮겨, 리서치 저장소가 `pip install`로 의존할 수 있게 한다. **legal-intake의 동작은 그대로.**

## 내용
- `packages/intake_guard/`: `pyproject.toml`(이름 `intake-guard`, 의존성 없음, Python ≥3.12), `src/intake_guard/`에 두 코어를 **그대로 이동**(로직 변경 금지), `__init__`에서 `check_input_policy`, `mask_personal_data`, `check_output_policy`, `check_marketing_response`(있다면 코어 함수명 그대로), `TextDecision`, `MASKING_VERSION` 등을 공개.
- `app/security/policy_core.py`·`marketing_core.py`는 패키지에서 다시 내보내는 얇은 호환 파일로 바꾼다(기존 import 경로 유지). legal-intake 실행 환경에서 패키지를 찾도록 `sys.path` 조작 대신 **editable 설치 안내**와, 설치 안 된 경우를 위한 상대 경로 폴백(`packages/intake_guard/src`)을 한 곳에만 둔다.
- 패키지 자체 시험: 기존 보안 시험에서 코어 단위 시험을 복사하지 말고, 패키지 공개 함수의 대표 사례(차단·허용·마스킹·멱등·단독 import)를 새로 작성.
- `docs/GUARD_PACKAGE_2026-11-10.md`: 설치 방법(`pip install -e packages/intake_guard`, git URL 설치 `pip install "intake-guard @ git+https://github.com/ai-agent-orchestrator/legal-intake-fastapi-lab#subdirectory=packages/intake_guard"`), 버전 규칙(`MASKING_VERSION` 변경 시 패키지 버전도 올림).

## 완료 기준
기존 보안 시험 파일 전부 기대값 수정 없이 통과(지정 범위, 개수 기록), 패키지 시험 통과, `python -c "import intake_guard"`가 legal-intake 밖에서도 동작. 저장소 전체 통과로 표시하지 않는다.

## 공통 규칙
- 레인 브랜치에서 이전 명세 결과 위에 이어서 작업. 맥락: `docs/EQUALIZER_V0.ko.md`, `docs/DESIGN.ko.md` (결정 D8~D11).
- 데이터 내용 수정 금지: `data/golden_rules/**`, `profiles/*.json`, `data/equalizer/**`, `data/golden_sets/**`.
- `tests/test_structure.py` 통과 유지. `KNOWN_DEBT` 증가 금지. 무거운 라이브러리 import는 어댑터 파일 안에서만.
- 기존 시험 기대값 수정·skip·삭제 금지. 시험에서 네트워크·모델 다운로드 금지. LLM·`.env` 금지. push 금지.
- **끝나면 반드시 `git add` + `git commit`.** 막히면 원인만 보고서에 적고 그 보고서를 커밋한 뒤 멈춘다.
- 보고서: 구현·시험 통과 구분, 전체 시험 `n passed`, 대표가 직접 실행해야 하는 단계(모델 다운로드 등)를 명령과 함께 목록으로.
