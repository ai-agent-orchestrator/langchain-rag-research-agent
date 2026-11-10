files: src/rag_research_agent/rag/brief.py, src/rag_research_agent/rag/profile.py, src/rag_research_agent/rag/library.py, tests/test_wiring_c8.py, docs/EQUALIZER_V0.ko.md, docs/C8_REPORT_2026-11-10.md
forbid: data/**, profiles/**, src/rag_research_agent/ontology/**, src/rag_research_agent/retrieve/**, .env*
effort: high
coder: codex

# C8: 인과 쌍 링크(C1)·의미 관련도(C4)를 조립에 연결

## 전제
같은 레인에서 C1(`ontology/link_rules.py` `RuleLinkBuilder`)과 C4(`retrieve/semantic_relevance.py` `make_semantic_relevance`)가 커밋돼 있어야 한다. **없으면 구현하지 말고 보고서에 "전제 없음"만 적고 커밋한 뒤 멈춘다.**

## 내용
- `Parts` 기본 `link_builder`를 `RuleLinkBuilder`로(텍스트 주입은 `with_text` 방식, `labeler`와 같게). 기존 동작과 달라지는 시험이 있으면 기대값을 바꾸지 말고 `Parts(link_builder=FakeLinkBuilder())`로 명시해 기존 시험을 유지하는 방법을 쓰되, **기존 시험 파일 수정은 금지**이므로 기본값 변경 대신 `Parts.with_defaults_v1()` 같은 새 생성자를 추가하는 쪽을 우선 검토하고 보고서에 선택 이유를 적는다.
- `Library.brief(...)`: 서재의 임베더로 `make_semantic_relevance`를 만들어 관련도로 사용하는 옵션(`relevance="semantic"|"overlap"`, 기본 overlap 유지).
- `Equalizer.brief(..., parts_preset="v1")` 같은 방식으로 새 기본 조합을 선택 가능하게.
- `docs/EQUALIZER_V0.ko.md` 부품 표에 연결 상태 갱신.

## 시험 `tests/test_wiring_c8.py`
인과 쌍이 있는 합성 초안에서 v1 조합으로 감량 시 쌍이 함께 남거나 함께 빠짐, semantic 관련도 옵션으로 서재 브리프가 돌아감(가짜 임베더), 기존 시험 전부 그대로 통과.

## 공통 규칙
- 저장소 `langchain-rag-research-agent`, 레인 브랜치에서 이전 명세 결과 위에 이어서 작업. 맥락: `docs/EQUALIZER_V0.ko.md`, `docs/HANDOFF_CODEX_PROTOTYPE_2026-11-09.md` 3절.
- 데이터 내용 수정 금지: `data/golden_rules/**`, `profiles/*.json`, `data/equalizer/**`, `data/golden_sets/**`.
- `tests/test_structure.py` 통과 유지(모듈 간 직접 import 금지, 조립은 `rag/`·`scripts/`에서). `KNOWN_DEBT` 증가 금지.
- 기존 시험 기대값 수정·skip·삭제 금지. 네트워크·LLM·`.env` 금지. push 금지.
- **작업이 끝나면 반드시 `git add`와 `git commit`으로 커밋한다**(커밋이 없으면 실패로 처리됨). 막히면 원인만 보고서에 적고, 그 보고서도 커밋한 뒤 멈춘다.
- 보고서: 구현·시험 통과 구분, 전체 시험 `n passed`, 한계·열린 질문.
