files: .github/workflows/tests.yml, README.md, docs/F7_REPORT_2026-11-10.md
forbid: data/**, profiles/**, src/**, tests/**, .env*
effort: low
coder: codex

# F7: GitHub Actions 시험 + README 배지 (낮 Codex 전용: NightCoder는 .github 금지)

## 내용
- `.github/workflows/tests.yml`: push·PR(main)에서 Ubuntu, Python 3.12, `pip install -e ".[test,langchain,chroma]"`, `pytest -q`. memvid가 없으면 memvid 시험은 **실패 대신 명시적 표시**가 되도록 워크플로 쪽에서 `-m "not memvid"`로 선택(시험 코드는 수정하지 않음; 이미 `memvid` 마커가 있는지 확인하고, 없으면 해당 파일 경로를 `--deselect`로 지정하고 보고서에 그 사실 명시).
- 외부 전송 없음: `LANGSMITH_TRACING=false`, 텔레메트리 끔 환경 변수.
- README 첫 줄 아래에 배지 한 줄(영문 README만, 한국어는 같은 배지). README의 다른 내용은 건드리지 않는다.

## 완료 기준
워크플로 문법 검사(`actionlint`가 없으면 YAML 파싱), 로컬에서 같은 명령으로 통과 개수 기록.

## 공통 규칙
데이터(`data/**`, `profiles/*.json`) 내용 수정 금지, 구조 시험 통과(`KNOWN_DEBT` 증가 금지, LangChain·LangGraph·LangSmith import는 `rag/` 어댑터 파일에만), 기존 시험 기대값 수정·skip 금지, 네트워크·모델 다운로드·LLM 호출 금지, 모든 새 기능은 순수 Python 공개 함수 + 얇은 CLI. **끝나면 반드시 커밋.** 막히면 원인만 보고서에 적고 커밋 후 멈춤. 보고서: 구현·시험 통과 구분, 전체 시험 `n passed`.
