files: scripts/suggest_cues.py, tests/test_suggest_cues.py, docs/C11_REPORT_2026-11-10.md
forbid: data/**, profiles/**, src/**, .env*
effort: medium
coder: codex

# C11: 신호 표현 추천 도우미 (피드백 루프 보조, 자동 수정 없음)

## 목표
골든셋에서 놓친 문장(보존 목록인데 하위권)과 과대평가 문장을 보고, 규칙 파일·프로필에 추가하거나 뺄 **후보 표현**을 제안한다. 파일은 절대 자동으로 고치지 않는다.

## 내용 `scripts/suggest_cues.py`
- `--set ... --packs ... [--profile litigation]`: `golden_edge_eval.evaluate` 결과를 사용.
- 놓친 문장마다: 어떤 규칙에도 안 걸린 2~6글자 어절·연결어(조사 제거)를 후보로, 다른 보존 문장에도 나오면 가산. 이미 있는 cue와 겹치면 제외.
- 과대평가 문장마다: 그 문장을 올린 규칙 ID와 cue를 표시(뺄 후보).
- 프로필을 주면, 놓친 문장이 Unclassified로 분류됐는지와 어느 분류의 cues에 넣으면 잡히는지 제안.
- 출력: 표(문장, 현재 이유, 추가 후보, 뺄 후보) Markdown + `.runs/cue_suggestions.json`.

## 시험
합성 골든셋에서 놓친 문장의 후보에 그 문장 고유 표현이 들어가는지, 이미 있는 cue는 제외되는지, 파일이 수정되지 않는지(해시 비교).

## 공통 규칙
- 저장소 `langchain-rag-research-agent`, 레인 브랜치에서 이전 명세 결과 위에 이어서 작업. 맥락: `docs/EQUALIZER_V0.ko.md`, `docs/HANDOFF_CODEX_PROTOTYPE_2026-11-09.md` 3절.
- 데이터 내용 수정 금지: `data/golden_rules/**`, `profiles/*.json`, `data/equalizer/**`, `data/golden_sets/**`.
- `tests/test_structure.py` 통과 유지(모듈 간 직접 import 금지, 조립은 `rag/`·`scripts/`에서). `KNOWN_DEBT` 증가 금지.
- 기존 시험 기대값 수정·skip·삭제 금지. 네트워크·LLM·`.env` 금지. push 금지.
- **작업이 끝나면 반드시 `git add`와 `git commit`으로 커밋한다**(커밋이 없으면 실패로 처리됨). 막히면 원인만 보고서에 적고, 그 보고서도 커밋한 뒤 멈춘다.
- 보고서: 구현·시험 통과 구분, 전체 시험 `n passed`, 한계·열린 질문.
