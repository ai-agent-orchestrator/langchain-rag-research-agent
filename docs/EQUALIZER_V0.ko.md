# Equalizer v0 — 갈아 끼우는 부품 구조

작성: 2026-11-09 · 상태: **v0, 보정 전.** LLM 호출 없음. 합성 골든셋으로만 돌려 봤다.

대표 방침: "Equalizer든 분야별 필터든 얼마든지 갈아 끼우고 고칠 수 있게. 결과값을 feedback loop로 보고 차이를 느끼거나 수치화된 board로 본다."

## 부품과 교체 지점

`build_brief(draft, task, knobs | preset, budget, focus, packs, parts)`가 아래 부품을 연결한다. 부품은 `Parts`로 넘겨 하나씩 바꿀 수 있다.

| 순서 | 부품 | v0 구현 | 교체 예 |
| --- | --- | --- | --- |
| 1 | 입력 정책 | `guard.FakeInputPolicy` | legal-intake 정본 `check_input_policy` 어댑터 (M3) |
| 2 | 분할 | `ingest.SentenceChunker` (문장, 원문 오프셋) | 문단·구조 분할 |
| 3 | 분류 | `ontology.FakeLabeler` (전부 Unclassified) | 정규식/모델 라벨러 |
| 4 | 인과 링크 | `ontology.FakeLinkBuilder` (없음) | 규칙 기반 원인–결과 쌍 |
| 5 | 관련도 | `term_overlap` (과제 단어 겹침, 과제 없으면 1.0) | E5 임베딩 + 리랭커 |
| 6 | 엣지 점수 | `edge.RuleEdgeScorer` (골든룰 150 + 묶음 50) | 다른 규칙 파일, 모델 점수기 |
| 7 | 노브 매핑 | `knobs.LinearKnobMapper` (τ 미보정) | 임베딩 모델별 보정 매퍼 |
| 8 | 감량 | `diet.ClassOrderDieter` (낮은 점수부터, 보호 유지, 쌍 함께, 자르지 않음) | 다른 감량 전략 |
| 9 | 조립 | `compose.ExtractiveComposer` (원문 순서, DATA 블록) | 분류 순서 조립 |
| 10 | 출력 검사 | `compose.NumberIdOutputChecker` (새 숫자·없는 구간 번호 거절) | 날짜·고유명사 검사 추가 |

## 필터 프로필 (재사용의 단위)

`profiles/*.json` 하나 = 분야 필터 하나: 온톨로지 분류(그 분야의 문장 종류와 판별 표현), 감량 순서, 절대 빼지 않는 분류, 노브, 분야 묶음, 집중 키워드, 외부 허용. 누구든 `profiles/_template.json`을 복사해 고치면 된다. 다른 프로젝트에서는 `Equalizer.from_profile("litigation").brief(text)`로 붙인다. 사용법: [profiles/README.md](../profiles/README.md).

## 필터 (= 프리셋), 데이터로 교체

`data/equalizer/presets_v0.json`. 필터 하나 = 노브 수준(Low/Mid/High) + 분야 묶음 + 기본 집중 키워드 + 외부 공급자 허용 여부. 감량 순서는 공통(`diet`).

| 필터 | 이름 | 창 | 방패 | 묶음 | 외부 |
| --- | --- | --- | --- | --- | --- |
| `research` | 일반 리서치 | Low | High | - | 허용 |
| `litigation` (= `litigation_evidence`) | 소송 | High | High | legal | **거부** |
| `politics` | 정치·지정학 | Low | High | geopolitics | 허용 |
| `macro` | 매크로 | Mid | High | macro | 허용 |
| `tech` | 기술·기업 | Mid | Mid | tech | 허용 |
| `defense` | 방위산업(전략·정책) | Mid | High | defense, geopolitics | 허용 |
| `counseling` (= `counseling_support`) | 상담 지원 | Mid | High | - | **거부** |
| `legal_lookup` | 법령·판례 조회 | High | Mid | legal | 허용 |
| `general_summary` | 일반 요약 | Low | Low | - | 허용 |

## 피드백 도구 세 개

| 명령 | 무엇을 보나 |
| --- | --- |
| `python scripts/golden_edge_eval.py --set ... --packs ...` | 문장별 엣지 점수와 이유, 놓침·과대, 지난 실행 대비 |
| `python scripts/brief_demo.py --set ... --preset litigation --budget 300` (또는 `--sweep`) | 노브·필터에 따라 무엇이 남고 빠지는지, 감량 기록, 백본 입력 |
| `python scripts/filter_board.py [--grid] [--budget N]` | **수치 보드**: 필터 × 골든셋의 보존 적중, 클리셰 남음, 압축률, 보호 수. `.runs/board.html`(어두운 화면, 폰에서 열림) + 지난 보드 대비 ▲▼ |

## 첫 보드에서 보인 것 (합성 2세트, 정직한 기록)

- 예산 300에서는 필터 간 차이가 거의 없었다. 과제 문장이 없으면 관련도가 모두 1.0이고, 초안이 짧아 대부분 남기 때문이다.
- 예산 170으로 줄이면 차이가 보이기 시작했다. 매크로 세트에서 `macro` 필터의 보존 적중이 오히려 0.429 → 0.286으로 낮았다. 매크로 묶음이 숫자 많은(긴) 문장에 점수를 몰아 줘 예산을 먼저 차지했기 때문으로 보인다.
- 즉 v0 필터는 아직 "다르게 동작한다"는 것을 보여 주지 못한다. 실제 초안과 골든셋으로 루프를 돌려야 의미가 생긴다. 이 보드가 그 판단 도구다.

## 아직 아닌 것

τ 보정, 실제 임베딩·리랭커, 분류기, 인과 링크 생성, LLM 백본 호출, LangGraph 그래프 연결(현재는 순수 Python 조립). 각각 위 표의 교체 지점에 끼운다.
# 2026-11-10 부품 연결 추가

| 부품 | 연결 상태 |
| --- | --- |
| C1 RuleLinkBuilder | `Parts.with_defaults_v1()` 또는 `Equalizer.brief(..., parts_preset="v1")`로 선택. 기존 기본 조합은 유지 |
| C4 make_semantic_relevance | `Library.brief(..., relevance="semantic")`로 서재 임베더 사용. 기본 `overlap` 유지, τ 보정 전 |

v1은 선택된 문장들의 감량에 인과 쌍 링크를 전달합니다. 관련도/상위 K 선택 전에
탈락한 문장까지 자동 복구하는 기능은 없습니다. 의미 관련도는 외부 모델을 준비하지
않으며 서재에 주입한 임베더를 그대로 사용합니다.

