files: src/rag_research_agent/rag/brief.py, src/rag_research_agent/rag/stages.py, src/rag_research_agent/rag/equalizer_graph.py, src/rag_research_agent/observe/local_log.py, tests/test_equalizer_graph.py, docs/P2B_REPORT_2026-11-10.md
forbid: data/**, profiles/**, src/rag_research_agent/guard/masking.py, .env*
effort: high
coder: codex

# P2b: 단계 함수 분리 + LangGraph 어댑터 (P2 보류 해제)

## 배경
P2는 `rag/brief.py` 수정 금지 때문에 보류됐다(`docs/P2_REPORT_2026-11-09.md`). 이번에는 **`brief.py`의 단계 분리를 허용**한다. 목표는 같은 단계 함수를 순수 Python(`build_brief`)과 LangGraph(`build_graph`)가 함께 쓰는 것(로직 복사 금지, 모듈 원칙 P0).

## 내용
1. `rag/stages.py`: `build_brief`의 단계를 순수 함수로 분리 — `guard_input`, `chunk_and_label`, `score`, `select`, `diet`, `compose_and_check`. 입력·출력은 하나의 상태 dict(설계 4-3 필드 이름: `raw_draft`, `segments`, `edge_scores`, `protected_ids`, `excluded_segments`, `diet_rounds`, `final_prompt_input`, `status`, `versions` 등). `Parts`를 인자로 받는다.
2. `rag/brief.py`의 `build_brief`는 그 단계들을 차례로 호출하는 얇은 함수로 바꾼다. **공개 시그니처·반환값(`Brief`, `BriefTrace`)·동작은 그대로.** 기존 시험 전부 기대값 수정 없이 통과해야 한다.
3. `rag/equalizer_graph.py`: `build_graph(parts=None, profile=None)` → 같은 단계 함수를 노드로 쓰는 LangGraph. `BLOCKED`·`REQUEST_MORE`·`BUDGET_PROTECTED_OVERFLOW`·`OUTPUT_REJECTED`에서는 조건 분기로 바로 종료(생성 0회). LangGraph import는 이 파일 안에서만.
4. `observe/local_log.py`: 허용 목록 필드만 `.runs/trace.jsonl`(원문 금지: 입력 해시·구간 ID·점수·분류·상태·버전). LangSmith는 `serving_trace_guard` 안에서.

## 시험 `tests/test_equalizer_graph.py`
- 합성 골든셋 2개 × 프로필 3개 이상에서 그래프 결과와 `build_brief` 결과(`final_prompt_input`, `status`, 남긴 ID)가 같다.
- 차단·근거 없음에서 `diet`·`compose` 노드가 실행되지 않음(노드 호출 기록).
- 로컬 로그에 원문 문장 없음, 허용 필드만.
- LangSmith 업로드 0 (자체 fixture).

## 공통 규칙
데이터 수정 금지, 구조 시험 통과(`KNOWN_DEBT` 증가 금지), 기존 시험 기대값 수정·skip 금지, 네트워크·LLM 금지, push 금지(NightCoder) / 브랜치 push(낮 Codex). **끝나면 반드시 커밋.** 막히면 원인만 보고서에 적고 커밋 후 멈춤.
