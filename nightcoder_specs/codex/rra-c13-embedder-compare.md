files: scripts/compare_embedders.py, src/rag_research_agent/observe/calibration.py, tests/test_compare_embedders.py, docs/C13_REPORT_2026-11-10.md
forbid: data/**, profiles/**, src/rag_research_agent/rag/**, src/rag_research_agent/store/**, .env*
effort: high
coder: codex

# C13: 임베딩 모델 비교와 임계값 보정 (설계 M2, 5-1절) — 결정 D8

## 목표
같은 골든셋으로 E5와 BGE-M3를 비교하고, 노브①(창)의 `τ_low`·`τ_high`를 모델별로 보정해 기록한다. 고정 0.85를 쓰지 않는다(F2).

## 내용
- `observe/calibration.py` (표준 라이브러리): 질의별 (정답 점수, 오답 최고 점수, 근거 없음 질의의 최고 점수) 목록 → `τ_low`(근거 있는 질의를 거의 다 살리는 가장 낮은 값), `τ_high`(근거 없음 오수용 0을 지키는 가장 보수적인 값), 1·2위 간격 분포, Hit@1/3, MRR. 기존 `observe/evaluate.py`의 `calibrate`가 있으면 재사용하고 중복 구현하지 않는다.
- `scripts/compare_embedders.py --models fake e5 bge-m3 --set data/golden_set.json --no-evidence data/golden_no_evidence.json`: 모델마다 색인을 `.runs/compare/<model>/`에 만들고(Chroma, 임베더 주입) 지표·보정값을 `.runs/calibration/<model>.json`(모델 ID·리비전 포함)과 비교표(Markdown + 어두운 HTML)로 출력. 캐시에 없는 모델은 건너뛰고 표에 "미준비"로 표시.
- 골든셋 형식은 기존 파일(`data/golden_set.json`, `golden_no_evidence.json`)을 그대로 읽는다. 형식이 맞지 않으면 어댑터 함수를 스크립트 안에 두고, 데이터 파일은 수정하지 않는다.
- 결과 해석 문구에 "합성 소규모 골든셋, 통계적 결론 아님"을 명시.

## 시험
fake 임베더로 전체 흐름(색인 → 지표 → 보정 → 파일), 보정 함수의 경계(근거 없음 0개, 동점, 한 질의) 단위 시험. 실제 모델은 시험하지 않는다.

## 공통 규칙
- 레인 브랜치에서 이전 명세 결과 위에 이어서 작업. 맥락: `docs/EQUALIZER_V0.ko.md`, `docs/DESIGN.ko.md` (결정 D8~D11).
- 데이터 내용 수정 금지: `data/golden_rules/**`, `profiles/*.json`, `data/equalizer/**`, `data/golden_sets/**`.
- `tests/test_structure.py` 통과 유지. `KNOWN_DEBT` 증가 금지. 무거운 라이브러리 import는 어댑터 파일 안에서만.
- 기존 시험 기대값 수정·skip·삭제 금지. 시험에서 네트워크·모델 다운로드 금지. LLM·`.env` 금지. push 금지.
- **끝나면 반드시 `git add` + `git commit`.** 막히면 원인만 보고서에 적고 그 보고서를 커밋한 뒤 멈춘다.
- 보고서: 구현·시험 통과 구분, 전체 시험 `n passed`, 대표가 직접 실행해야 하는 단계(모델 다운로드 등)를 명령과 함께 목록으로.
