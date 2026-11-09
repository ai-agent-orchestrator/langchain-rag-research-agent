files: src/rag_research_agent/ingest/sources.py, src/rag_research_agent/rag/cli.py, pyproject.toml, tests/test_sources.py, tests/test_cli.py, docs/PROTOTYPE_CLI.ko.md, docs/P1_REPORT_2026-11-09.md
forbid: data/golden_rules/**, profiles/*.json, data/equalizer/**, data/golden_sets/**, src/rag_research_agent/guard/masking.py, .env*
effort: high
coder: codex

# P1: 명령줄 `rra` + 입력 어댑터 (Equalizer 프로토타입)

## 목표
대표가 명령 한 줄로 글(파일·URL·붙여넣기)을 넣고 필터 프로필을 골라 브리프와 보드를 보는 것. LLM 호출 없음.

## 공통 규칙 (반드시 지킬 것)
- 저장소 `langchain-rag-research-agent`, main 최신에서 시작. 전체 맥락은 `docs/HANDOFF_CODEX_PROTOTYPE_2026-11-09.md`.
- 데이터 내용 수정 금지: `data/golden_rules/**`, `profiles/*.json`, `data/equalizer/**`, `data/golden_sets/**` (대표가 피드백 루프로 고치는 부분).
- `tests/test_structure.py` 통과 유지. `core` 외 모듈끼리 직접 import 금지, 조립은 `rag/`에서만. `KNOWN_DEBT`를 늘리지 않음.
- 기존 시험의 기대값 수정·skip·삭제 금지. 막히면 원인을 보고서에 적고 멈춤.
- 시험에서 외부 네트워크 접속 금지(가짜 fetcher 주입). LLM·외부 API 호출 금지. `.env` 접근 금지. push 금지(NightCoder가 패치로 회수).
- 합성 자료만 커밋. 실제 문서·결과물은 `.runs/`(git 무시)에만.
- 보고서: 구현·연결·시험 통과를 구분, 전체 시험 `n passed` 기록, "저장소 전체 통과" 같은 과장 금지, 열린 질문·미검증 항목 목록.

## 1. 입력 어댑터 `src/rag_research_agent/ingest/sources.py`
표준 라이브러리 기본. 이 파일은 `rag_research_agent.core`만 import 가능.
- `Document(source_id, title, text, origin, fetched_at, pages=None)` dataclass.
- `load_text_file(path)`: `.txt`, `.md` (UTF-8, BOM 허용).
- `load_docx(path)`: 선택 의존성 `docx` extra(`python-docx`). 없으면 설치 안내 오류.
- `load_pdf(path_or_bytes)`: 선택 의존성 `pdf` extra(`pypdf`). 페이지별 텍스트, 페이지 번호 기록. 추출 글자가 거의 없으면 "스캔 PDF로 보임, OCR 미지원" 안내 오류.
- `fetch_url(url, fetcher=None)`: `fetcher(url) -> (status, content_type, bytes)` 주입(기본 `urllib.request`, 타임아웃 20초, User-Agent는 일반 이름). HTML이면 `html.parser`로 script/style/nav/footer/aside 제외 본문 추출. PDF 응답이면 `load_pdf`.
- `google_doc_export_url(url)`: `docs.google.com/document/d/<id>/...` → `https://docs.google.com/document/d/<id>/export?format=txt`. 로그인 페이지·401·403이면 "링크 공유를 켜거나 txt/docx로 내려받아 --file로" 안내 오류. OAuth 없음.
- `github_raw_url(url)`: `github.com/<o>/<r>/blob/<ref>/<path>` → `raw.githubusercontent.com/<o>/<r>/<ref>/<path>`. 저장소 첫 화면 `github.com/<o>/<r>`는 README(`HEAD/README.md` → `README.ko.md` → `readme.md` 순). 그 외 깃허브 페이지는 일반 HTML. 404·비공개는 안내 오류. 인증 없음.
- `is_x_url(url)`: `x.com`, `twitter.com`, `mobile.twitter.com`이면 **가져오지 않고** "X는 로그인·약관 때문에 자동 수집하지 않습니다. 본문을 복사해 --text 또는 파일로 넣어 주세요" 오류.
- `load_source(arg, allow_network, fetcher=None)`: 경로/URL을 보고 위 함수로 분기. URL인데 `allow_network=False`면 실행하지 않고 안내.

## 2. 명령줄 `src/rag_research_agent/rag/cli.py`
`pyproject.toml`에 `[project.scripts] rra = "rag_research_agent.rag.cli:main"`, extras `pdf = ["pypdf"]`, `docx = ["python-docx"]` 추가(기존 항목 유지).
```
rra brief    --profile litigation (--file PATH ... | --url URL ... | --text "...") [--task "..."] [--budget 600]
             [--focus 금리:2 가계부채] [--auto-focus 2] [--allow-network] [--out .runs]
rra board    [--profiles litigation politics] [--sets data/golden_sets/*.json] [--budget 300] [--out .runs]
rra score    --set data/golden_sets/x.json [--packs macro] [--focus ...]
rra profiles
```
- 내부는 기존 함수 호출: `Equalizer.from_profile`(rag/profile.py), `scripts/filter_board.py`·`scripts/golden_edge_eval.py`의 함수(필요하면 그 로직을 `rag/` 아래 모듈로 옮기고 스크립트는 얇은 래퍼로 유지, 기존 시험이 깨지지 않게).
- `brief` 결과 폴더 `<out>/<UTC시각>-<profile>/`: `brief.md`(설정·상태·남긴 문장·생략 번호와 사유·감량 기록, 한국어), `trace.json`(행별 분류·점수·보호·사유, rule_version, 프로필 파일 해시), `input.txt`. 여러 입력이면 문서별 하위 폴더 + `index.md`. 마지막 줄에 결과 경로 출력.
- Windows 콘솔 한글: 출력 전 `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` 시도(실패해도 진행). 파일은 모두 UTF-8.
- 종료 코드: 정상 0, 입력·설정 오류 2, 차단(BLOCKED) 3.

## 3. 시험
- `tests/test_sources.py`: 가짜 fetcher로 HTML 추출, 구글 문서 변환·거부 안내, 깃허브 blob→raw와 README 경로, X 거절, `allow_network=False` 거절, PDF(시험 안에서 최소 PDF 생성; `pypdf` 없으면 설치 안내 오류가 나는지 시험).
- `tests/test_cli.py`: `main([...])`를 직접 호출. `brief --file <tmp 합성 txt>`가 세 파일 생성, `--url` + 네트워크 미허용 시 종료 코드 2, `profiles` 목록, `board --profiles litigation --out tmp`가 `board.html` 생성.

## 4. 문서 `docs/PROTOTYPE_CLI.ko.md` (대표용, 짧게)
설치 한 줄(`pip install -e ".[pdf,docx]"`), 명령 예 6개(파일·PDF·구글 문서·깃허브·붙여넣기·보드), 결과 파일 설명, 제약(X 붙여넣기, 구글 문서 공유 설정, 깃허브 공개만, 스캔 PDF 불가).

## 완료 기준
1. 위 시험 통과, 기존 시험 기준선 이상(새 시험 수 별도 표기), 구조 시험 통과.
2. `docs/P1_REPORT_2026-11-09.md` 작성.

## 멈춤 조건
금지 파일 수정 필요, `KNOWN_DEBT` 증가 필요, 네트워크 없이 시험 불가 설계, 기존 시험 실패.
