files: src/rag_research_agent/guard/intake_guard_adapter.py, src/rag_research_agent/rag/brief.py, pyproject.toml, tests/test_intake_guard_adapter.py, docs/C16_REPORT_2026-11-10.md
forbid: data/**, profiles/**, src/rag_research_agent/guard/masking.py, .env*
effort: medium
coder: codex

# C16: 리서치 저장소에 보안 패키지 연결 (설계 M3) — 결정 D11

## 전제
C15가 완료돼 `intake-guard` 패키지를 설치할 수 있어야 한다(git URL 또는 로컬 경로). **설치할 수 없으면 구현하지 말고 보고서에 "전제 없음"만 적고 커밋한 뒤 멈춘다.**

## 내용
- `pyproject` extra `guard = ["intake-guard @ git+https://github.com/ai-agent-orchestrator/legal-intake-fastapi-lab#subdirectory=packages/intake_guard"]`.
- `guard/intake_guard_adapter.py`: `IntakeMasker`(`Masker` 프로토콜), `IntakeInputPolicy`(`InputPolicy` 프로토콜, `PolicyDecision`으로 변환). 패키지 import는 이 파일 안에서만. 미설치면 안내 오류.
- `rag/brief.py`: `Parts`의 기본 입력 정책을 "패키지가 설치돼 있으면 `IntakeInputPolicy`, 아니면 기존 가짜"로 고르는 생성자(`Parts.with_guard()`)를 추가. **기존 기본값은 바꾸지 않는다**(기존 시험 보호). 서재 적재 전에 마스킹을 적용하는 옵션(`Library(masker=...)`)은 `rag/library.py`를 건드리지 말고 보고서에 다음 단계로 제안.
- 연구 저장소의 `guard/masking.py`(frozen)는 그대로 둔다. 정본은 패키지(결정 D3, 마스킹 구현 복사 금지).

## 시험
패키지 설치 시: 개인정보 합성 문자열이 마스킹됨, 차단 입력이 `BLOCKED`로 이어져 생성 0회. 미설치 시 `importorskip`으로 이유 남기고 skip. 구조 시험 통과.

## 공통 규칙
- 레인 브랜치에서 이전 명세 결과 위에 이어서 작업. 맥락: `docs/EQUALIZER_V0.ko.md`, `docs/DESIGN.ko.md` (결정 D8~D11).
- 데이터 내용 수정 금지: `data/golden_rules/**`, `profiles/*.json`, `data/equalizer/**`, `data/golden_sets/**`.
- `tests/test_structure.py` 통과 유지. `KNOWN_DEBT` 증가 금지. 무거운 라이브러리 import는 어댑터 파일 안에서만.
- 기존 시험 기대값 수정·skip·삭제 금지. 시험에서 네트워크·모델 다운로드 금지. LLM·`.env` 금지. push 금지.
- **끝나면 반드시 `git add` + `git commit`.** 막히면 원인만 보고서에 적고 그 보고서를 커밋한 뒤 멈춘다.
- 보고서: 구현·시험 통과 구분, 전체 시험 `n passed`, 대표가 직접 실행해야 하는 단계(모델 다운로드 등)를 명령과 함께 목록으로.
