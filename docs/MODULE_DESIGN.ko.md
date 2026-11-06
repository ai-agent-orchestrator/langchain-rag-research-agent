# 모듈 설계안 v0.2 — 법률 검색·리서치에서 재사용하는 RAG·보안 백엔드 모듈

2026-11-06 · **설계 단계, 대표 확정 전.** `main`에는 M0 패키지 뼈대(PR #4, 합성 자료와 가짜 모델 시험만)가 있고, 긴 프롬프트 브리프·골든셋 비교 실험 코드는 Draft PR #5에 참고용으로 둡니다. 실모델 검증은 아직 하지 않았습니다.

③는 두 가지 일을 합니다. 하나는 ①에서 검증한 구현·계약·시험을 **정리**하는 일이고, 다른 하나는 LangChain·LangGraph·LangSmith·임베딩·유사도 검색·보안을 ①보다 **넓게 실험**해 법률 검색과 리서치 오케스트레이터가 가져다 쓰는 **실용 백엔드 모듈**로 만드는 일입니다. 이 문서는 그 순서와 계약, 평가·보안 기준, 완료 조건을 정합니다.

---

## 0. 저장소 역할

| | ① legal-intake-fastapi-lab | ③ python-memvid-guardrail |
| --- | --- | --- |
| 목적 | 상담 안내 API 하나에서 보안·검색·생성·마케팅을 **최소 범위로 검증** | ①의 구현·계약·시험을 **정리** + **확장 실험** + **재사용 모듈** |
| LangChain·LangGraph·LangSmith·RAG | 필수 범위의 기본 사용(3 node, 합성 평가) | 같은 부품을 모듈로 묶고 하이브리드·리랭킹·질의 재작성·의미 기반 가드·긴 프롬프트 브리프까지 실험 |
| 데이터 | 합성 안내문 10개 | 컬렉션 여러 개(안내문, 합성 조문, 리서치 카드, 합성 장문 프롬프트) |
| 결과물 | 동작하는 FastAPI 앱 | 설치 가능한 패키지 + 실험 보고서 + 골든셋 |

README 저장소 순서 문구(반영안):

| 순서 | 역할 |
| --- | --- |
| ① legal-intake-fastapi-lab | FastAPI 단독에서 보안·검색·생성·마케팅 기능을 최소 범위로 검증 |
| ③ python-memvid-guardrail | ①에서 검증한 구현·계약·시험을 정리하고, LangChain·LangSmith·보안·RAG·유사도 검색을 더 넓게 실험해 법률 검색·리서치에서 쓰는 재사용 백엔드 모듈로 개발 |
| ② spring-fastapi-async-refactor | Spring 인증·인가와 FastAPI AI 서비스 연결 |
| 이후 | 검증한 기능을 기반으로 별도 비공개 상업화 개발 |

## 0-1. 설계 원칙

1. **세 단계.** `stable`(실모델 증거 있음) · `incubating`(①에서 옮겨 왔지만 ① 증거 대기) · `lab`(③ 실험). 모듈마다 `MATURITY` 상수로 밝히고, 시험이 단계 규칙을 검사합니다.
2. **실험은 격리.** stable·incubating 코드는 `lab`을 import하지 않습니다.
3. **프레임워크는 선택.** core는 표준 라이브러리만 쓰고, memvid·E5·LangChain·LangGraph·LangSmith·NeMo·FastAPI는 추가 설치(extras)로 둡니다.
4. **유사도는 후보, 확정은 게이트.** 검색·필터·라우팅은 후보를 내고, 정책·시험·사람이 결정합니다.
5. **외부 전송 0이 기본값.** 텔레메트리, 외부 임베딩, 원격 tracing은 모두 기본 OFF이며, 켤 때는 코드에서 명시합니다.
6. **복사 금지.** 검증된 부품은 ③으로 옮기고 ①과 리서치는 ③을 의존성으로 씁니다.
7. **증거로 승격.** 단계를 올릴 때마다 `docs/evidence/`에 결과 파일을 남깁니다.

---

## 1. 사용 시나리오

### S1. Legal Intake 상담 안내 근거 검색 (①이 사용)

| 항목 | 내용 |
| --- | --- |
| 호출자 | ① `POST /api/intakes/{id}/guidance` 서비스 |
| 입력 | 필드별 검사·마스킹된 질의(`caseType + coreStatement + desiredNextStep`), 컬렉션 `synthetic-guides-v1` |
| 출력 | `RetrievalResult(OK / EMPTY / BELOW_THRESHOLD)` + 출처 청크 → 구조화 초안 → 서버가 조립한 `answer` |
| 성공 기준 | 근거 질문 Hit@3를 개수로 보고, 무근거 질문은 생성 0회, 인용 ID는 검색 결과의 부분집합, 외부 전송 0 |
| 하지 않음 | 접수 원문·후기를 공식 근거에 섞기, 승소·기한·금액 단정 |
| 부품 | core · guard · embed · store · retrieve(게이트) · rag · observe |

### S2. 법률 검색 (시범)

| 항목 | 내용 |
| --- | --- |
| 호출자 | 상담 준비 화면·내부 도구(이후 ② 경유) |
| 입력 | 자연어 질문, 컬렉션(합성 조문·안내 자료·공개 자료 시범) |
| 출력 | 조문·자료 상위 k개(ID·제목·버전·발췌), 무근거 판정, 키워드/벡터/혼합 방식 표시 |
| 성공 기준 | 골든셋 1위 정답·3위 안 정답 수(개수), 무근거 혼동표, 질문 1건 지연 상한 |
| 하지 않음 | 법률 판단 생성, 출처 없는 요약, 실제 사건 자료 적재 |
| 부품 | core · embed · store · retrieve(키워드+벡터, 게이트) · observe(골든셋) |

### S3. 리서치 오케스트레이터 — 긴 프롬프트 브리프

| 항목 | 내용 |
| --- | --- |
| 호출자 | 리서치 멀티 에이전트(로컬 Llama 요약 전 단계), Legal Intake의 긴 지시문 요약 |
| 입력 | DB에 저장된 40쪽 이상 프롬프트(결정 기록·회의록·명세), 다음 작업 설명, 글자 예산 |
| 출력 | 작업용 추출 브리프(원문 문장만, 원래 순서), 제외된 주입 구간 목록, 폐기안 포함 여부, (선택) 원문 검사를 통과한 요약 |
| 성공 기준 | 심어 둔 결정·제약 회수율, 주입·개인정보 누출 0, 폐기안이 현재 결정보다 앞서지 않음, 예산 이하 |
| 하지 않음 | 원문을 외부로 보내기, 요약이 새 숫자·ID를 만드는 것 |
| 부품 | guard · embed · retrieve · lab/briefing |

### S4. 리서치 피드 필터·오케스트레이터 맥락 고르기

| 항목 | 내용 |
| --- | --- |
| 호출자 | 리서치 DP-14 필터, 명세를 쓰는 CTO 에이전트 |
| 입력 | 마스킹된 피드 항목 또는 과거 결정·실패·REPORT 기록 |
| 출력 | 중복 묶음(대표 1개 + 나머지 목록), 분야 표시, 새로움 표시, 관련 맥락 상위 k개 |
| 성공 기준 | 잘못된 병합 0에 가깝게(정밀도 우선), 줄어든 요약 호출 수, 그림자 1주 비교 |
| 하지 않음 | 항목 삭제, S 등급 강등, 맥락 고르기로 결정을 자동 확정 |
| 부품 | embed · store(NumPy) · retrieve(중복·MMR·새로움) |

---

## 2. 모듈 구조와 인터페이스

### 2-1. 패키지 구조

```text
src/memvid_guardrail/
  core/      contracts.py   Chunk, Evidence, RetrievalResult, IndexManifest, 상태·오류 코드 (의존성 없음)
  guard/     masking.py · input_policy.py · semantic_signal(lab) · context.py · risk.py · network.py
  embed/     providers.py   Embedder 규약, E5 · Ollama · 가짜
  ingest/    chunking.py    제목 보존 분할(토큰 계수기 주입) · loaders.py
  store/     memvid_store.py · flat_store.py(NumPy)
  retrieve/  keyword.py · gate.py · diversity.py(중복·MMR·새로움)
  rag/       answer.py · chain.py · graph.py
  observe/   tracing.py · evaluate.py · golden.py
  adapters/  fastapi.py · cli.py  (선택)
  lab/       hybrid.py · semantic_guard.py · briefing/ · query_rewrite.py · rerank.py
data/        golden_set.json · articles.json (합성)
docs/        설계·증거
```

### 2-2. 공개 인터페이스 (계약)

| 모듈 | 함수·타입 | 입력 → 출력 | 실패 시 | 계약 |
| --- | --- | --- | --- | --- |
| embed | `Embedder.encode_documents(texts)` | 문자열 목록 → 정규화 벡터 목록 | `EmbeddingError` | 차원·유한값·L2 정규화 검사, 512토큰 초과 거절 |
| embed | `Embedder.encode_query(text)` | 문자열 → 벡터 | 같음 | 모델 규약(E5는 지시문 접두)을 내부에서 적용 |
| embed | `Embedder.identity()` | → `(model, revision, dimension, normalization)` | — | 색인·질의의 일치 확인에 사용 |
| ingest | `build_chunks(docs, count_tokens, …)` | 문서 + 토큰 계수기 → `Chunk[]` | `ValueError`(예산 초과) | 같은 입력이면 같은 chunkId·해시(멱등) |
| store | `publish(chunks, vectors, version, identity)` | → `IndexManifest` | `RetrievalUnavailable` | 8개 이하 묶음, seal 후 전수 검증 통과 시에만 포인터 교체 |
| store | `open_active(identity)` | → `Index` | `RetrievalUnavailable` | 포인터·manifest·파일 해시·identity가 모두 일치해야 열림 |
| store | `Index.search_vector(vec, k)` / `search_lex(text, k)` | → `(Chunk, score, rank)[]` | `RetrievalUnavailable` | 출처는 manifest에서 찾고, memvid 메타데이터는 쓰지 않음 |
| retrieve | `gate(hits, rule)` | → `RetrievalResult` | — | top-k가 있다는 이유만으로 OK를 주지 않음. 규칙 버전 기록 |
| retrieve | `group_duplicates` · `mmr_select` · `is_novel` | 벡터 → 묶음·선택·판정 | — | 지우지 않음, 보호 항목 유지, 애매하면 통과 |
| guard | `mask(text)` | → `(safe_text, matched_types)` | 마스킹 실패 시 원문 대신 중단 | 저장·임베딩·trace·출력 전에 적용 |
| guard | `check_input(text, profile)` | → `Decision(ALLOW/BLOCK/REVIEW)` | `SecurityError` | 정규식은 확정 차단, 의미 신호는 REVIEW까지만 |
| rag | `build_chain(model)` | → Runnable(intake, evidence → `GuidanceDraft`) | `DraftRejected` | 1회 생성, JSON + Pydantic, 근거는 데이터 블록 |
| rag | `build_graph(retrieve, generate)` | → 컴파일된 그래프 | 검색 장애는 그대로 올림 | 무근거 시 생성 0회, 요청별 상태 |
| rag | `assemble_answer(draft, evidence, check)` | → 문자열 | `DraftRejected` | 필드별 검사 후 서버가 조립, 출처는 서버 기록에서 |
| observe | `serving_trace_guard()` | 컨텍스트 | — | 환경변수가 켜져 있어도 업로드 0 |
| observe | `golden.compare(embedders, golden, corpus)` | → 보고서 | `ValueError`(형식) | 1위·3위 안·MRR·갈린 질문 |
| lab | `build_brief(text, task, budget, strategy)` | → `Brief` | `ValueError` | 추출식, 주입 구간 제외, 폐기안 뒤로 |

### 2-3. 공통 규칙

- **버전 필드:** `chunker_version`, `masking_version`, `policy_version`, `index_version`, `prompt_version`, `rule_version`, `golden_version`. 결과 파일에는 반드시 기록합니다.
- **오류 코드:** `RETRIEVAL_UNAVAILABLE`(503), `AI_DRAFT_REJECTED`, `REQUEST_CONTEXT_MISMATCH`(500), `GUARDRAIL_UNAVAILABLE`(503). 정책 차단과 기술 오류를 섞지 않습니다.
- **패키지 버전:** `0.x` 동안에는 계약이 바뀔 수 있습니다. 바꿀 때는 변경 기록과 함께 한 단계 이전 계약을 유지합니다.
- **extras:** `memvid`(memvid-sdk 고정), `e5`(sentence-transformers), `langchain`, `langsmith`, `nemo`, `fastapi`, `test`.

---

## 3. 데이터·색인 수명주기

```text
정본(원본) → 정제·마스킹 → 분할 → 임베딩 → 색인 작성(새 버전 파일) → 검증 → 활성(포인터 교체) → 보관/삭제
```

| 단계 | 규칙 |
| --- | --- |
| 정본 | 색인 밖에 둡니다(파일·DB). 삭제·권한·보존의 기준이며 색인은 언제든 정본에서 다시 만듭니다 |
| 컬렉션 | 용도별로 분리합니다(`guides`, `articles`, `research-cards`, `long-prompts`). 접수 원문·후기는 공식 근거 컬렉션에 섞지 않습니다 |
| 마스킹 | 분할 전에 적용하고, 토큰 수는 마스킹된 본문 기준으로 셉니다 |
| 분할 | 제목·소제목을 보존하고, 모델 토크나이저로 예산(예: 300/40)을 셉니다. 같은 입력이면 같은 chunkId가 나옵니다 |
| 임베딩 | 고정 revision, 로컬 실행, 원격 코드 실행 금지. identity를 색인과 함께 저장합니다 |
| 색인 작성 | `data/index/<collection>/<indexVersion>.mv2` 새 파일. 버전 파일은 바꾸지 않고, 같은 이름으로 다시 만들지 않습니다 |
| 검증 | 8개 이하 묶음 적재 → seal → 읽기 전용 재오픈 → `total_hits == 청크 수` → 모든 청크 자기 벡터 1위 → 파일 sha256 기록 |
| 활성 | 작은 포인터 파일(`active.json`)만 교체합니다(Windows에서 열린 .mv2는 덮어쓰지 않음) |
| 질의 | 열 때 포인터·manifest·해시·identity를 확인하고, 하나라도 다르면 `RETRIEVAL_UNAVAILABLE` |
| 모델 교체 | 새 색인 + 같은 골든셋 재평가 → 승인 후 포인터 교체. 다른 모델의 벡터를 섞지 않습니다 |
| 삭제 요청 | 정본에서 지우고 색인을 다시 만듭니다(memvid는 추가 전용). 이전 버전 파일은 핸들을 닫은 뒤 삭제합니다 |
| 보관 | 활성 버전과 직전 버전 1개만 남기고, 증거 파일에는 벡터를 넣지 않습니다 |

manifest 필드: `indexVersion, file, sha256, collectionId, embeddingModel, pinnedRevision, dimension, normalization, chunkerVersion, createdAt, chunks[documentId, chunkId, sourceVersion, title, safeText, tokenCount, maskingVersion, policyVersion, contentHash]`.

---

## 4. 평가 체계

### 4-1. 골든셋 관리

| 항목 | 규칙 |
| --- | --- |
| 형식 | `{"question", "source", "type", "split"?, "notes"?}`. `source`는 정답 문서 ID이며, 정답이 여럿이면 `sources` 목록을 씁니다 |
| 작성 | 질문 작성자와 문서 작성자를 가능하면 나눕니다. `paraphrase` 질문에는 정답 문서 제목 단어를 쓰지 않습니다 |
| 구성 | 유형을 섞습니다(의역·법률 용어·짧은 질의·긴 질의·PII 포함). 헷갈리는 문서 짝을 포함하고, 무근거 질문은 30% 이상 넣습니다(별도 세트 가능) |
| 분할 | `compare`(보정·튜닝용) / `confirm`(동결, 기준을 정한 뒤 1회만 사용) |
| 버전 | `golden_version`을 붙이고 바뀌면 이전 결과와 비교하지 않습니다 |
| 크기 | 20문항(학습) → 60문항(모델 선택) → 200문항(운영 전) 순으로 늘립니다 |
| 검토 | 질문·정답 짝을 두 사람이 확인하거나, 한 사람이 하루 뒤 다시 확인합니다 |

현재 `data/golden_set.json`(20문항, 조문 10개, 헷갈리는 짝 3쌍)은 학습 단계용입니다. 무근거 질문 9개(주제 밖 4, 비슷하지만 답 없는 5)는 `data/golden_no_evidence.json`에 따로 두어, 합치면 29문항 중 31%입니다.

### 4-2. 지표

| 범주 | 지표 |
| --- | --- |
| 검색 | 1위 정답, 3위 안 정답, MRR, 유형별 결과, 모델 간 결과가 갈린 질문 |
| 무근거 | 혼동표(근거 있음/없음 × 통과/차단), 기준값과 그 버전 |
| 두 축 | 질문마다 "정답 순위"와 "판정"을 함께 기록. `found_refused`(정답 1위인데 거절)와 `wrong_accepted`(오답인데 통과)는 따로 셉니다 (`observe/evaluate.two_axis_report`, [예시](evidence/golden/README.md)) |
| 브리프 | 결정·제약 회수율, 폐기안 포함 수, 주입·개인정보 누출 수, 압축률, 예산 준수 |
| 응답 | 인용 ID가 검색 결과의 부분집합인지, 형식 실패율, 원문에 없는 숫자·ID 수 |
| 비용·자원 | 문서 인코딩 시간, 질문 인코딩 중앙값, 메모리, 실패·timeout 수 |

### 4-3. 해석 규칙

- 표본이 작으므로 결과는 `n/총수` 개수로 적고 백분율만 단독으로 쓰지 않습니다.
- 무작위 기준선은 가정을 함께 적습니다(예: 문서 10개, 정답 1개, 서로 다른 3개를 뽑을 때 3/10).
- 모델 비교는 같은 골든셋·같은 분할·같은 identity 규칙에서만 합니다. 결과가 갈린 질문은 사람이 하나씩 읽습니다.
- 기준값(τ)은 `compare`로만 정하고 `confirm`에는 한 번만 적용합니다. 다시 정하면 새 버전입니다.

### 4-4. 실험 기록

결과 파일에 반드시 넣는 것: 실행 명령, 날짜, 패키지·모델 버전, identity, `golden_version`, seed, 질문별 결과, 요약 표, 외부 연결 시도 수(0이어야 함). 벡터와 실제 데이터는 넣지 않습니다.

### 4-5. 승격 조건

| 승격 | 조건 |
| --- | --- |
| lab → incubating | 같은 평가셋에서 기존 방식보다 나음 + 보안 지표(누출 0, 무근거 오판 증가 없음) 유지 + 시험 |
| incubating → stable | ① 또는 ③ 평가에서 **실모델** 증거 + Windows 확인(파일 동작이 걸린 경우) + 계약 문서화 |

---

## 5. 보안 위협 모델

| 위협 | 경로 | 통제 | 확인 시험 |
| --- | --- | --- | --- |
| 프롬프트 주입(직접) | 사용자 입력 | 정규식 확정 차단 + 의미 신호 REVIEW, 지시·자료 분리 프롬프트 | 공격·정상 세트, 숨긴 한 줄 공격 |
| 프롬프트 주입(간접) | 검색 자료·긴 프롬프트 | 자료 검사 단계 분리, 차단 구간 제외·보고(사용자 위험 점수에는 넣지 않음) | 주입 구간 제외 수, 사용자 세션 점수 불변 |
| 말 바꾼 공격 | 입력·자료 | 의미 기반 신호(lab), 문장 단위 비교 | 공격 예문 대비 회수·오탐 |
| 개인정보 노출 | 임베딩·색인·trace·출력 | 저장·임베딩 전 마스킹, 필드별·최종 출력 검사, trace 허용 목록 | 합성 PII가 어디에도 남지 않음 |
| 원격 전송 | memvid 텔레메트리, 키가 있을 때 자동 임베딩, LangSmith 환경변수 tracing, 모델 다운로드 | `MEMVID_TELEMETRY=0`, `opts={"enable_embedding": False}`, 서빙 tracing 차단, `HF_HUB_OFFLINE=1`, 실행 중 소켓 차단 | 대조군 포함 전송 0 시험, 외부 연결 시도 0 |
| 색인 변조·구버전 | 디스크 파일 | manifest 해시·identity 확인, 버전 파일 불변 | 변조·다른 모델·포인터 없음 → 503 |
| 조용한 적재 누락 | memvid 대량 `put_many` | 8개 이하 묶음 + 전수 검증 후 활성 | 60/120개 회귀 시험(Linux·Windows) |
| 출처 위조 | 생성 모델 | 인용 ID 부분집합 검사, 출처는 서버 기록으로 표시 | 없는 ID 인용 → 거절 |
| 수치 지어내기 | 요약·생성 | 원문에 없는 숫자·날짜·ID가 있으면 거절 | 요약 검사 시험 |
| 요청 섞임 | 동시 요청 | 요청별 상태·문맥 바인딩, 공유 가변 상태 금지 | A/B 동시 실행 |
| 자원 고갈 | 동기 추론·취소 | 전용 실행 자원, 작업이 실제로 끝날 때 슬롯 반환, 시간·토큰 상한 | 취소 후 실행 중 작업 수 |
| 오탐으로 인한 잠김 | 세션 위험 | 입력 정책 차단만 적립, 출력·자료 차단은 기록만 | 출력 위반 시 점수 불변 |
| 공급망 | 패키지·모델 | 버전·revision 고정, `trust_remote_code=False`, lock 파일 | 설치 후 회귀 시험 |
| 벡터 역추적 | 저장된 임베딩 | 벡터도 개인 자료로 취급(공개 저장소·증거 파일 금지, 암호화 대상) | 증거 파일에 벡터 없음 검사 |
| 평가 오염 | 골든셋·코퍼스 | 작성 규칙, confirm 동결, 버전 관리 | 동일 질문 중복·누출 검사 |

---

## 6. 모델 후보와 실행 환경

### 6-1. 임베딩 후보

| 후보 | 이유 | 확인할 것 | 상태 |
| --- | --- | --- | --- |
| `intfloat/multilingual-e5-large-instruct` (MIT, 1024차원, 512토큰) | 다국어 검색 기준 모델. ①과 같은 모델 | revision `274baa4…` 고정, CPU 속도, 지시문 효과 | 1순위 |
| Ollama 제공 임베딩 모델 1개 | Llama와 같은 런타임 하나로 운영 | 어떤 모델이 한국어에 맞는지, 품질 | 후보 조사 |
| 더 작은 다국어 모델 1개 | CPU 지연 비교용 | 1위·3위 안 정답 손실 대비 속도 | 후보 조사 |
| 가짜 임베더(글자 2-gram 해싱) | 키워드 수준 기준선 | — | 기준선 |
| 원격 API 임베딩 | 비교용 대안 | 외부 전송이 생기므로 기본 제외, 별도 승인 | 제외 |

Qwen 계열은 Legal Intake와 같은 방침으로 쓰지 않습니다.

### 6-2. 생성 모델

Llama 계열을 씁니다. 모델 ID·정밀도·서빙 방식(Ollama 로컬 서버 또는 프로세스 내 실행)은 ① S0의 PC 사양을 근거로 B03 전에 정합니다. ③의 체인은 특정 모델에 묶지 않습니다.

### 6-3. 실행 환경

| 항목 | 내용 |
| --- | --- |
| 대표 PC | Windows, RAM 약 16GB, RTX 5060 VRAM 약 8GB, E5는 CPU로 시작 (①의 S0에서 확인) |
| Python | 3.12 RAG 실행 환경(① `rag-runtime`과 같은 조건), 시험은 3.12·3.13 |
| CI | Linux에서 가짜 임베더 + 실제 memvid. 실모델 시험은 표시해 따로 실행 |
| 원칙 | 오프라인 로딩, revision 고정, 원격 코드 실행 금지, 추론은 전용 실행 자원에서 |

---

## 7. 핵심 기능

### 7-1. 긴 프롬프트 브리프 (보안 + 요약 + 검색 키워드 강화)

요약 품질은 요약 모델보다 **요약에 들어갈 재료를 잘 고르는 데**서 먼저 올라갑니다.

```text
긴 프롬프트 → 구간 분할 → 보안 처리(마스킹, 주입 구간 제외·보고, 폐기 표시 구간 강등)
 → 핵심어 강화: 조사 제거 → BM25 + 문서 핵심어(TF-IDF) → 질의 확장(상위 구간의 핵심어 추가)
 → 순위: 키워드 · 벡터 · 혼합(RRF) + 반드시 남길 구간(제약·결정·숫자) 가점
 → MMR로 글자 예산 안에서 다양하게 선택 → 원래 순서로 이어 붙인 추출 브리프
 → (선택) LLM 요약 + 원문에 없는 숫자·날짜·ID가 생기면 거절
```

프로토타입 참고 결과(Draft PR #5, 합성 41.6쪽, 예산 6,000자, 과제 6개). 가짜 임베더로 얻은 결과라 의미 검색 결과는 아닙니다.

| 방식 | 평균 정답 회수율 | 주입·개인정보 누출 | 폐기안 포함 |
| --- | --- | --- | --- |
| 앞부분 자르기 | 0.0 | 0 | 0 |
| 키워드(BM25) | 0.467 | 0 | 2 |
| 벡터(가짜) | 0.445 | 0 | 0 |
| 혼합 | 0.943 | 0 | 0 |

승격 조건: 실제 임베딩으로 혼합이 단독 방식보다 나음, 실제 저장 프롬프트의 마스킹본 10건에서 사람이 "필요한 내용이 빠지지 않았다"고 확인.

### 7-2. 골든셋으로 임베딩 모델 고르기

임베딩 모델마다 한국어 의미 파악 능력과 검색 정확도가 다르므로, 감으로 고르지 않고 질문과 정답 조문을 짝지은 골든셋으로 직접 재서 고릅니다.

```json
{"question": "평일 오후 4시에 매장에서 식사할 수 있어?", "source": "제1조"}
```

- **1위 정답:** 가장 유사하다고 고른 1위 조문이 정답 조문과 같은 질문 수
- **3위 안 정답:** 상위 3개 검색 결과 안에 정답 조문이 있는 질문 수
- 함께 보는 것: MRR, 유형별 결과, 지연, 모델 간 결과가 갈린 질문
- 자료: `data/golden_set.json`(질문 20개), `data/articles.json`(합성 조문 10개). 프로토타입 기준선(가짜 임베더): 1위 정답 12/20, 3위 안 정답 13/20

### 7-3. 임베딩 학습 트랙

| 단계 | 질문 | 해 볼 것 |
| --- | --- | --- |
| E1 | 코사인 유사도는 무엇을 재나? | 같은 질문·조문의 점수 분포, 정규화 전후 내적 |
| E2 | 키워드와 의미 검색은 어디서 갈리나? | 기준선 vs E5, 유형별 차이 |
| E3 | 모델은 어떻게 고르나? | 골든셋으로 1위·3위 안·MRR·지연·갈린 질문 |
| E4 | 질의 지시문은 얼마나 중요한가? | E5 지시문 있음/없음 |
| E5 | 청크 크기는 결과를 어떻게 바꾸나? | 조문 통째 vs 문장 vs 300/40 |
| E6 | "근거 없음"은 어떻게 판정하나? | 무근거 질문 추가, top1·간격 보정, 고정 0.8이 안 되는 이유 |
| E7 | 합치면 나아지나? | RRF 혼합 vs 단독 |
| E8 | 다른 일에 쓰면? | 중복 병합·MMR, 긴 프롬프트 브리프, 의미 기반 주입 신호 |

### 7-4. 실험판(lab) 목록

| 실험 | 질문 | 승격 조건 |
| --- | --- | --- |
| 하이브리드(RRF) | 키워드+벡터가 단독보다 나은가? | 같은 평가셋에서 우위 + 무근거 오판 증가 없음 |
| 의미 기반 주입 신호 | 말 바꾼 공격을 잡나? | 공격·정상 법률 질문 세트에서 오탐 기준 충족, REVIEW로만 |
| 질의 재작성(Llama) | 짧은 접수 문장을 늘리면 나아지나? | 전후 비교 + 원문 보존 + 비용 상한 |
| 리랭킹 | 상위 10개 재정렬이 도움이 되나? | 지연 상한 안에서 개선 |
| LangSmith 실험 비교 | 변경을 trace·dataset으로 비교 | 합성 자료만, 허용 목록 통과 |
| 맥락 고르기 | 과거 결정·실패를 골라 넣으면 명세가 나아지나? | 사람 검토 |

---

## 8. 마일스톤·완료 기준·위험

### 8-0. 진행 방식 (대표 방침)

완벽한 개발을 서두르지 않습니다. **먼저 만들어 써 보고, 배우고 익힌 뒤 설계안을 다시 잡아 최종안으로 개발**합니다.

| 단계 | 시기 | 할 일 | 남길 것 |
| --- | --- | --- | --- |
| 1. 시험 개발 | 다음 주 오전 | ① B02b 이후 진행, ③ 프로토타입(Draft PR #5) 유지 | 커밋, 증거 파일 |
| 2. 써 보고 배우기 | 다다음 주 | 개발된 것 복습, 학습 트랙 E1~E8을 직접 돌려 보기 | 막힌 점·의문점 메모 |
| 3. 설계 다시 잡기 | 다다음 주 | 메모와 증거로 이 문서를 v1.0으로 고치고 검수 | 확정된 설계안, 대표 결정 |
| 4. 최종 개발 | 그 뒤 | M0부터 정식 구현 | 시험·증거·승격 기록 |

이 문서(v0.2)는 2단계에서 배울 때 지도로 쓰고, 3단계에서 틀린 부분을 고칩니다.

### 8-1. 마일스톤

| 단계 | 내용 | 완료 기준 | 선행 조건 |
| --- | --- | --- | --- |
| D0 | 이 설계안 확정 | 대표 결정 4개 + 검수 반영 | — |
| M0 | 패키지 뼈대, core 계약, extras, CI(단계 규칙 시험) | 빈 패키지 설치·시험 통과 | D0 |
| M1 | embed·ingest·store·retrieve(게이트)·observe(평가·골든셋) | ① B02b와 같은 결과를 ③에서 재현, Windows 적재 회귀 | ① B02b 검수 |
| M2 | 골든셋 실모델 비교(E5 + 후보 1개) | `docs/evidence/golden/` 보고서, 모델 선택 기록 | M1 |
| M3 | guard(문맥·세션 위험 → 입력·출력·마스킹) | ① 보안 시험을 ③에서 재현 | ① S1~S3 |
| M4 | rag·observe(tracing) | 무근거 생성 0회, 전송 0(대조군 포함) | ① B03~B05 실모델 |
| M5 | 긴 프롬프트 브리프 실모델 평가 | 합성 + 실제 마스킹본 10건 확인 | M2 |
| M6 | 리서치 DP-14 필터에서 ③ 사용 | 그림자 1주 결과 | M2, 리서치 DP-14 결정 |
| M7 | 법률 검색 시범(합성·공개 자료) | 60문항 골든셋 + 무근거 판정 평가 | M2 |

### 8-2. 위험과 대응

| 위험 | 대응 |
| --- | --- |
| memvid SDK의 조용한 결함(대량 적재 누락 등) | 버전 고정, 적재 후 전수 검증, 회귀 시험, 문제 기록 |
| Windows 파일 잠금 | 포인터만 교체, 핸들 정리 후 삭제, Windows 시험 |
| E5 CPU 지연 | 배치 상한, 작은 모델 비교(§6-1), 색인은 미리 적재 |
| 작은 골든셋 과적합 | confirm 동결, 단계별 크기 확대, 개수로 보고 |
| 범위 확장 | 새 기능은 lab에서 시작, 승격 조건 충족 전 stable 금지 |
| ①과 ③의 코드 중복 | 원칙 6(복사 금지), 이전 뒤 ①이 ③을 의존 |
| 코더 크레딧 한도 | 코드 작성은 마일스톤 단위로 나누고, 실행·측정은 대표 PC에서 |
| 외부 전송 실수 | 기본 OFF + 실행 중 소켓 차단 + 대조군 시험 |

---

## 9. 대표가 정할 것

1. 패키지 이름: **A** `memvid_guardrail` 유지 / B 범위를 드러내는 새 이름(예: `legal-rag-kit`)
2. ①과의 관계: **A** 검증 후 ③으로 옮기고 ①이 ③을 의존성으로 사용 / B 당분간 ①에 두고 ③은 문서만
3. lab의 공개 범위: **A** 공개 저장소 안 `lab/`(합성 자료만) / B lab은 비공개 저장소로 분리
4. 기존 Spring 하이브리드 설계 문서: **A** `docs/hybrid/`로 옮겨 유지 / B README 앞부분 유지

추천: `③: 1A 2A 3A 4A`. **상태: 대표 결정 대기.** 결정 전에는 M0 이후 개발과 실제 모델 비교를 시작하지 않습니다.

## 10. 하지 않는 것

실제 의뢰인·소송 자료, 유료 API 기본 사용, 원격 tracing 기본 사용, 검증 없는 stable 승격, 같은 부품을 두 저장소에서 따로 고치기, 유사도 결과로 결정을 자동 확정하기.

## 부록. 현재 코드와의 대응 (main = M0 뼈대, Draft PR #5 = 실험 추가분)

| 설계 절 | 프로토타입 위치 | 비고 |
| --- | --- | --- |
| §2 store·retrieve·embed·ingest | `src/memvid_guardrail/{store,retrieve,embed,ingest}` | ① B01~B02b 참고 구현에서 옮김 |
| §2 rag·observe | `src/memvid_guardrail/{rag,observe}` | 가짜 모델 시험만 |
| §7-1 브리프 | `src/memvid_guardrail/lab/briefing` (Draft PR #5) | 가짜 임베더 결과 |
| §7-2 골든셋 | `src/memvid_guardrail/lab/golden.py`, `scripts/compare_embedders.py` (Draft PR #5) | 가짜 임베더 결과 |

나머지 행은 `main`의 M0 뼈대에 있습니다. 설계 v1.0 확정 뒤 필요한 부분만 다시 판단해 M1부터 정식으로 만듭니다.
