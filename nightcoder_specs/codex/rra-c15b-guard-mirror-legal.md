files: packages/intake_guard/pyproject.toml, packages/intake_guard/README.md, packages/intake_guard/src/intake_guard/__init__.py, packages/intake_guard/src/intake_guard/policy_core.py, packages/intake_guard/src/intake_guard/marketing_core.py, packages/intake_guard/tests/test_intake_guard.py, tests/test_intake_guard_mirror.py, scripts/sync_intake_guard.py, docs/GUARD_PACKAGE_2026-11-10.md
forbid: app/**, rag-runtime/**, tests/rag/**, tests/test_rag_b03_b05.py, tests/test_policy_core_structure.py, docs/evidence/**, .env*
effort: medium
coder: codex

# C15b: 보안 코어 패키지 = 검증된 미러 (저장소: legal-intake-fastapi-lab) — C15 차단 해제

**legal-intake 새 클론**(`C:\work\legal-intake-guard`, 브랜치 `feat/intake-guard-package`)에서 진행. 기존 C15 보고서(`docs/GUARD_PACKAGE_2026-11-10.md`)를 갱신한다.

## 결정 (Claude, 2026-11-10)
C15는 기존 시험 `tests/test_policy_core_structure.py`(코어 파일 단독 실행)와 "재내보내기" 방식이 충돌해 막혔다. 그래서:
- **정본은 `app/security/policy_core.py`·`marketing_core.py` 그대로**(수정 금지, 기존 시험 그대로 통과).
- 패키지 `packages/intake_guard/src/intake_guard/`의 두 파일은 **정본과 바이트까지 동일한 미러**. `scripts/sync_intake_guard.py`가 복사하고, `tests/test_intake_guard_mirror.py`가 **SHA-256 동일성**을 강제한다(정본만 고치고 미러를 안 고치면 시험 실패 → 어긋날 수 없음). 미러를 손으로 고치지 않는다.
- `intake_guard/__init__.py`: 두 코어의 공개 함수·타입·`MASKING_VERSION`을 다시 내보낸다. 패키지 버전 = `MASKING_VERSION` 기반.

## 내용
- `packages/intake_guard/pyproject.toml`(이름 `intake-guard`, 의존성 없음, Python ≥3.12, src 레이아웃), README(설치: `pip install -e packages/intake_guard` 또는 `pip install "intake-guard @ git+https://github.com/ai-agent-orchestrator/legal-intake-fastapi-lab#subdirectory=packages/intake_guard"`; 정본·미러 규칙).
- 패키지 시험: 대표 사례(차단·허용·마스킹·멱등) + `python -I -S` 없이 일반 설치 환경에서 `import intake_guard`.
- **시험 명령은 보안 범위로 지정**(RAG 시험은 이 환경에 langchain이 없어 수집 오류): 기존 보안 시험 파일 목록 + 새 시험 2개. 보고서에 그 명령과 `n passed`. 저장소 전체 통과로 표시하지 않는다.

## 공통 규칙
데이터(`data/golden_rules/**`, `profiles/*.json`, `data/equalizer/**`, `data/golden_sets/**`, `data/golden_retrieval/**`) 수정 금지, 구조 시험 통과(`KNOWN_DEBT` 증가 금지, LangChain·LangGraph·LangSmith import는 `rag/` 어댑터 파일에만), 기존 시험 기대값 수정·skip 금지, 네트워크·모델 다운로드·LLM 호출 금지. **끝나면 반드시 커밋.** 막히면 원인만 보고서에 적고 커밋 후 멈춤. 보고서: 구현·시험 통과 구분, 전체 시험 `n passed`.
