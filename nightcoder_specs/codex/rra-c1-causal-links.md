files: src/rag_research_agent/ontology/link_rules.py, tests/test_link_rules.py, docs/C1_REPORT_2026-11-09.md
forbid: data/**, profiles/**, src/rag_research_agent/rag/**, src/rag_research_agent/edge/**, src/rag_research_agent/guard/masking.py, pyproject.toml, .env*
effort: high
coder: codex

# C1: 규칙 기반 인과 쌍 링크 (LinkBuilder 구현)

저장소 `langchain-rag-research-agent`, main 최신. 맥락: `docs/EQUALIZER_V0.ko.md`, `docs/GOLDEN_RULES.ko.md` 1-1절(쌍 보호).

## 목표
원인 문장과 결과 문장을 `CausalLink`로 이어, 감량(`diet/dieter.py`, 이미 링크된 쌍을 함께 빼거나 함께 남김)이 반쪽만 남기지 않게 한다.

## 내용 `ontology/link_rules.py` (표준 라이브러리, `core`만 import)
- `RuleLinkBuilder(source_text)`: `ontology.protocols.LinkBuilder` 구현, `with_text(text)` 지원(`RuleLabeler`와 같은 방식).
- 규칙(인접 문장 기준, 문장 i와 i+1):
  1. 뒤 문장이 결과 표지로 시작: "그 결과", "이에 따라", "따라서", "결국", "그래서" → (i → i+1, `causes`)
  2. 뒤 문장이 원인 표지로 시작: "그 이유는", "원인은", "이는 ~ 때문" → (i+1 → i, `causes`)
  3. 뒤 문장이 반박·대체: "그러나 실제로는", "하지만 실제로는" → (i+1 → i, `contradicts`)
  4. 같은 문장 안 인과는 링크 불필요(이미 한 문장).
- 링크마다 `origin="rule"`. 규칙 표지 목록은 파일 상단 상수 하나로 모아 고치기 쉽게.

## 시험 `tests/test_link_rules.py`
- 규칙별 합성 문장 쌍으로 링크 방향·종류 확인, 무관한 인접 문장은 링크 없음.
- `ClassOrderDieter`에 이 링크를 넣었을 때 쌍이 함께 제거되는 통합 시험(`diet`·`ingest.sentences` 사용, `rag/`는 수정 금지).

## 규칙
데이터·프로필 수정 금지, `rag/`·`edge/` 수정 금지(연결은 다음 단계), 구조 시험 통과, 기존 시험 기대값 수정·skip 금지, 네트워크·LLM 금지, push 금지. 막히면 원인만 `docs/C1_REPORT_2026-11-09.md`에 적고 멈춤. 보고서: 구현·시험 통과 구분, 전체 시험 `n passed`.
