# Diagrams / 다이어그램

Every diagram exists in Korean (`NAME.png`, `NAME.mmd`) and English (`NAME.en.png`, `NAME.en.mmd`). The English README uses the `.en` files, the Korean README uses the plain ones. Rendered with Mermaid CLI in the house dark style (`mermaid-config.json`).

한글판은 `NAME.png`, 영문판은 `NAME.en.png`입니다. 영문 README는 `.en`, 한글 README는 기본 파일을 씁니다.

| # | Diagram | 다이어그램 |
| --- | --- | --- |
| 01 | Architecture overview | 전체 구조 |
| 02 | Full LangGraph flow | LangGraph 전체 흐름 |
| 02a | Graph, search half | 그래프 앞부분 (검색) |
| 02b | Graph, Token Diet half | 그래프 뒷부분 (Token Diet) |
| 03 | Two knobs and presets | 노브 2개와 프리셋 |
| 04 | Hybrid retrieval and edge scoring | 하이브리드 검색과 엣지 점수 |
| 05 | Repository split | 저장소 분리 |
| 06 | Concept map | 개념 지도 |
| 07 | Open-source model combination | 오픈소스 모델 결합 |
| 08 | Use cases | 활용 지도 |

Re-render: `mmdc -i NAME.en.mmd -o NAME.en.png -c mermaid-config.json -p puppeteer.json -b "#111820" -s 2`
