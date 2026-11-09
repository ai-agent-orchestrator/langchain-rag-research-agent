# Codex 인수인계: Equalizer 프로토타입 (2026-11-09 야간)

저장소: `langchain-rag-research-agent` · 기준: **main 최신** · 작성: Claude (대표 승인 방향)

## 0. 한 줄 요약

**고정 부분(입력, 실행, 그래프, 기록, 검증)은 단단하게 만들고, 바뀌는 부분(골든룰 150개, 필터 프로필)은 데이터 파일로 남겨 손대지 않는다.** 프로토타입이다. LLM 호출은 없다(브리프까지).

## 1. 대표 결정 (2026-11-09)

| 항목 | 결정 |
| --- | --- |
| 골든룰 | 150개 + 분야 묶음 50개로 확정, 이후 피드백 루프로 계속 수정 (`data/golden_rules/research_v1.json`) |
| 필터 | 프로필 파일 하나 = 분야 필터 하나 (`profiles/*.json`), 누구나 템플릿 복사로 만들 수 있게 |
| LLM | **프로토타입에서는 연결하지 않음.** 추출 브리프까지 |
| 실행 방식 | **명령줄 + 보드 HTML** |
| 입력 | **구글 문서, X 웹페이지 주소** (+ 텍스트 파일) |
| 소송 감량 순서 | `profiles/litigation.json`의 초안 그대로 실험 (O1은 보드 결과로 나중에 결정) |

## 2. 지금 있는 것 (main)

- `rag/brief.py` `build_brief(...)`: 입력 정책 → 문장 분할 → 분류 → 관련도 → 엣지 점수 → 노브 → 보호 경로 → 감량 → 추출 조립 → 출력 검사. 모든 부품은 `Parts`로 교체.
- `rag/profile.py` `Equalizer.from_profile(name_or_path).brief(text, ...)`, `load_profile`, `list_profiles`.
- `edge/rules.py`, `edge/scorer.py`, `edge/focus.py`, `knobs/mapper.py`, `diet/dieter.py`, `compose/extractive.py`, `ingest/sentences.py`, `ontology/rule_labeler.py`.
- 스크립트: `scripts/golden_edge_eval.py`, `scripts/brief_demo.py`, `scripts/filter_board.py`, `scripts/render_rules_catalog.py`.
- 문서: `docs/EQUALIZER_V0.ko.md`, `docs/GOLDEN_RULES.ko.md`, `docs/FEEDBACK_LOOP.ko.md`, `profiles/README.md`.
- 시험: 클라우드 86 passed (memvid-sdk 미설치로 8건 실패). Windows 실제 memvid 기준은 Codex가 확인.

## 3. 공통 규칙 (모든 명세)

- **손대지 않는 데이터:** `data/golden_rules/**`, `profiles/*.json`(내용), `data/equalizer/presets_v0.json`, `data/golden_sets/**`. 대표가 피드백 루프로 고치는 부분이다. 형식 검증 코드는 추가해도 되지만 **내용은 바꾸지 않는다.**
- **모듈 경계(P0):** `tests/test_structure.py`가 통과해야 한다. `core` 외 모듈끼리 직접 import 금지, 조립은 `rag`(와 CLI)에서만. `KNOWN_DEBT`를 늘리지 않는다.
- **합성 자료만** 커밋한다. 실제 기사·문서·결과물은 `.runs/`(커밋 안 함)에만 둔다.
- **네트워크:** 시험에서는 절대 외부 접속하지 않는다(가짜 fetcher). 실행 시 URL 가져오기는 `--allow-network`를 줬을 때만.
- **X(트위터):** 자동 수집하지 않는다(로그인 요구·약관). X 주소가 오면 "본문을 복사해 `--text`나 파일로 넣으라"는 안내 오류를 낸다.
- **구글 문서:** "링크가 있는 모든 사용자" 공유 문서만 `export?format=txt` 주소로 가져온다. 비공개 문서는 내려받은 `.txt`/`.docx`로. OAuth 연동은 하지 않는다.
- LLM·외부 API 호출 금지, `.env` 접근 금지, push는 브랜치에만, main 병합 금지.
- 기존 시험의 기대값 수정·skip·삭제 금지. 막히면 원인을 보고서에 적고 멈춘다.
- 보고: 구현·연결·시험 통과를 구분하고 통과 개수를 적는다. "전체 통과"라고 쓰지 않는다.

## 4. 우선순위 (사용량이 부족하면 위에서부터)

1. **P1 명령줄 + 입력 어댑터** (가장 중요, 대표가 바로 씀)
2. **P3 프로필·규칙 검사기** (교체 부분이 깨지지 않게)
3. **P2 LangGraph 어댑터 + 로컬 기록** (설계 M4)

각 명세는 브랜치 하나, 보고서 하나. 하나를 끝내고 다음으로 간다.

---

## 명세 P1: 명령줄 `rra` + 입력 어댑터

```
files: src/rag_research_agent/ingest/sources.py, src/rag_research_agent/rag/cli.py, pyproject.toml, tests/test_sources.py, tests/test_cli.py, docs/PROTOTYPE_CLI.ko.md, docs/P1_REPORT_2026-11-09.md
forbid: data/golden_rules/**, profiles/*.json, data/equalizer/**, data/golden_sets/**, src/rag_research_agent/guard/masking.py, .env*
effort: high
coder: codex
```

### 목표
대표가 명령 한 줄로 글을 넣고 필터를 골라 브리프와 보드를 보는 것.

### 입력 어댑터 (`ingest/sources.py`, 표준 라이브러리만, 다른 모듈 import 금지 — `core`만)
- `Document(source_id, title, text, origin, fetched_at)` (dataclass, `core`에 두거나 `ingest` 안에)
- `load_text_file(path)` — `.txt`, `.md`
- `load_docx(path)` — `.docx` (선택 의존성 `docx` extra로 `python-docx`; 없으면 안내 오류)
- `fetch_url(url, fetcher)` — `fetcher`는 주입(기본은 `urllib.request`). HTML이면 표준 `html.parser`로 `script/style/nav/footer`를 빼고 본문 텍스트 추출.
- `google_doc_export_url(url)` — `docs.google.com/document/d/<id>/...` → `.../export?format=txt`. 접근 거부(로그인 페이지·403)면 "공유 설정 또는 내려받기" 안내 오류.
- `is_x_url(url)` — `x.com`, `twitter.com`이면 **수집하지 않고** 안내 오류.

### 명령 (`rag/cli.py`, `pyproject`의 `[project.scripts] rra = "rag_research_agent.rag.cli:main"`)
```
rra brief  --profile litigation  (--file a.txt | --url https://... | --text "...")  [--task "..."] [--budget 600] [--focus 금리:2 가계부채] [--auto-focus 2] [--allow-network] [--out .runs]
rra board  [--profiles litigation politics] [--sets data/golden_sets/*.json] [--budget 300]
rra score  --set data/golden_sets/x.json [--packs macro] [--focus ...]      # golden_edge_eval 래핑
rra profiles                                                               # 목록과 한 줄 설명
```
- `brief` 결과: `.runs/<UTC시각>-<profile>/` 아래 `brief.md`(사람용: 설정, 상태, 남긴 문장, 생략 번호와 사유, 감량 기록), `trace.json`(행별 점수·분류·보호·사유, rule_version, 프로필 해시), `input.txt`(가져온 원문). 마지막에 경로를 출력.
- 여러 `--file`/`--url`을 주면 문서 단위로 각각 처리하고 `index.md`에 모은다.
- 기존 `scripts/*.py`는 그대로 둔다(호환). CLI가 같은 함수를 호출하게 한다.

### 완료 기준
1. 가짜 fetcher로 HTML 본문 추출, 구글 문서 주소 변환, 접근 거부 안내, X 주소 거절을 시험한다(네트워크 0).
2. `rra brief --profile litigation --file <합성 txt>`가 `.runs/` 아래 세 파일을 만든다(시험은 `tmp_path`).
3. `--allow-network` 없이 `--url`을 주면 실행하지 않고 안내한다.
4. 구조 시험 포함 전체 시험이 기준선 이상(새 시험 개수 별도 표기).
5. `docs/PROTOTYPE_CLI.ko.md`: 대표용 사용법(설치 한 줄, 명령 예 5개, 결과 파일 설명, X·구글 문서 제약).

### 멈춤 조건
- 금지 파일 수정이 필요하거나 구조 시험을 통과시키려면 `KNOWN_DEBT`를 늘려야 할 때.
- 외부 접속 없이는 시험할 수 없는 설계가 될 때.

---

## 명세 P3: 프로필·골든룰 검사기 (교체 부분 보호)

```
files: src/rag_research_agent/rag/lint.py, src/rag_research_agent/rag/cli.py, schemas/profile.schema.json, schemas/golden_rules.schema.json, tests/test_lint.py, docs/P3_REPORT_2026-11-09.md
forbid: data/golden_rules/**, profiles/*.json, data/equalizer/**, data/golden_sets/**, .env*
effort: medium
coder: codex
after: P1
```

### 목표
대표나 다른 사람이 프로필·규칙 파일을 고쳤을 때 **실행 전에** 실수를 잡는다.

### 검사 항목 (`rra check <파일>`; 오류와 경고를 구분)
- 오류: JSON 문법, 필수 항목, 정규식 컴파일 실패, 중복 ID, 정의 안 된 분류가 `diet_order`/`never_remove`에, 없는 묶음 이름(`packs`), 집중 키워드 6개 이상, 가중치 음수.
- 경고: 같은 `cue`가 여러 분류·규칙에 겹침(어느 쪽이 먼저 걸리는지 표시), 한 글자 `cue`, 분류가 `diet_order`에서 빠짐(맨 뒤로 감), `cue`가 클리셰와 기둥에 동시에 있음.
- `schemas/*.json`은 문서 겸 형식 정의(JSON Schema 초안). 검사기는 표준 라이브러리로 구현하고, `jsonschema`는 쓰지 않아도 된다.
- 출력: 사람이 읽는 표 + 종료 코드(오류 1, 경고만 0).

### 완료 기준
- 제공 파일 전부(`profiles/*.json`, `data/golden_rules/research_v1.json`)가 **오류 0**으로 통과(경고는 보고서에 목록으로).
- 일부러 깨뜨린 합성 파일들로 각 오류·경고를 시험.

---

## 명세 P2: LangGraph 어댑터 + 로컬 기록 (설계 M4)

```
files: src/rag_research_agent/rag/equalizer_graph.py, src/rag_research_agent/observe/local_log.py, tests/test_equalizer_graph.py, docs/P2_REPORT_2026-11-09.md
forbid: data/**, profiles/*.json, src/rag_research_agent/guard/masking.py, .env*
effort: high
coder: codex
after: P3
```

### 목표
`build_brief`와 **같은 부품(`Parts`)**으로 LangGraph 그래프를 조립해 다른 에이전트 그래프에 끼울 수 있게 한다(설계 6절, 공개 함수 `build_graph`).

### 내용
- 노드: `guard_input → chunk → label → score → select → diet → compose → output_check`. 상태는 요청마다 새로 만든다(공유 가변 상태 금지). 설계 4-3의 필드 이름(`raw_draft`, `filtered_context`, `final_prompt_input`, `status` 등)을 쓴다.
- `BLOCKED`, `REQUEST_MORE`, `BUDGET_PROTECTED_OVERFLOW`에서는 이후 노드를 건너뛰고 끝낸다(생성 호출 0회).
- **같은 입력에 대해 그래프 결과와 `build_brief` 결과가 같아야 한다**(시험).
- `observe/local_log.py`: 실행마다 허용 목록 필드만 JSONL로 `.runs/trace.jsonl`에 남김(원문 전체·개인정보 필드 금지, 해시·ID·점수·상태만). LangSmith는 끄고(`serving_trace_guard`), 업로드 0 시험.
- LangGraph import는 `rag/` 어댑터 파일에만(구조 시험).

### 완료 기준
- 그래프·`build_brief` 동일성 시험, 차단·근거 없음에서 후속 노드 미실행 시험, 업로드 0 시험, 구조 시험 통과.

---

## 5. 하지 않는 것 (이번 프로토타입)

LLM 백본 호출, E5 임베딩 관련도(τ 보정 필요, 다음 단계), 차트 이미지 입력(O6), 예측 모듈(O8), X 자동 수집, 구글 OAuth, 웹 화면, 골든룰·프로필 내용 수정.

## 6. 아침에 대표가 볼 것

1. 각 보고서(`docs/P1_REPORT...`, `P3`, `P2`)의 통과 개수와 열린 질문.
2. `rra brief --profile litigation --file <내 글>` 한 번 실행 → `.runs/.../brief.md`.
3. `rra board` → `.runs/board.html`에서 필터별 수치 비교.
