files: src/rag_research_agent/rag/equalizer_graph.py, src/rag_research_agent/observe/local_log.py, tests/test_equalizer_graph.py, docs/P2_REPORT_2026-11-09.md
forbid: data/**, profiles/*.json, src/rag_research_agent/guard/masking.py, src/rag_research_agent/rag/brief.py, .env*
effort: high
coder: codex
after: rra-p3-lint

# P2: LangGraph 어댑터 + 로컬 기록 (설계 M4)

## 목표
`build_brief`와 **같은 부품(`Parts`)**으로 LangGraph 그래프를 조립해, 나중에 다른 에이전트 그래프에 서브그래프로 끼울 수 있게 한다(설계 `docs/DESIGN.ko.md` 6절, 공개 함수 `build_graph`).

## 공통 규칙 (반드시 지킬 것)
- 저장소 `langchain-rag-research-agent`, main 최신에서 시작. 전체 맥락은 `docs/HANDOFF_CODEX_PROTOTYPE_2026-11-09.md`.
- 데이터 내용 수정 금지: `data/golden_rules/**`, `profiles/*.json`, `data/equalizer/**`, `data/golden_sets/**` (대표가 피드백 루프로 고치는 부분).
- `tests/test_structure.py` 통과 유지. `core` 외 모듈끼리 직접 import 금지, 조립은 `rag/`에서만. `KNOWN_DEBT`를 늘리지 않음.
- 기존 시험의 기대값 수정·skip·삭제 금지. 막히면 원인을 보고서에 적고 멈춤.
- 시험에서 외부 네트워크 접속 금지(가짜 fetcher 주입). LLM·외부 API 호출 금지. `.env` 접근 금지. push 금지(NightCoder가 패치로 회수).
- 합성 자료만 커밋. 실제 문서·결과물은 `.runs/`(git 무시)에만.
- 보고서: 구현·연결·시험 통과를 구분, 전체 시험 `n passed` 기록, "저장소 전체 통과" 같은 과장 금지, 열린 질문·미검증 항목 목록.

## 내용
- `rag/equalizer_graph.py`: `build_graph(parts=None, profile=None)` → 컴파일된 그래프. 노드 `guard_input → chunk → label → score → select → diet → compose → output_check`. 각 노드는 `rag/brief.py`의 부품을 그대로 호출(로직 복사 금지; 공통 단계가 필요하면 `brief.py`를 고치지 말고 보고서에 리팩터링 제안).
- 상태: 요청마다 새로 생성, 공유 가변 상태 금지. 필드는 설계 4-3 이름 사용(`raw_draft`, `filtered_context`, `token_count`, `final_prompt_input`, `status`, `segments`, `edge_scores`, `protected_ids`, `excluded_segments`, `diet_rounds`, `versions` 등).
- `BLOCKED`, `REQUEST_MORE`, `BUDGET_PROTECTED_OVERFLOW`, `OUTPUT_REJECTED`에서는 이후 노드를 건너뛰고 종료(생성 호출 0회).
- `observe/local_log.py`: 실행마다 허용 목록 필드만 `.runs/trace.jsonl`에 추가(원문 전체 금지: 입력 해시·구간 ID·점수·분류·상태·버전만). LangSmith는 `observe/tracing.py`의 `serving_trace_guard` 안에서 실행.
- LangGraph import는 `rag/` 파일에만(구조 시험).

## 시험 `tests/test_equalizer_graph.py`
1. 같은 입력·같은 프로필에서 그래프 결과(`final_prompt_input`, `status`, 남긴 ID)와 `build_brief` 결과가 같다(합성 골든셋 2개 × 프로필 3개 이상).
2. 차단 입력(`[BLOCK]`)과 근거 없음에서 `diet`·`compose` 노드가 실행되지 않음(노드 호출 기록으로 확인).
3. 로컬 로그에 원문 문장이 들어가지 않음, 허용 필드만 있음.
4. LangSmith 업로드 0 (기존 `armed_tracing` 방식 참고, 시험 파일 안에 자체 fixture로).

## 완료 기준
위 시험 통과, 기존 시험 기준선 이상, 구조 시험 통과, `docs/P2_REPORT_2026-11-09.md`.

## 멈춤 조건
`brief.py` 수정 없이는 동일성 보장이 안 될 때: 구현을 멈추고 필요한 변경을 보고서에 제안.
