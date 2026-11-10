files: src/rag_research_agent/rag/tune.py, scripts/tune.py, tests/test_tune.py, docs/TUNE_WORKFLOW.ko.md, docs/F4_REPORT_2026-11-10.md
forbid: data/**, profiles/**, .env*
effort: high
coder: codex

# F4: 튜닝 제안 → 승인 → 적용 흐름 (피드백 루프 자동화, 데이터는 대표 승인으로만)

## 목표
골든룰·프로필 수정을 "제안 파일"로 만들고, 대표가 승인하면 백업 후 적용·버전 기록·전후 보드 비교까지 한 번에.

## 내용
- `rag/tune.py`:
  - `propose(set, profile, packs)`: `golden_edge_eval`·`suggest_cues`(C11) 결과로 변경 제안 목록(추가 cue, 뺄 cue, 분류 cues 추가) → `.runs/tune/<시각>/proposal.json`(항목마다 근거 문장과 예상 효과).
  - `apply(proposal, accept_ids)`: **대표가 고른 항목만** 대상 파일(규칙 JSON 또는 프로필 JSON)에 적용. 적용 전 원본을 `.runs/tune/<시각>/backup/`에 복사, 적용 후 `rag.lint`(P3) 검사 통과 필수, 실패하면 자동 되돌림. 변경 내역 `CHANGELOG` 한 줄(규칙 버전 해시 전→후).
  - `compare(before_run, after_run)`: 적용 전후 `filter_board` 지표 차이 표.
- `scripts/tune.py propose|apply|compare`. **`apply`는 `--yes` 없이는 무엇을 바꿀지 보여만 준다.**
- 이 명세에서 Codex는 **실제 데이터 파일에 apply를 실행하지 않는다**(시험은 임시 복사본으로만).
- `docs/TUNE_WORKFLOW.ko.md`: 대표용 4단계(제안 보기 → 고르기 → 적용 → 보드 비교).

## 시험
임시 폴더의 복사본으로 제안 생성, 일부 승인 적용, lint 실패 시 자동 되돌림, 백업 존재, 버전 해시 변경, `--yes` 없으면 파일 불변.

## 공통 규칙
데이터(`data/**`, `profiles/*.json`) 내용 수정 금지, 구조 시험 통과(`KNOWN_DEBT` 증가 금지, LangChain·LangGraph·LangSmith import는 `rag/` 어댑터 파일에만), 기존 시험 기대값 수정·skip 금지, 네트워크·모델 다운로드·LLM 호출 금지, 모든 새 기능은 순수 Python 공개 함수 + 얇은 CLI. **끝나면 반드시 커밋.** 막히면 원인만 보고서에 적고 커밋 후 멈춤. 보고서: 구현·시험 통과 구분, 전체 시험 `n passed`.
