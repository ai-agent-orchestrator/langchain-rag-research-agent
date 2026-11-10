# 다른 프로젝트에 붙이기

순수 Python에서는 `Equalizer.from_profile("research").brief(text)` 또는
`Library(path, embedder="fake").open().brief(query)`를 호출합니다.
실제 모델은 먼저 준비하고, 서재를 만들 때와 같은 임베더·리비전으로 여세요.

LangChain 연결(선택 의존성 `.[langchain]`, 서재는 `.[chroma]`):

```python
from rag_research_agent.rag.library import Library
from rag_research_agent.rag.lc_adapters import LibraryRetriever, EqualizerRunnable, library_brief_tool, make_research_chain
lib = Library(".runs/library").open()
result = make_research_chain(lib, "research").invoke("질문")
tool = library_brief_tool(lib, "research")
```

| 수업 개념 | 연결 객체 | 반환 |
| --- | --- | --- |
| Retriever | LibraryRetriever(library=lib, k=8, mode="hybrid") | 본문과 출처·점수·순위가 담긴 Document 목록 |
| Runnable/LCEL | EqualizerRunnable(profile, budget) | brief/status/kept_ids/excluded |
| Tool | library_brief_tool(lib, profile) | research_brief 도구의 브리프 문자열 |
| LCEL 파이프 | make_research_chain(lib, profile) | 검색→본문 결합→추출 결과 |

Runnable 입력은 문자열 또는 `{"text": "본문", "task": "질문"}`입니다.
추출만 수행하며 모델 생성은 호출하지 않습니다. 어댑터 직접 invoke/ainvoke는
원격 tracing을 끕니다. 별도로 구성한 상위 체인·에이전트 전체도 서비스 실행에서는
`serving_trace_guard()`로 감싸세요.

LangGraph에는 P2b 서브그래프를 노드로 연결할 수 있습니다.

```python
from langgraph.graph import StateGraph, START, END
from rag_research_agent.rag.equalizer_graph import build_graph
parent = StateGraph(dict)
parent.add_node("equalize", build_graph(profile="research"))
parent.add_edge(START, "equalize")
parent.add_edge("equalize", END)
# parent.compile().invoke({"raw_draft": "합성 본문"})를 serving_trace_guard 안에서 호출
```

P2b 결과는 status/final_prompt_input/included_ids 및 단계 상태를 포함합니다.
기본 로컬 로그는 `.runs/trace.jsonl`, 비활성화하려면 `log_path=None`입니다.
