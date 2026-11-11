# 리서치 도메인 LangGraph 가드레일 설계 (분업형 리서치 그래프 + 교체형 도메인 필터)

2026-11-11 KST · 작성: Claude · 상태: 설계안(1단계만 구현) · 관련: D13/P1, `docs/LANGGRAPH_GUARDRAIL.ko.md`, `docs/DOMAIN_FILTERS.ko.md`

## 0. 한 줄 요약

AI가 바로 답하게 두지 않는다. **질문 분류 → 로컬 DB 검색 → 규정·사실 필터**를 반드시 거치게 하고,
리서치는 "연구원 한 명"이 아니라 **정제 → 개념 추출 → 찬반 분리 탐색 → 상충 비교 → 작성 → 검수**의 분업으로 처리한다.
모든 중간 산출물은 **출처 태그가 붙은 채 State에 리듀서로 칸칸이 누적**되고, 검수에서 부족한 부분만 **그 노드로 되돌아가** 채운다.
그래프의 모양은 도메인과 무관하게 고정이고, 도메인마다 바뀌는 것은 **필터 묶음(DomainFilter + 도메인 팩)** 하나다.

## 1. 전체 구조

```text
START → classify ─smalltalk→ finish
            │research
            ▼
         screen (도메인 입력 필터: 범위·응급·관할)───blocked──→ finish(BLOCKED)
            ▼
          plan  (질문 → 필수 지표·쟁점·관점 목록, 구조화 출력)
            ▼
   ┌── retrieve_pro ──┐     (조건부 엣지로 관점을 강제 분리. 로컬 Chroma만)
   ├── retrieve_con ──┤
   └── retrieve_base ─┘
            ▼
         refine  (정제: 중복 제거, 마스킹, 문단별 주입 검사, 출처 태그 부착)
            ▼
         extract (온톨로지 추출: 주장·개체·관계·수치를 구조화 출력으로. 원문 위치(span) 필수)
            ▼
         compare (상충 비교: 찬반 주장 짝짓기, contradicts/supersedes 관계)
            ▼
         coverage (필수 지표 대비 빈칸 계산, 순수 Python) ──gap & 예산 남음──→ retrieve_gap ─→ refine
            ▼ 충분
          write  (State의 주장만으로 작성, 문장마다 claim_id 인용)
            ▼
         verify  (도메인 필터 검수) ──pass──→ finish
            ├─ 수치·지표 누락(GAP)        ──→ retrieve_gap  (해당 지표만 재검색)
            ├─ 서술 문제(밀도·인과·조건)   ──→ write          (재작성만, 재검색 없음)
            └─ 고칠 수 없음·예산 소진      ──→ finish (부분 보고서 + "확인 못 한 항목" 명시)
   (모든 엣지 공통) 반복 횟수·비용 단위 초과, 노드 오류 → kill
```

## 2. State 설계 (중앙 금고)

원칙: **덮어쓰지 않고 쌓는다.** 문서별 주장·출처·수치는 리듀서로 누적하고, 원문 대신 위치(span)와 출처 ID를 들고 다닌다.

| 필드 | 타입 | 리듀서 | 내용 |
| --- | --- | --- | --- |
| `question` | str | 덮어쓰기 | **마스킹된** 질문 |
| `plan` | `ResearchPlan` | 덮어쓰기 | 필수 지표(`required_metrics`), 쟁점, 관점(pro/con/base) |
| `sources` | list[`SourceRef`] | id 기준 병합 | `source_id`, 문서 버전, 관점 태그, 검색 점수 |
| `claims` | list[`Claim`] | 누적(add) | `claim_id`, 문장, 관점, `source_id`, `span(start,end)`, 종류(가설·제약·사실) |
| `entities` | list[`Entity`] | id 기준 병합 | 개념(온톨로지 5종 + Unclassified) |
| `relations` | list[`Relation`] | 누적 | causes / supports / contradicts / supersedes / condition, 양끝 claim_id, `source_id` |
| `metrics` | list[`Metric`] | 누적 | 지표명, 값, 단위, 기간, 비교 기준, `source_id`, span (원문 그대로, 계산 금지) |
| `gaps` | list[str] | 덮어쓰기 | 아직 못 채운 필수 지표·쟁점 |
| `draft` | `Draft` | 덮어쓰기 | 문장 목록, 문장별 `claim_ids` |
| `verdict` | `Verdict` | 덮어쓰기 | 검수 결과 코드·점수 |
| `counters` | dict | 덮어쓰기 | 노드별 실행 횟수, 비용 단위, 지표별 재검색 횟수 |
| `domain_log` | list[str] | 누적 | 각 관문의 판정 **코드만** (예: `VERIFY:FAIL:GAP`) |

규칙
- 모든 `Claim`·`Metric`은 `source_id`와 `span` 없이는 State에 들어갈 수 없다(검증 실패 시 버림, 버린 개수는 로그 코드로).
- `span`으로 원문을 다시 잘라 봤을 때 그 텍스트가 실제로 있어야 한다. 모델이 지어낸 인용은 여기서 걸러진다.
- 원문, 질문 원문, 예외 메시지는 State·로그에 넣지 않는다(기존 원칙 유지).

## 3. 노드별 역할과 "하지 않는 일"

| 노드 | 하는 일 | 구현 방식 | 하지 않는 일 |
| --- | --- | --- | --- |
| classify | research / smalltalk | 규칙 라우터(기본), 구조화 출력 라우터(선택, 마스킹 텍스트만) | 원문 외부 전송 |
| screen | 도메인 입력 필터 | `DomainFilter.check_input` | 모델 호출 |
| plan | 필수 지표·쟁점·관점 결정 | 구조화 출력 `ResearchPlan`, 실패 시 규칙(질문 속 지표 단어) | 검색·답변 |
| retrieve_pro/con/base | 관점별 질의로 로컬 검색 | Chroma + 기존 근거 게이트(τ) | 웹 검색, 관점 섞기 |
| refine | 중복 제거, 마스킹, 주입 검사, 출처 태그 | 기존 guard·검색 게이트 재사용 | 내용 수정 |
| extract | 주장·개체·관계·수치 추출 | 구조화 출력(`Claim`·`Relation`·`Metric`), 규칙 폴백(`ontology/rule_labeler`, `compose/numbers`) | span 없는 항목 저장 |
| compare | 상충 주장 짝짓기 | 순수 Python(같은 개체·지표, 반대 관점) + 선택적 모델 판정 | 승자 정하기 |
| coverage | 빈칸 계산 | 순수 Python: `required_metrics` − `metrics` | 모델 호출 |
| retrieve_gap | 빈 지표만 표적 재검색 | 지표명으로 질의, 지표별 재시도 한도 | 전체 재검색 |
| write | State의 주장으로만 작성 | 생성 모델, 입력은 claims/metrics/relations 표 | 원문 직접 투입, 출처 없는 문장 |
| verify | 검수 | `DomainFilter.verify` (리서치 필터) | 고쳐 쓰기(판정만) |

## 4. 검수(verify)와 표적 루프

검수 결과 코드마다 **되돌아갈 노드가 다르다.** 이것이 "부족한 부분만 다시 돌리는" 핵심이다.

| 코드 | 의미 | 되돌아갈 곳 |
| --- | --- | --- |
| `GAP:<지표>` | 계획한 필수 지표가 보고서에 없음 | `retrieve_gap` (그 지표만) |
| `UNSUPPORTED_NUMBER` | 원문(State의 metrics)에 없는 수치 | `write` |
| `UNGROUNDED_SENTENCE` | 인용 claim과 문장 내용이 안 맞음 | `write` |
| `CAUSAL_LOSS` | 근거의 인과관계가 보고서에서 사라짐 | `write` |
| `CONSTRAINT_DROPPED` | 조건·예외가 빠짐 | `write` |
| `LOW_DENSITY` | 일반론 위주, 구체 내용 비율 낮음 | `write` |
| `ONE_SIDED` | 반대 근거가 있는데 한쪽만 서술 | `write` (반대 근거가 아예 없으면 보고서에 "반대 근거 없음" 명시) |
| `NO_EVIDENCE` | 확인할 근거 자체가 없음 | `finish` (안전 답변) |

한도: 지표별 재검색 ≤ 2회, 재작성 ≤ 2회, RAG·생성 호출 총합은 기존 `max_loops`·`max_cost` 예산 안. 한도를 넘으면
엉성한 답 대신 **부분 보고서 + 확인하지 못한 항목 목록**으로 끝낸다(지어내지 않는다).

## 5. 도메인 교체 지점 (나중에 법률·의료·로컬 행정으로 확대)

그래프 노드와 엣지는 그대로 두고, 아래 묶음만 바꾼다.

| 교체 지점 | 리서치 (지금) | 법률 (예정) | 의료 (예정) | 로컬 비즈니스·행정 (예정) |
| --- | --- | --- | --- | --- |
| `check_input` | 범위·길이 | 사건 유형 분기(형사/민사 격리) | **응급 여부 분류**(응급이면 즉시 안내 후 종료) | **관할·조건 분기** |
| plan의 필수 항목 | 질문 속 지표·쟁점 | 시점, 당사자, 쟁점 법조 | 증상, 복용 약, 기저질환 | 관할, 신청 유형, 구비서류 |
| 관점 분리 | 찬성/반대·리스크 | 원고/피고 주장 | 가이드라인 권고/금기 | 원칙/예외 규정 |
| State 추가 칸 | — | **시간순 사건 로그(리듀서)** | 금기 약물 목록 | 서류 체크리스트 |
| 검색 강제 | 로컬 문서 | **검증된 법조항 DB만**, 폐지·개정 여부 | 임상 가이드라인 근거 매핑 | **최신 규정 DB만**, 양식 버전 |
| verify 규칙 | 수치·근거·인과·조건·밀도·균형 | 없는 조항·폐지 판례 인용 차단, 시차 뒤섞임 | 진단 단정 차단, 금기 누락 | 구버전 양식, 예외 규정 누락 |
| finalize | 그대로 | 법률 자문 아님 고지 | **면책·전문의 권고** | 기관 확인 안내 |

코드상 계약: `guard/domain_filter.py`의 `DomainFilter`(check_input / verify / finalize, name·version).
새 도메인은 파일 하나를 추가하고 `register("legal", ...)`만 하면 그래프에 끼워진다. 모든 등록 필터는 같은 계약 시험을 통과해야 한다.

## 6. 단일 LLM 대비 차이: 주장이 아니라 측정할 가설

아래는 이 설계가 노리는 효과다. 아직 측정하지 않았으므로 **가설**로 두고, 합성 골든셋으로 단일 모델 직접 요약과 비교한다.

| 가설 | 측정 지표 | 비교 대상 |
| --- | --- | --- |
| 핵심 뼈대 보존(고밀도 압축) | 골든 인과·조건 문장 보존율, 밀도 점수 | 단일 모델 "핵심만 요약" |
| 출처 정확도 | 근거 없는 수치 수, 잘못된 출처 연결 수 | 동일 |
| 관점 균형(확증 편향 차단) | 반대 근거가 있을 때 보고서 포함률 | 동일 |
| 자가 보완 | 필수 지표 충족률, 루프 횟수, 비용 단위 | 루프 끈 같은 그래프 |

표본이 작으면 경향으로만 보고 Wilson 95% 구간을 같이 적는다(AGENTS.md 평가 규칙).

## 7. 기존 코드와의 연결

- 이미 있음: 가드레일 그래프(classify·rag·비용/반복 관문, D13), `serving_trace_guard`, Chroma 저장소, 근거 게이트,
  `ontology/rule_labeler`(도메인 프로필로 클래스 정의), `compose/numbers`(수치를 원문 그대로 추출), 골든 룰의 인과 유형·도메인 팩.
- 1단계 구현 완료(이번 커밋): `guard/domain_filter.py`(교체 계약·등록), `guard/research_filter.py`(검수 v1:
  수치·근거·인과·조건·밀도), 가드레일 그래프의 `screen`·`verify` 관문과 재생성 루프, `GuidancePipeline.ainvoke_with_evidence`.
  시험 `tests/test_domain_filter.py` 18개.
- 아직 없음: plan, 관점 분리 검색, refine 분리, extract(구조화 출력), compare, coverage·표적 재검색, claim 인용 작성, `GAP`·`ONE_SIDED` 판정.

## 8. 구현 순서 (각 단계 끝마다 시험 통과 + 보고서)

1. **(완료)** 도메인 필터 계약 + 리서치 검수 v1 + screen/verify 관문.
2. State 스키마와 리듀서(`Claim`·`Metric`·`Relation`·`SourceRef`), span 검증기. 순수 Python, 모델 없음.
3. extract 노드: 규칙 폴백 먼저(rule_labeler·numbers), 그다음 구조화 출력 어댑터(rag/ 안에서만).
4. plan + coverage + `retrieve_gap` 표적 루프, `GAP` 코드와 지표별 한도.
5. 관점 분리 검색(pro/con/base)과 compare, `ONE_SIDED` 판정.
6. write를 claim 인용 방식으로 바꾸고, verify를 claim 단위로 강화(문장 ↔ 인용 claim 대조).
7. 6절 가설 측정(합성 골든셋, 단일 모델 기준선).

2·3·4단계는 모델 없이 시험 가능한 부분이 많아 NightCoder 명세로 나눠 맡기기 좋다.

## 9. 결정이 필요한 것

- plan의 필수 지표를 누가 정하는가: 질문에서 자동 추출만 할지, 사용자가 체크리스트로 줄 수 있게 할지.
- 반대 근거가 로컬 DB에 아예 없을 때: 보고서에 "반대 근거 없음"만 적을지, 자료 추가를 요청하고 멈출지.
- 구조화 출력 모델: 로컬 모델(Llama 계열)로 할지, 마스킹 후 외부 모델을 허용할지(리서치 프리셋 한정).
