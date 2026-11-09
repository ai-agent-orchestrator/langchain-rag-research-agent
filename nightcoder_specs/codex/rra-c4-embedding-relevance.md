files: src/rag_research_agent/retrieve/semantic_relevance.py, tests/test_semantic_relevance.py, docs/C4_REPORT_2026-11-09.md
forbid: data/**, profiles/**, src/rag_research_agent/rag/**, src/rag_research_agent/embed/**, src/rag_research_agent/edge/**, pyproject.toml, .env*
effort: medium
coder: codex

# C4: 의미 유사도 관련도 부품 (교체용, 모델 다운로드 없음)

저장소 `langchain-rag-research-agent`, main 최신. 현재 `build_brief`의 관련도는 `rag/brief.py`의 `term_overlap(task)`(과제 단어 겹침)이고, `Parts.relevance`로 교체할 수 있다(시그니처: `relevance(task) -> (segment_text -> float 0..1)`).

## 목표
임베딩 기반 관련도를 `Parts.relevance`에 그대로 끼울 수 있는 부품으로 만든다. 연결(`rag/` 수정)은 다음 단계.

## 내용 `retrieve/semantic_relevance.py`
- `make_semantic_relevance(embedder, normalize="minmax"|"none", cache=True)` → `relevance(task)` 함수 반환.
- `embedder`는 **덕 타이핑**: `encode_query(text) -> list[float]`, `encode_documents(texts) -> list[list[float]]`를 가진 객체. `embed` 모듈을 import하지 않는다(구조 시험: 모듈 간 직접 import 금지).
- 과제가 없으면 모든 구간 1.0(기존 동작과 같음). 코사인 유사도를 0..1로 정규화. 같은 문장 반복 계산은 캐시.
- 임계값(τ) 보정은 하지 않는다(설계 5-1, 모델별 골든셋 보정이 필요). 보고서에 "보정 전"을 명시.

## 시험 `tests/test_semantic_relevance.py`
- 시험 안에서 정의한 결정적 가짜 임베더(단어 해시 기반 벡터)로: 관련 문장이 무관 문장보다 높음, 과제 없음 1.0, 범위 0..1, 캐시 동작.
- `rag.brief.Parts(relevance=make_semantic_relevance(fake))`로 `build_brief`가 돌아가는 통합 시험(시험 파일에서만 조립, `rag/` 수정 금지).
- 실제 E5 모델 로드·다운로드 금지.

## 규칙
구조 시험 통과, 기존 시험 기대값 수정·skip 금지, 네트워크·LLM 금지, push 금지. 막히면 원인만 `docs/C4_REPORT_2026-11-09.md`에 적고 멈춤.
