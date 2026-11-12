# langgraph-research-kit 분리 계획

작성일: 2026-11-12 KST. R34는 문서 작업이며 아래 이동·인터페이스는 **제안**이다. 이번 작업에서는 코드·시험·패키징을 변경하지 않는다. 현재 구현 사실은 명시한 파일에서 확인했고, 분리 후 실행 가능성은 미검증이다.

## 1. 범위와 현재 경계

설계 정본은 [리서치 그래프](RESEARCH_GRAPH_DESIGN.ko.md), [도메인 필터](DOMAIN_FILTERS.ko.md), [가드레일](LANGGRAPH_GUARDRAIL.ko.md)이다. 리서치 그래프, 필터, 외곽 가드레일, 평가·보드를 키트로 옮기되 저장소·모델·서비스 수명주기는 호출자가 소유하도록 제안한다. 개발 연결은 Chroma 기준이며 memvid 코드·시험은 원 저장소에 보존한다.

현재 `rag/research_graph.py`의 `SearchFn`은 `(query, k) -> list[(source_id, masked_text)]`이다. `build_research_graph`에는 planner/extractor/writer/verifier/refiner 콜백과 모델·masker·checkpointer 주입점이 있다. `ResearchRunner` 생성자는 모델·masker·checkpointer를 받지만 위 다섯 콜백을 직접 받지는 않는다. 공개 파사드 `research/__init__.py`는 `API_VERSION="0.1"`과 지연 export를 제공한다. 따라서 새 경계를 처음부터 발명하기보다 이 계약을 이관하는 순서가 적합하다.

## 2. 파일별 import 그래프와 이동안

아래 경로는 별도 표기가 없으면 `src/rag_research_agent/` 기준이다. 표는 기존 패키지에 대한 의존을 열거한다. 표준 라이브러리는 생략하고 외부 패키지는 별도로 적었다. 함수 내부·TYPE_CHECKING·문자열 지연 import도 포함한다. 정적 인벤토리는 `.runs/r34/imports.json`에 남겼다.

| 현재 파일 | 기존 패키지 의존 | 제안 목적지·처리 |
| --- | --- | --- |
| `core/research.py` | 없음; dataclass·typing만 사용 | `core/research.py`로 이동. Claim, Metric, Relation, SourceRef, ResearchPlan, Draft, ReportSentence, span_matches의 정체성 보존 |
| `research/__init__.py` | `core.research`; 지연 `rag.research_graph`, `guard.domain_filter`, `rag.research_chroma` | 키트 `__init__.py`·`api.py`로 공개 API 분리. Chroma export는 원 저장소 어댑터 경유 |
| `research/api.py` | `research`의 API_VERSION, __all__, run_research, __getattr__ | 기존 경로의 호환 파사드는 원 저장소에 유지; 키트 API를 재노출 |
| `rag/research_graph.py` | `core.research`, `guard.research_filter`, `observe.tracing`; 함수 내부 `rag.research_llm` | `rag/research_graph.py`; tracing 경계 추출 필요. LangGraph 사용 |
| `rag/research_llm.py` | `core.research`, `observe.tracing`, `rag.research_graph`의 규칙 함수 | `rag/research_llm.py`; tracing 분리. Pydantic 사용. graph의 지연 import 순서 보존 |
| `rag/research_export.py` | `core.research.span_matches`; TYPE_CHECKING의 `rag.research_graph.ResearchResult` | `rag/research_export.py`; 출처·인용·HTML 이스케이프 동작 보존 |
| `guard/domain_filter.py` | 정적 패키지 import 없음; BUILTINS의 `rag_research_agent.guard.research_filter` 문자열을 importlib로 로드 | `guard/domain_filter.py`; 문자열 경로도 키트로 변경 |
| `guard/research_filter.py` | `core.research`, `guard.domain_filter` | 동일 상대 경로로 이동. 텍스트 검수와 claim 검수 구분 유지 |
| `guard/legal_filter.py` | `guard.domain_filter` | 동일 상대 경로로 이동 후보; import 시 register·BUILTINS 갱신 보존 |
| `guard/medical_filter.py` | `guard.domain_filter` | 동일 상대 경로로 이동 후보; 순수 규칙 필터로 한정 |
| `guard/local_admin_filter.py` | `guard.domain_filter` | 동일 상대 경로로 이동 후보; 호출자 관할 매핑 주입 유지 |
| `rag/guardrail_graph.py` | `core.contracts.RetrievalUnavailable`, `core.types.Status`, `observe.tracing`, `rag.execution.InferenceCapacityExceeded/InferenceTimeout`, `guard.domain_filter`, `rag.guidance.GuidanceReply` | 키트 `rag/guardrail_graph.py`로 제어 흐름만 이동; 응답·실행·관찰 의존 제거 후 이관 |
| `rag/research_guardrail.py` | `core.types.Status`, `guard.domain_filter`, `rag.answer.EvidenceStatus`, `rag.guidance.GuidanceReply`, `rag.guardrail_graph`, `rag.research_graph` | 현재 Guidance 변환·상속은 원 저장소 유지. 범용 ResearchResult→키트 응답 변환만 후속 분리 |
| `rag/research_chroma.py` | `core.contracts.RetrievalMode`, `embed.providers.Embedder/EmbeddingError`, `guard.protocols.Masker`, `rag.research_graph.SearchFn`, `retrieve.gate.RelevanceRule/to_result`, `store.chroma_store.ChromaIndex` | 원 저장소에 유지. 키트 SearchFn 제공자로 연결; store/embed/retrieve 전체를 키트로 끌어오지 않음 |
| `scripts/research_eval.py` | `core.research.NO_COUNTER_EVIDENCE`, `observe.gate_grid.wilson`, `rag.research_graph`; 함수 내부 `research_board.render` | 키트 `eval/research_eval.py`; CLI·입출력 경로 분리 |
| `scripts/research_grid.py` | `scripts.research_eval`, 함수 내부 `scripts.research_board` | `eval/research_grid.py`; compare 전용 조합 평가 보존 |
| `scripts/research_board.py` | 기존 패키지 import 없음 | `eval/research_board.py`; 파일 기반 기본 문항·grid 조회를 명시적 입력으로 분리 |
| `scripts/research_graph_diagram.py` | `rag.research_graph` | `rag/diagram.py` 및 얇은 CLI. 기본 문서 출력 위치는 호출자 지정으로 변경 제안 |
| `scripts/domain_eval.py` | `observe.gate_grid.wilson`; 함수 내부 `rag.research_graph` | `eval/domain_eval.py`; domain pack과 research pack의 경로 분리 |
| `scripts/domain_board.py` | `scripts.domain_eval.load_pack/validate_metrics` | `eval/domain_board.py`; 팩·실행 이력·출력 루트 주입 |
| `observe/gate_grid.py`의 `wilson` | 표준 라이브러리 math; 함수 자체는 다른 패키지 의존 없음 | 함수만 키트 `eval/statistics.py`로 분리하고 원 저장소 재노출. sweep/rates 등 검색 게이트 보정 로직은 잔류 |

새 디렉터리의 `__init__.py`, 패키지 메타데이터·라이선스·배포 설정은 후속 작성 대상이다. 기존 모듈 전체를 복사한다는 의미가 아니다. 특히 `core/contracts.py`, `core/types.py`, `rag/guidance.py`, `rag/execution.py`, `rag/answer.py`, `observe/tracing.py`는 키트 이동 대상이 아니다.

## 3. 끊어야 할 의존과 대체 계약 제안

| 연결 | 코드에서 확인한 사용 | 대체 인터페이스 제안·검증 조건 |
| --- | --- | --- |
| GuidanceReply·Status | 가드레일이 상태·답변·호출 수를 읽고, 차단·검수 실패·smalltalk 응답을 직접 생성/교체 | 키트 `core`에 불변 Reply와 자체 상태 값, `answer`, `reason_code`, `retrieval_calls`, `generation_calls` 계약을 둔다. 원 저장소 `rag` 어댑터가 GuidanceReply↔Reply와 citation/model/evidence 메타데이터를 손실 없이 왕복시킨다. 읽기 Protocol만으로는 응답 생성·교체 요구를 충족하지 못함 |
| RAG 호출 결과 | `RagCall` 주석은 응답 하나이나 노드는 `(reply, evidence)`도 수용 | `core`에 명시적 RagOutcome(reply, evidence_texts) 제안. 기존 단일 응답은 어댑터에서 빈 근거로 정규화; 근거 없음의 검수 종료 동작 유지 |
| execution·검색 예외 | 가드레일 TRANSIENT에는 검색 불가·용량 부족·시간 초과가 있고, 나머지는 오류 종료 | 키트 ErrorInfo(code, retryable)와 예외 분류 콜백 제안. 원 저장소가 실제 예외를 분류하고 HTTP 매핑용 원 예외는 로컬 어댑터에서 보존. 메시지 문자열은 로그·직렬화로 전달하지 않음. 알려지지 않은 예외를 재시도하지 않는 기본값 유지 |
| observe.tracing | 연구 실행·resume·LLM·가드레일이 serving_trace_guard/serving_config 사용 | 키트 `core`에 실행 context factory와 config provider 계약, 구현은 `rag`에 둔다. 원 저장소는 기존 함수를 주입. 독립 기본 구현도 원격 tracing 차단을 수행하고 모델 호출·stream·resume·병렬 분기를 모두 감싸야 한다. 빈 context 대체는 승인 기준 미충족 |
| masking | LLM 함수는 주입 masker를 요구; Chroma 어댑터는 masker 옵션, 호출자 마스킹 전제 존재 | 동결 `guard/masking.py`는 잔류. 키트 core에 최소 `mask(text)->str` 계약을 제안하고 실제 호출 형식은 어댑터로 정규화. 질문·검색 본문·checklist의 마스킹 책임과 span의 기준 텍스트를 문서화 |
| Chroma | make_chroma_search가 인덱스·임베더·근거 게이트를 SearchFn으로 감쌈 | 현 어댑터를 원 저장소에서 키트 SearchFn에 연결. 인덱스 생명주기·차원·오류·근거 게이트를 원 저장소가 소유. 키트에서 모델 자동 로딩·fake 폴백 금지 |
| 스크립트 경로 | ROOT/sys.path 조작, evals·.runs 경로, git_sha의 subprocess, render의 기본 파일 조회 | 데이터셋·grid·runs·revision을 함수 인자로 전달. 원 저장소 얇은 CLI가 기존 기본 경로와 명령을 유지. 키트 결과 저장은 호출자 `.runs/` 아래로 제한 |

`guard/domain_filter.py`의 계약은 변경 없이 우선 이동한다. 추가 도메인은 현재 자기 모듈 import 때 등록·BUILTINS를 갱신한다. research만 최초 BUILTINS에 있으므로 법률·의료·행정의 자동 발견을 이미 완성된 기능으로 취급하지 않는다. 등록 레지스트리는 하나만 유지하고 중복 import·register 실패를 검사한다.

## 4. 새 패키지와 원 저장소 연결

제안 저장소·배포명은 `langgraph-research-kit`, Python import명은 `langgraph_research_kit`이다. 이름의 외부 가용성·배포 권한은 미검증이며 이번 작업에서는 조회·발행하지 않는다.

```text
langgraph-research-kit/
  pyproject.toml
  src/langgraph_research_kit/
    __init__.py, api.py
    core/research.py, contracts.py
    guard/domain_filter.py, research_filter.py
    guard/legal_filter.py, medical_filter.py, local_admin_filter.py
    rag/research_graph.py, research_llm.py, research_export.py
    rag/guardrail_graph.py, runtime.py, diagram.py
    eval/research_eval.py, research_grid.py, research_board.py
    eval/domain_eval.py, domain_board.py, statistics.py
  tests/
  evals/research/, evals/domains/
```

위 구조의 새 파일명 `contracts.py`, `runtime.py`, `statistics.py`는 제안이며 현재 존재하는 키트 구현이 아니다. Python 하한은 현재 원 패키지의 `>=3.12`를 출발점으로 한다. core·필터는 표준 라이브러리만으로 import되게 유지하고 그래프용 LangGraph, 구조화 모델용 Pydantic은 선택 의존성 그룹으로 제안한다. 현 원 저장소의 `langchain` extra는 langchain-core와 langgraph를 함께 선언한다. 새 최소 버전·호환 범위는 실제 시험 후 결정하며 추측한 버전 번호를 고정하지 않는다.

원 저장소는 검증한 키트 버전을 의존성으로 고정하고 기존 `research.api`와 `rag`의 호환 경로를 재노출한다. 클래스 복제 대신 같은 객체를 재노출해 isinstance·dataclass 비교·레지스트리 정체성을 보존한다. `rag/research_chroma.py`, Guidance 변환, HTTP 매핑, 실행 worker, 마스킹·정책은 원 저장소 `rag` 조립 계층에 남긴다. 비-rag 모듈이 서로 직접 연결되는 새 의존은 만들지 않고 공유 계약은 core를 경유한다. LangChain·LangGraph import는 키트에서도 rag에만 두고 MATURITY를 유지한다. `KNOWN_DEBT` 확대는 금지한다.

## 5. 시험 이동 목록

모든 경로는 `tests/` 기준이다. 아래는 **후속 이동 계획**이며 이번에 기존 시험·기대값·skip은 수정하지 않는다. 원 저장소에서 제거하기 전에 키트에서 동등 시험이 실행되고 원 저장소 호환 시험이 통과해야 한다.

| 파일 목록 | 이동·잔류 조건 |
| --- | --- |
| `test_research_graph.py`, `test_research_claim_verify.py`, `test_research_parallel.py`, `test_research_parallel_extract.py`, `test_research_noise.py`, `test_research_loop_policy.py`, `test_research_checkpoint.py`, `test_research_plugins.py` | 키트 그래프 시험으로 이동 후보. tracing 관련 검증은 키트 차단 구현과 원 저장소 주입 연결 양쪽에 보존 |
| `test_research_llm_extract.py`, `test_research_llm_plan.py`, `test_research_llm_writer.py` | 실제 키트 그래프·구조화 출력 클래스를 유지하고 모델만 주입하는 경로 시험. 기존 mask_pii 연결 시험은 원 저장소에도 보존 |
| `test_domain_filter.py`, `test_legal_filter.py`, `test_medical_filter.py`, `test_local_admin_filter.py` | 키트 필터 시험 후보. `test_domain_filter.py`의 GuidanceReply·GuardrailRunner 연결 부분은 원 저장소 통합 시험으로 잔류 |
| `test_research_export.py`, `test_research_diagram.py` | 키트 렌더링·그래프 시험 후보. 원 저장소 docs 출력 위치·CLI 기본값 검증은 잔류 |
| `test_research_and_eval.py`, `test_research_board.py`, `test_research_grid.py`, `test_research_eval_cases_option.py`, `test_research_cases_v2.py`, `test_domain_eval.py`, `test_domain_board.py`, `test_medical_eval_pack.py` | 키트 평가·보드 시험 후보. evals 파일·ROOT·CLI·Node 의존을 각각 확인하고 키트 리소스와 원 저장소 기본 경로 검증으로 분리 |
| `test_research_public_api.py` | 기존 API 정체성·문서·지연 import 검증은 원 저장소 유지; 키트 자체 공개 계약 검증은 새 시험으로 추가 |
| `test_guardrail_graph.py`, `test_research_guardrail.py` | 범용 경로·한도·재시도 시험은 키트 후보; GuidanceReply·HTTP·실행 예외·실제 GuidancePipeline 연동은 원 저장소 유지. 전자는 `test_guidance_bridge`의 fixture도 참조하므로 통째 이동 불가 |
| `test_research_chroma.py` | 원 저장소 유지. 실제 ChromaIndex·근거 게이트·FakeEmbedder를 쓰는 경로 시험; 실제 임베딩 품질 증거로 취급 금지 |
| `test_structure.py` | 원 저장소 구조 규칙 유지; 키트에도 MATURITY·core 순수성·모듈 경계·선택 의존성 차단 시험을 별도 마련 |

문항 리소스 후보는 `evals/research/cases.ko.json`, `cases_v2.ko.json`, `knobs.json`, `evals/domains/legal/{cases,metrics}.json`, `evals/domains/medical/{cases,metrics}.json`이다. 이들 경로의 존재를 확인했다. `domain_eval.research_pack`은 research 문항을 변환하므로 별도 research domain 폴더가 있다고 가정하지 않는다. `data/**`, `profiles/**`는 이동 대상에서 제외한다. fixture·문항 복사 전 개인정보 점검이 필요하며 이번 문서에 개인정보 예시 값은 추가하지 않는다.

## 6. 단계·위험·완료 기준

| 순서 | 후속 작업 | 위험과 완료 기준 |
| --- | --- | --- |
| A | 현재 API·설정·로그·JSONL·기본 경로를 계약 목록으로 고정 | 품질 결과와 경로 시험 혼동 방지. 기존 전체 시험과 보호 해시 기준 확보 후 시작 |
| B | core 연구 타입·필터를 키트로 이동하고 기존 경로 재노출 | 타입·레지스트리 중복 및 지연 등록 순서 위험. 같은 객체·중복 등록 동작·선택 패키지 없이 import 검증 |
| C | runtime·응답·오류 계약을 만들고 가드레일·연구 그래프 이관 | tracing 누출, 재시도/HTTP 의미 변경 위험. 실제 그래프에서 업로드 차단·한도·안전 응답·예외 분류 검증. checkpoint 직렬화의 이전 모듈 경로 호환은 미검증이므로 별도 이관 시험 필요 |
| D | 원 저장소 Chroma·Guidance·HTTP 어댑터를 연결 | 인용 메타데이터·마스킹·게이트 누락 위험. 실제 기존 클래스 경로 시험, 실패·중단 초안 노출 방지 검증. 체크포인트 검토 세션은 현재 ResearchGuardrailAdapter가 거부하므로 후속 연결 필요 |
| E | 평가·보드 함수와 리소스를 이관하고 기존 CLI를 얇게 유지 | dataset version/hash·gold 연결·HTML 이스케이프·출력 위치 회귀 위험. 기존 기록 렌더링·명시 문항 파일·compare 선택·confirm 단일 설정 검증 |
| F | 설치된 키트만 있는 격리 환경에서 시험 후 원 저장소 의존성 고정 | 소스 경로·미포함 리소스·암묵 의존 위험. 네트워크 없이 wheel 설치/리소스 로드·기존 API 호환·전체 회귀 시험 통과 후 배포 검토 |

각 단계는 구현→docs 보고→전체 시험→한 작업 한 커밋으로 진행하며 NightCoder에서는 push하지 않는다. 이번 R34는 A 이전의 계획서만 작성한다. 실제 후속 소스 변경은 별도 허용 범위와 작업 지시가 필요하다.

## 7. 설계와 실제 구현의 차이·미검증

설계의 classify/screen/finish/kill 전체 흐름은 연구 그래프 하나에 모두 있지 않다. 연구 그래프는 plan부터 시작하고 종료는 END이며 외곽 GuardrailRunner가 분류·스크리닝·RAG 호출을 감싼다. 기본 검색은 한 retrieve 노드가 관점별 순차 검색을 하며 `parallel_branches`로 분리 노드를 켠다. 이를 분리 작업 중 하나의 새 그래프로 합치지 않는다.

설계의 원문 대신 위치만 보유한다는 설명과 달리 현재 SourceRef에는 text, Claim에는 text·span이 있고 모델 경로와 검색 경로는 마스킹된 텍스트를 전제로 한다. Metric은 자체 span 필드 없이 claim_id로 Claim을 참조한다. Relation.kind도 현재 causes/contradicts/condition으로 한정된다. 온톨로지 전체·독립 Entity 상태·compose.numbers 재사용이 구현되어 있다고 주장하지 않는다. 현 `extract_rule`은 자체 규칙이다. `verify_report`와 텍스트 DomainFilter.verify는 서로 다른 입력 계약이며 파사드의 비-research 도메인은 외곽 입력 검사·최종 검수만 추가한다. 도메인별 전문 DB 강제·분기 격리·의료/법률 품질은 키트 분리만으로 완성되지 않는다.

규칙 planner/extractor/writer, 병렬·검토 옵션 꺼짐 등 현재 기본 설정을 유지한다. 선택은 compare만 사용하고 confirm은 선택된 한 설정에 한 번 적용한다. 비율에는 표본 수와 Wilson 95% 구간을 붙이고 injection은 검색 품질 분모에서 제외한다. 이번에는 평가·설정 선택·실제 모델 실행을 하지 않았으며 실성능·독립 설치·배포·checkpoint 이전 호환은 미검증이다. memvid 전용 버전 발행·롤백·해시 manifest 기능은 **Chroma 경로에 없음**으로 기록하고 키트에서 임의 대체하지 않는다.
