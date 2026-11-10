files: src/rag_research_agent/lab/kiwi_terms.py, scripts/compare_lex_terms.py, pyproject.toml, tests/test_kiwi_lab.py, docs/C14_REPORT_2026-11-10.md
forbid: data/**, profiles/**, src/rag_research_agent/core/**, src/rag_research_agent/retrieve/**, src/rag_research_agent/store/**, .env*
effort: medium
coder: codex

# C14: Kiwi 형태소 키워드 실험 (설계 O5) — 결정 D10

## 목표
"반환이"와 "반환"을 같은 단어로 보는 한국어 키워드 처리를 **실험 모듈(lab)** 로 만들고, 기존 `core.lexical.lex_terms`와 비교한다. 승격(기본값 교체)은 하지 않는다.

## 내용
- `lab/kiwi_terms.py`: 선택 의존성 `kiwi` extra(`kiwipiepy`). `kiwi_terms(query) -> list[str]`: 명사·동사 어간·외래어·숫자+단위를 남기고 조사·어미 제거, 기존 `lex_terms`와 같은 제외 규칙(사건 유형 라벨, 1글자, OR/AND/NOT) 유지. `MATURITY = "lab"`.
- `scripts/compare_lex_terms.py --set data/golden_set.json`: 서재 키워드 검색(`search_lex`)을 두 방식으로 돌려 Hit@1/3, MRR, 질의별 차이를 표로. Kiwi 미설치면 안내 후 종료(0이 아닌 코드).
- 승격 기준을 보고서에 제안만: 예) Hit@3가 떨어지지 않고 MRR이 오르면 승격 검토.

## 시험
Kiwi가 설치돼 있으면 조사 제거 사례("반환이"→"반환", "계약서를"→"계약서"), 미설치면 `importorskip`으로 이유를 남기고 skip(조용한 skip 금지). 비교 스크립트는 가짜 term 함수 주입으로 흐름 시험.

## 공통 규칙
- 레인 브랜치에서 이전 명세 결과 위에 이어서 작업. 맥락: `docs/EQUALIZER_V0.ko.md`, `docs/DESIGN.ko.md` (결정 D8~D11).
- 데이터 내용 수정 금지: `data/golden_rules/**`, `profiles/*.json`, `data/equalizer/**`, `data/golden_sets/**`.
- `tests/test_structure.py` 통과 유지. `KNOWN_DEBT` 증가 금지. 무거운 라이브러리 import는 어댑터 파일 안에서만.
- 기존 시험 기대값 수정·skip·삭제 금지. 시험에서 네트워크·모델 다운로드 금지. LLM·`.env` 금지. push 금지.
- **끝나면 반드시 `git add` + `git commit`.** 막히면 원인만 보고서에 적고 그 보고서를 커밋한 뒤 멈춘다.
- 보고서: 구현·시험 통과 구분, 전체 시험 `n passed`, 대표가 직접 실행해야 하는 단계(모델 다운로드 등)를 명령과 함께 목록으로.
