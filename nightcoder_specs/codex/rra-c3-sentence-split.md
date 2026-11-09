files: src/rag_research_agent/ingest/sentences.py, tests/test_sentences_ko.py, docs/C3_REPORT_2026-11-09.md
forbid: data/**, profiles/**, src/rag_research_agent/rag/**, src/rag_research_agent/edge/**, scripts/**, pyproject.toml, .env*
effort: medium
coder: codex

# C3: 한국어 문장 분할 개선 (`ingest/sentences.py`)

저장소 `langchain-rag-research-agent`, main 최신. 현재 `SentenceChunker`는 `.!?` 뒤 공백·줄바꿈에서 자른다.

## 목표
원문 오프셋을 유지하면서 한국어 기사·보고서에서 잘못 자르는 경우를 줄인다. 인터페이스(`split(text, source) -> list[Segment]`, ID `s01`...)는 그대로.

## 고칠 것 (각각 시험)
1. 소수점·버전·날짜 숫자 안의 점: "3.5%", "v2.1", "2026. 11. 9."는 자르지 않음.
2. 따옴표·괄호 안의 문장부호: `"...했다." 고 말했다`, `(예: A. B.)` 처리. 닫는 따옴표·괄호가 문장 끝 뒤에 붙으면 그 문자까지 포함.
3. 약어·이니셜: "U.S.", "e.g.", "Dr.", "Inc." 등 짧은 목록(상단 상수로 고치기 쉽게).
4. 줄 목록(`- `, `1. `, `• `)은 각 줄을 한 구간으로.
5. 빈 줄 여러 개, 앞뒤 공백, 전각 문장부호(。！？).
6. 오프셋 불변: 모든 구간에 대해 `text[s.start:s.end]`가 원문 그대로이고 공백으로 시작·끝나지 않음.

## 규칙
기존 시험(`tests/test_equalizer_v0.py`, `tests/test_edge_rules.py` 등)의 기대값 수정 금지. 기존 합성 골든셋에서 분할 결과(문장 수)가 바뀌면 보고서에 전후를 적는다(골든셋 파일은 수정 금지). 구조 시험 통과, 네트워크·LLM 금지, push 금지. 막히면 원인만 `docs/C3_REPORT_2026-11-09.md`에 적고 멈춤.
