# 리서치 공개 API 0.1

공개 경로는 `rag_research_agent.research.api`다. `research/__init__.py`에서 공개 이름을 지연 집계하고 `research/api.py`는 같은 패키지의 이름만 가져온다.
`tests/test_structure.py`는 패키지 집계 파일을 모듈 간 import 검사에서 제외한다. 실행 구현은 기존 rag·guard·store에 둔다.
구현은 기존 위치에 유지하며 `API_VERSION = "0.1"`을 제공한다.

공개 이름: `run_research`, `ResearchConfig`, `ResearchResult`, `DomainFilter`,
`register`, `get_filter`, `SearchFn`, `keyword_search`, `chroma_search`.
`chroma_search`는 기존 `make_chroma_search`와 같은 함수다.

`run_research(question, *, search, config=None, checklist=(), domain="research")`
는 기존 `ResearchResult`를 반환한다. config 생략 시 기존 ResearchConfig 기본값을 그대로 쓴다.
기본 research는 기존 주장 단위 검수·재검색 루프에 그대로 위임한다.
다른 등록 도메인은 검색 전 check_input, 그래프 실행 후 verify, 통과 후 finalize를 적용한다.
입력 차단 시 stopped는 BLOCKED, 도메인 검수 실패 시 VERIFY_FAILED이며 안전 문구를 반환한다.
도메인 검수는 한 번이며 추가 재시도는 없다. 성공 시 report에는 finalize의 고지가 붙고
draft는 그래프의 인용 문장 그대로 남는다. verify_codes가 남으면 검수 통과로 취급하지 않는다.

파사드 모듈·도메인 계약만 import할 때 LangChain/LangGraph는 필요 없다.
ResearchConfig·ResearchResult·SearchFn·검색 함수는 기존 구현을 지연 re-export하므로
그 이름을 가져오거나 실행하려면 기존 그래프의 LangGraph 의존성이 필요하다.
Chroma 예제는 chromadb가 필요하다. 파사드는 설치·모델 로딩을 수행하지 않는다.
아래 세 블록은 각각 독립 실행할 수 있고 시험에서 그대로 실행한다.

## 예제 1: 키워드 검색

```python
from rag_research_agent.research.api import (
    API_VERSION, ResearchConfig, ResearchResult, keyword_search, run_research,
)

corpus = {"doc-a1": "주택 거래량은 18% 감소했다."}
result = run_research(
    "주택 거래량을 정리해 주세요.", search=keyword_search(corpus),
    config=ResearchConfig(k=1, stance_split=False, auto_metrics=False),
    checklist=("주택 거래량",),
)
assert API_VERSION == "0.1"
assert isinstance(result, ResearchResult)
assert result.verify_codes == () and "18%" in result.report
```

## 예제 2: 로컬 Chroma (합성 임베딩 경로 시험)

다른 프로젝트에서는 이미 연 ChromaIndex와 같은 차원의 임베더를 주입하면 된다.
이 독립 예제는 기존 FakeEmbedder로 실제 Chroma 저장·검색·그래프 경로만 검사한다.
실제 모델의 검색 품질을 나타내지 않는다. 결과는 `.runs/`에만 생성한다.

```python
from pathlib import Path
from uuid import uuid4
from rag_research_agent.core.contracts import Chunk
from rag_research_agent.embed.providers import FakeEmbedder
from rag_research_agent.store.chroma_store import publish_chroma
from rag_research_agent.research.api import ResearchConfig, chroma_search, run_research

text = "주택 거래량은 18% 감소했다."
embedder = FakeEmbedder(dimension=64)
chunk = Chunk("doc-a1", "chunk-a1", "v1", "synthetic", "Synthetic", text,
              embedder.count_tokens(text), "ck1", "m1", "p1")
index = publish_chroma(
    [chunk], embedder.encode_documents([text]),
    path=Path(".runs/r19/examples") / uuid4().hex,
    collection="research-api", dimension=embedder.dimension,
)
try:
    result = run_research(
        "주택 거래량을 정리해 주세요.", search=chroma_search(index, embedder),
        config=ResearchConfig(k=1, stance_split=False, auto_metrics=False),
        checklist=("주택 거래량",),
    )
    assert result.verify_codes == () and "18%" in result.report
    assert result.sources[0].source_id == "chunk-a1"
finally:
    index.close()
```

## 예제 3: 도메인 교체

기존 LegalFilter를 명시적으로 import하여 공유 레지스트리에 등록한다.
새 도메인은 `register("새이름", 실제필터팩토리)`로 등록할 수 있다.

```python
from rag_research_agent.guard.legal_filter import LegalFilter
from rag_research_agent.research.api import (
    DomainFilter, ResearchConfig, get_filter, keyword_search, run_research,
)

assert isinstance(get_filter("legal"), DomainFilter)
assert isinstance(get_filter("legal"), LegalFilter)
result = run_research(
    "계약 손해배상 비율을 정리해 주세요.",
    search=keyword_search({"doc-b1": "계약 손해배상 비율은 18%이다."}),
    config=ResearchConfig(k=1, stance_split=False, auto_metrics=False),
    checklist=("계약 손해배상 비율",), domain="legal",
)
assert result.verify_codes == ()
assert "18%" in result.report and "법률 자문이 아닙니다" in result.report
assert result.path[0] == "screen" and result.path[-1] == "finalize"
```

질문·체크리스트·검색 문서는 호출자가 미리 마스킹해야 한다. Chroma 어댑터에는 기존
masker 옵션을 전달할 수 있다. 인덱스의 수명도 호출자가 관리한다.
LLM 추출·계획, 계획 검토·체크포인터는 모델·세션 인자가 필요한 기존 ResearchRunner를 사용한다.
이 파사드는 그 인자를 추가하지 않는다. 별도 패키지 배포와 도메인별 그래프 내부 재시도는 후속 연결 필요다.
