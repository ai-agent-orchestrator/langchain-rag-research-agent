# 하이브리드 내부 계약·memvid 어댑터 설계 (한국어 초안 v1)

> 상태: **설계 초안**. 구현·통합·성능·운영 보안은 모두 검증되지 않았다. 이 문서의 통제와 수치는 설계 책임이지 검증된 게이트가 아니다.
> 상위 문서: [README](../README.md) · [공부 가이드](study-guide.ko.md). 기준 구현: `legal-ai-intake-system`(Spring Boot, Java 21).

## 1. 한 장 요약

- **Spring**: 인증·사건 권한·정책·예산 판단의 단일 경계. 지금 구현(38개 API, JWT, Fixed/Dynamic Guard, 비용 통제, Privacy 마스킹)을 그대로 계승한다.
- **FastAPI**: 허용된 작업만 실행한다. 검색·memvid 접근·모델 호출. **Spring이 서명한 요청만** 받고, 사건 범위는 Python도 다시 확인한다.
- **memvid**: 사건 단위 파일(`case` 하나 = 파일 하나)에 근거 자료와 색인을 보관한다. 파일 경로는 서버 매핑표로만 정한다(사용자 입력 금지).
- 연결은 **좁은 JSON 계약 5개**뿐이다(3장). 계약이 같으면 memvid를 다른 저장소로 바꿀 수 있다(결정 D-021).

## 2. 신뢰 경계와 책임

| 영역 | 맡는 일 | 맡지 않는 일 |
|---|---|---|
| Spring | 로그인, 역할, **사건 접근 권한**, Fixed/Dynamic Guard, 예산 예약·정산, 요청 서명, 감사 기록, 최종 Privacy 마스킹, 변호사 검토 상태 | 검색 색인, 임베딩, memvid 파일 접근 |
| FastAPI | 서명·만료·범위 재검증, memvid 적재·검색·삭제, 모델 호출(허용된 단계만), 근거 묶음 생성, 사용량 보고 | 사용자 인증, 권한 판단, 예산 결정, DB 직접 쓰기(업무 DB) |
| memvid | 사건별 문서·청크·색인 저장 | 권한, 비용, 만료 판단 |

원칙: **보안·비용은 코드로 강제**하고 모델 판단에 맡기지 않는다. Spring이 거부한 요청은 Python까지 가지 않는다. Python은 Spring을 믿되 서명과 범위를 다시 확인한다(내부 API 직접 호출·위조 방지).

## 3. 내부 계약 (Spring → FastAPI)

공통 규칙(5개 모두):
- 전송: 내부망 HTTPS 또는 같은 호스트 loopback. 외부 노출 금지.
- 인증: `Authorization: Bearer <내부 토큰>`. HS256(또는 Spring 개인키 서명 RS256)이며 **TTL 60초 이하**. 클레임은 아래와 같다.
  `iss, aud=fastapi-memory, jti(1회용), exp, tenantId, caseIds[](이번 요청에 허용된 사건), role, purpose, budget{maxCostCredits, maxStages, deadlineMs}, requestId`
- 헤더: `X-Request-Id`, `Idempotency-Key`(쓰기·모델 호출 필수), `X-Trace-Id`.
- 본문에는 비밀값·내부 경로·사용자 비밀번호를 넣지 않는다. 사건 자료 본문은 마스킹된 텍스트만.
- 응답 공통 필드: `requestId, status(OK|REFUSED|FAILED), code, usage{stages, inputTokens, outputTokens, costCredits}, warnings[]`.
- 오류 코드(고정 목록): `AUTH_INVALID, AUTH_EXPIRED, REPLAY_DETECTED, CASE_NOT_ALLOWED, TENANT_MISMATCH, MEMORY_NOT_FOUND, MEMORY_CORRUPT, MEMORY_LOCKED, EVIDENCE_INSUFFICIENT, BUDGET_EXCEEDED, STAGE_NOT_APPROVED, MODEL_TIMEOUT, MODEL_INVALID_JSON, MODEL_REFUSED, IDEMPOTENT_CONFLICT, INTERNAL`.

| # | 메서드·경로 | 용도 | 핵심 요청 | 핵심 응답 |
|---|---|---|---|---|
| M1 | `POST /internal/v1/memory/documents` | 자료 적재 | `caseId, documentId, version, sourceType, text(마스킹됨), docDate, chunkHint` | `documentId, version, chunkCount, embeddingModel, memoryVersion` |
| M2 | `POST /internal/v1/memory/search` | 근거 검색 | `caseId, query(마스킹됨), topK(≤8), filters{docIds, dateFrom, dateTo}` | `evidence[]`, `evidenceSufficient(bool)`, `memoryVersion` |
| M3 | `POST /internal/v1/summaries` | 변호사 전달용 상담 요약 초안 | `caseId, intakeFacts{구조화 필드}, evidenceQuery, stagePlan` | `draft{sections[]}`, `claims[]`(각 주장 → evidence 참조), `reviewRequired=true` |
| M4 | `DELETE /internal/v1/memory/cases/{caseId}` | 사건 파일 삭제·보존 만료 | `reason, requestedBy` | `deleted(bool), backupsPurgedAt` |
| M5 | `GET /internal/v1/health` | 상태 | - | `status, memvidVersion, embeddingModel, openHandles` |

`evidence[]` 한 건의 필드: `evidenceId, caseId, documentId, documentVersion, chunkId, quote(원문 일부), offsets, docDate, ingestedAt, score`.
**출처와 갱신일이 없는 근거는 반환하지 않는다.** `evidenceSufficient=false`면 Spring이 답변 범위를 제한하고(예: "자료가 부족해 확인할 수 없습니다") 모델 호출을 생략할 수 있다.

M3의 규칙:
- 요약의 모든 주장(`claims[]`)은 `evidenceId` 하나 이상을 가져야 한다. 없으면 `unsupported`로 표시하고 변호사 화면에서 강조한다.
- 코드가 검증한다: JSON 스키마, 출처 존재 여부, 금액·날짜 수치가 근거 청크에 실제로 있는지. 모델의 자기 평가는 쓰지 않는다.
- 초안은 항상 `reviewRequired=true`. 변호사 승인 전에는 의뢰인에게 나가지 않는다.

## 4. memvid 어댑터

Python 안의 함수 경계 하나 뒤에 둔다. 교체해도 3장 계약은 변하지 않는다.

```
MemoryStore (인터페이스)
  open(caseRef) -> Handle              # 사건 파일 열기 (쓰기는 단일 writer)
  append(handle, doc) -> ChunkInfo     # 적재 + 색인
  search(handle, query, topK, filters) -> list[Evidence]
  delete(caseRef) -> DeleteResult      # 파일·색인·캐시 삭제
  verify(caseRef) -> VerifyResult      # 파일 무결성 점검
  close(handle)
```

- **경로 결정**: `CaseRegistry`(서버 매핑표 `tenantId + caseId → 파일 상대경로`)만 사용한다. 요청에서 온 문자열을 경로에 쓰지 않는다. 경로는 허용 루트 아래로 정규화하고 탈출(`..`, 심볼릭 링크)을 거부한다.
- **격리**: 캐시 키는 항상 `tenantId + caseId + memoryVersion`. 공유 전역 캐시에 사건 간 자료를 섞지 않는다.
- **동시성**: 사건 파일마다 쓰기 잠금 1개. 읽기는 다수 허용. 잠금 대기는 최대 N초(기본 5초) 후 `MEMORY_LOCKED`.
- **임베딩**: 모델 이름과 버전을 사건 파일 메타에 기록한다. 모델이 바뀌면 그 사건은 재색인 전까지 `MEMORY_STALE` 경고를 낸다. 기본은 **로컬 임베딩**(외부 유료 호출 없음). 외부 임베딩을 쓰면 그 호출도 예산 예약 대상이다.
- **버전**: 문서 수정은 새 `documentVersion`으로 append. 검색은 최신 버전을 기본으로 하되 `version`을 반환한다.
- **백업·삭제**: 사건 파일 단위 스냅샷. 삭제 요청(M4)은 원본, 색인, 캐시, **백업까지** 정해진 기한 내 제거하고 `backupsPurgedAt`을 기록한다.
- **손상**: `verify` 실패 시 `MEMORY_CORRUPT`. 자동 복구는 마지막 스냅샷에서만, 복구 사실은 감사에 남긴다.
- **상태**: memvid 어댑터는 현재 `UNVERIFIED`다. 첫 단계에서 적재→검색→삭제 왕복과 사건 간 격리 테스트로 검증한다(구현 첫 단계).

## 5. 요청 하나의 흐름 (상담 요약 예시)

1. 변호사가 사건 요약을 요청한다. Spring: JWT → **사건 접근 권한**(소유·배정 LAWYER·ADMIN) → DTO 검증.
2. Spring: Fixed Guard → 비용 통제 → Dynamic Guard. 막히면 여기서 `reasonCode`와 함께 종료(FastAPI 호출 없음).
3. Spring: 예산 **예약**(원자적: 잔액 확인과 예약을 한 번에). 내부 토큰 발급(허용 사건 ID, 한도, 마감).
4. FastAPI: 토큰 서명·만료·`jti` 재사용·사건 범위 확인 → M2 검색.
5. `evidenceSufficient=false`면 모델 호출 없이 "근거 부족" 응답(비용은 검색분만 정산).
6. 충분하면 승인된 단계만 모델 호출 → M3 검증(스키마·출처·수치).
7. Spring: 출력 Guard → Privacy 마스킹 → 검토용 초안으로 저장(`DRAFT`, 변호사 승인 대기).
8. Spring: **정산**(공급자 usage 기준). 모델 호출 후 실패해도 이미 쓴 단계 비용은 정산한다. 어떤 경로든 마지막에 반환/정산이 실행되어야 한다(finally).

## 6. 비용 통제

- 예약 단위: 단계(검색, 임베딩, 요약, 재시도). 단계마다 상한이 있고 합계가 `budget.maxCostCredits`를 넘으면 `BUDGET_EXCEEDED`.
- 모델 호출은 한 요청에 **정해진 횟수만**(기본 1회). 재시도는 같은 `Idempotency-Key`로, 한도 안에서만.
- 타임아웃과 "미실행"을 구분한다. 응답을 못 받았으면 `UNSETTLED`로 두고 공급자 사용량과 대조한 뒤 정산한다.
- 취소(클라이언트 끊김)에도 예약은 반환된다(비동기 리팩터 A2 명세와 동일 규칙).

## 7. 구현 순서 (개요)

| 단계 | 내용 | 선행 |
|---|---|---|
| H0 | 계약 문서 확정(OpenAPI 스키마와 오류 코드 목록) | - |
| H1 | FastAPI 골격: 서명 검증, 오류 코드, `/health`, 계약 테스트 틀 | H0 |
| H2 | `MemoryStore` 인터페이스, 가짜 구현, memvid 어댑터, 격리·왕복·손상 테스트 | H1 |
| H3 | 적재(M1)·검색(M2): 출처·갱신일·충분성 판정 | H2 |
| H4 | Spring `FastApiMemoryClient`: 서명, 타임아웃, 재시도, 예약·정산 연결, 스텁 서버 계약 테스트 | H0 |
| H5 | 요약(M3)과 검증기(스키마·출처·수치) | H3 |
| H6 | 변호사 요약 화면과 승인 상태 | H4, H5 |
| H7 | 삭제·보존 만료·백업 정리(M4) | H3 |
| H8 | 운영 준비: HTTPS, 비밀값 관리, 영속 DB·예산 장부, 회원 DB, 관리자 인증 강화 | 별도 |
| H9 | 전환·이탈 분석 대시보드(실측 기반) | 실데이터 |

모든 단계는 정상·실패·차단 경로의 회귀 테스트를 유지한다.

## 8. 테스트 매트릭스 (계약 테스트는 Spring과 Python 양쪽이 같은 케이스를 쓴다)

| 구분 | 케이스 | 기대 |
|---|---|---|
| 정상 | 적재 후 검색, 근거에 출처·갱신일 포함 | `evidenceSufficient=true` |
| 정상 | 요약 생성, 모든 주장에 근거 연결 | `reviewRequired=true` |
| 차단 | 서명 오류 / 만료 / `jti` 재사용 | `AUTH_INVALID` / `AUTH_EXPIRED` / `REPLAY_DETECTED` |
| 차단 | 토큰에 없는 사건 ID 요청 | `CASE_NOT_ALLOWED` |
| 차단 | 다른 테넌트 사건 접근(경로 위조 포함) | `TENANT_MISMATCH`, 파일 열지 않음 |
| 차단 | 예산 초과 / 승인 안 된 단계 | `BUDGET_EXCEEDED` / `STAGE_NOT_APPROVED` |
| 실패 | 모델 타임아웃, 모델 JSON 오류, 취소 | 예약 반환·정산 확인 |
| 실패 | memvid 파일 손상, 잠금 대기 초과 | `MEMORY_CORRUPT` / `MEMORY_LOCKED` |
| 경계 | 근거 없음 | `EVIDENCE_INSUFFICIENT`, 모델 미호출 |
| 경계 | 같은 `Idempotency-Key` 재시도 | 같은 응답, 이중 과금 없음 |
| 격리 | 사건 A 적재 후 사건 B 검색 | A의 자료가 B에 나오지 않음(캐시 포함) |
| 삭제 | M4 후 검색·백업 | 자료 없음, `backupsPurgedAt` 기록 |

## 9. 관측·감사

- 요청마다 `requestId, tenantId, caseId, purpose, 정책 사유, 단계별 usage, 최종 상태`를 감사 기록에 남긴다. 사건 자료 본문은 로그에 쓰지 않는다(마스킹 후에도).
- 기존 Metric/Trace 체계(MeterRegistry, C16)에 FastAPI 호출 성공·실패·지연·근거 부족 비율을 추가한다.

## 10. 위험과 아직 모르는 것

- memvid 어댑터의 안정성(동시 쓰기, 대용량, 파일 손상 복구)은 **측정 전**이다. H2의 테스트가 첫 근거가 된다.
- 로컬 임베딩 품질은 실제 법률 문서로 측정해야 한다. 지금은 품질을 단정하지 않는다.
- memvid가 사건 단위 파일 수천 개에서 어떻게 동작하는지는 모른다. 상용화 전에 부하 시험이 필요하다.
- 개인정보·법률 자료의 보관 기간과 삭제 의무는 **변호사·법무 검토가 필요**하다. 이 문서는 기술 설계이고 법적 판단이 아니다.

## 11. 멀티테넌시 (판매 시작 시 필수, 2장·4장 보강)

테넌트 = 개인 변호사 또는 로펌 하나. 아래는 "토큰에서 Tenant ID만 확인하면 끝"이 아니라 **데이터가 지나가는 모든 곳**에서 격리를 지키는 목록이다.

| 위치 | 규칙 |
|---|---|
| 요청 | 내부 토큰의 `tenantId`가 유일한 기준이다. 본문·경로·쿼리의 `tenantId`는 신뢰하지 않고 토큰과 다르면 `TENANT_MISMATCH` |
| Spring DB | 모든 업무 테이블에 `tenant_id` 컬럼, 모든 조회 조건에 필수, 복합 UNIQUE에 포함. 테넌트 없는 조회 메서드는 만들지 않는다 |
| memvid | 파일 경로 `tenants/<tenantId>/cases/<caseId>`를 서버 매핑표로만 결정(4장). 캐시 키에 `tenantId` 포함 |
| **마스킹 매핑표** | **테넌트마다 따로 저장하고 따로 암호화한다.** 한 테넌트의 `[이름1] ↔ 원문` 매핑이 다른 테넌트 요청에 쓰이지 않는다. 매핑표 자체가 가장 민감한 자료이므로 로그·백업·프롬프트에 넣지 않는다 |
| 암호화 키 | 테넌트별 데이터 키(DEK)를 두고 상위 키(KEK)로 감싼다. 테넌트 해지 시 키 폐기로 복구 불가 삭제를 보강한다 |
| 한도 | 속도 제한·예산·동시 호출 상한을 **테넌트별**로 둔다(한 테넌트의 폭주가 다른 테넌트를 막지 않게) |
| 로그·감사 | 모든 기록에 `tenantId`. 사건 자료 본문은 기록하지 않는다. 운영자 화면도 테넌트 범위 안에서만 집계 |
| 백업·삭제 | 테넌트 단위 백업·복원·삭제. 삭제는 4장 M4의 `backupsPurgedAt`까지 포함 |

격리 테스트(8장 격리 행)에 **테넌트 A가 B의 사건 ID를 알아도 접근 불가**, **A의 마스킹 매핑이 B의 응답에 나타나지 않음**, **한쪽 한도 소진이 다른 쪽에 영향 없음**을 추가한다. 격리가 완성되었다고 말하려면 이 테스트가 통과하고 외부 검토(침투 시험 등)를 거쳐야 한다. 설계만으로 끝났다고 보지 않는다.

## 12. 과금·정산 (기존 비용 통제 위에 얹기)

기존 예산 장부(예약·정산·반환)를 **고객 과금의 원천 데이터**로 쓴다. 비용 통제와 과금은 같은 장부를 보되 역할이 다르다. 비용 통제는 "넘으면 막는다", 과금은 "쓴 만큼 청구한다."

| 항목 | 설계 |
|---|---|
| 요금제 | 기본 요금제(월 정액, 포함 크레딧) + 크레딧 충전(팩). 단계별 단가(Tiered)는 포함량 초과분에 적용 |
| 크레딧 | 1 크레딧 = 정해진 원화 가치. **LLM 실비용 + 검색·저장 비용 + 마진**으로 단가 산정. 모델·공급자 단가가 바뀌면 단가표만 바꾼다(코드 상수 금지) |
| 미터링 | 요청마다 `tenantId, 단계, usage, costCredits`를 장부에 기록(5장 정산). 과금은 이 기록의 월 집계다. 정산 실패·미확정(`UNSETTLED`)은 청구에서 제외하고 확정 후 반영 |
| 한도 | 크레딧 소진 시 새 요청 거부(`CREDIT_INSUFFICIENT`), 진행 중 요청은 완료 후 정산. 잔액 확인과 예약은 원자적으로 |
| 대시보드 | 테넌트별 월 사용 크레딧, 요청 수, 차단 사유, 남은 크레딧. 기존 운영자 화면(09~13)의 테넌트 뷰로 확장 |
| ROI 화면 | "이번 달 접수된 문의 수 · 상담 전환 수 · 사용 크레딧"을 **나란히 보여 주는 지표**. 수익을 추정하거나 보장하는 문구는 쓰지 않는다 |
| 결제 | 결제 대행(PG) 연동과 세금계산서는 외부 계정·법적 절차가 필요해서 외부 계정과 법적 절차가 필요하므로 별도 절차로 진행한다 |

주의:
- 처음 받은 제안의 "이탈률이 제로에 수렴"은 근거가 없는 표현이다. ROI를 보여 주면 이탈이 줄 **가설**이 있을 뿐이고 실측 후에 판단한다(9장 7장 H9와 같은 원칙).
- 변호사 마케팅·의뢰인 유입을 다루는 기능(유입 수, 광고 연계)은 **변호사 광고·수임 관련 규정 검토가 먼저**다. 기술 설계 범위 밖이며 법무 확인 전에는 유입 집계를 "내부 통계"까지만 둔다.

## 13. 1차 스크리닝 유스케이스 · 퍼널 지표 · 정산 API

### 13.1 유스케이스 (DDD 핵심 유스케이스 추가안)

"문의 접수 → 1차 스크리닝 초안 → 변호사 검토 → 상담 예약 → (변호사 입력) 수임".

| 단계 | 도메인 이벤트 | 누가 | 비고 |
|---|---|---|---|
| 접수 | `INTAKE_SUBMITTED` | 의뢰인 | 기존 C03 |
| 초안 | `SCREENING_DRAFT_READY` | 시스템(M2·M3) | 근거·출처 포함, `reviewRequired=true` |
| 검토 | `LAWYER_REVIEWED` | 변호사 | 승인·보완·반려 |
| 예약 | `CONSULT_BOOKED` | 의뢰인/변호사 | **새 기능**(현재 38개 API에 예약 없음) |
| 수임 | `RETAINED` | **변호사가 직접 입력** | 수임 여부·금액은 시스템이 알 수 없다 |

### 13.2 메모리는 두 종류다 (memvid 적용 방식)

| 종류 | 내용 | 격리 | 쓰기 |
|---|---|---|---|
| 사건 메모리 | 의뢰인 제출 자료·상담 내용 | 테넌트·사건별 파일(4장, 11장) | 적재(M1) |
| 참조 메모리 | 공개 판례·법령·절차 정보(`R01~R06` 계열) | 테넌트 공통 읽기 전용, 갱신일·출처 필수 | 운영자 갱신만 |

검색(M2)은 `scope=case|reference|both`를 받고, 결과의 `evidence[]`에 어느 메모리에서 왔는지(`memoryKind`)를 표시한다. 판례는 **변호사 화면의 근거 자료**로 쓴다. 의뢰인에게 판례 기반 "진단"을 직접 보여 주는 기능은 만들지 않는다. 비변호사가 법률 판단을 제공하는 것으로 읽힐 수 있고, 이 제품은 상담 준비 정리까지만 한다는 현재 선언(README)과도 충돌한다. **법무 검토 전 설계 제외.**

### 13.3 퍼널 지표와 정산 API (Spring, 테넌트는 JWT에서만 결정)

| API | 설명 | 권한 |
|---|---|---|
| `GET /api/analytics/funnel?from&to` | 단계별 건수와 단계 간 전환율(접수 → 초안 → 검토 → 예약 → 수임 입력) | 테넌트 소유 변호사·ADMIN |
| `GET /api/analytics/cost-per-outcome?from&to` | 접수 1건당·예약 1건당 사용 크레딧 | 동일 |
| `GET /api/billing/plan` | 요금제, 포함 크레딧, 남은 크레딧 | 동일 |
| `GET /api/billing/usage?month=` | 월 사용 요약(단계별 크레딧, 차단 건수) | 동일 |
| `GET /api/billing/ledger?month=&page=` | 장부 행(요청 ID, 단계, 크레딧, 상태) | 동일 |
| `POST /api/billing/credit-packs` | 크레딧 충전(결제 연동 후) | 테넌트 소유자, 결제 연동은 별도 절차 |
| `POST /api/outcomes/{intakeId}/retained` | 수임 여부·금액 입력(선택) | 배정 변호사 |

- "수임 매출 대비 LLM 비용" 지표는 **변호사가 입력한 금액**이 있을 때만 계산한다. 입력이 없으면 비용만 보여 주고 매출은 "미입력"으로 둔다. 시스템이 수임 매출을 추정하지 않는다.
- 지표는 집계 숫자만 낸다. 문구는 "전환 N%, 예약 1건당 M크레딧"처럼 사실만 쓴다. "통화 시간 80% 절감"과 "이탈 방지" 같은 효과는 **실측 후에** 주장한다(지금은 가설).
- **고액 사건만 골라 잡는 자동 선별**은 설계에서 뺀다. 의뢰인 접근성과 변호사 윤리 규정의 쟁점이 될 수 있다. 대신 변호사 목록에는 "정보 충족도"(자료가 얼마나 채워졌는지)와 "긴급도"(기한 신호)만 표시한다. 수임 가치 기준 정렬은 법무 확인 후 재검토.
- 마케팅 유입 지표는 11장·12장 주의대로 변호사 광고 규정 확인 전에는 내부 통계까지만 둔다.

### 13.4 상담 요약 파이프라인 (M3의 내부 단계)

모델 호출은 **한 요청에 한 번**이다. 나머지는 코드가 한다.

| 단계 | 담당 | 내용 |
|---|---|---|
| 0 입력 구조화 | 코드 | 접수 필드(분류, 사실, 기한, 자료 목록)를 마스킹된 구조화 데이터로 만든다 |
| 1 근거 검색 | 코드 | M2 검색, 사건 메모리 우선(필요하면 참조 메모리). 각 근거에 `evidenceId` |
| 2 요약 생성 | **모델 1회** | 고정 시스템 프롬프트 + 구분자로 감싼 데이터. 근거 본문은 "지시가 아니라 자료"로 명시. JSON 스키마 출력 |
| 3 검증 | 코드 | 스키마, `evidenceId` 존재, 금액·날짜가 해당 청크에 실제로 있는지, 금지 표현(승소 가능성·결론 단정), 남은 개인정보 패턴. 실패 시 **복구 재시도 최대 1회**(예산에 포함), 그래도 실패면 `MODEL_INVALID_JSON` |
| 4 저장 | Spring | 출력 Guard → Privacy 마스킹 → `DRAFT`로 저장(변호사 승인 대기) |

출력 섹션: 사건 개요 / 쟁점 후보(질문 형태) / 확인된 사실(각 주장 → `evidenceId`) / 불명확한 점·추가 자료 요청 / 기한 신호. **결론, 승소 가능성, 법률 판단은 쓰지 않는다**(검증 3단계에서 거른다).
프롬프트는 파일로 버전 관리한다(`prompts/summary_v1.md`). 초안에는 프롬프트 버전·해시, 모델명, `memoryVersion`을 함께 저장해 나중에 재현·감사할 수 있게 한다.

### 13.5 저장 구조 (Repository)

Python은 **업무 DB에 쓰지 않는다.** 저장은 Spring 쪽이다.

| 테이블 | 핵심 컬럼 | 비고 |
|---|---|---|
| `screening_draft` | `id, tenant_id, intake_id, version, status(DRAFT/APPROVED/REJECTED/SUPERSEDED), prompt_version, memory_version, model, created_at, reviewed_by, reviewed_at` | 복합 UNIQUE `(tenant_id, intake_id, version)` |
| `screening_claim` | `id, draft_id, tenant_id, text, supported(bool)` | `supported=false`는 변호사 화면에서 강조 |
| `screening_claim_evidence` | `claim_id, evidence_ref_id` | 주장과 근거 연결 |
| `evidence_ref` | `id, tenant_id, case_id, document_id, document_version, chunk_id, quote_masked(짧게), quote_hash, doc_date` | 원문 전체는 저장하지 않는다 |
| `funnel_event` | `id, tenant_id, intake_id, type, at, actor` | 13.1 이벤트를 그대로 기록 |
| `outcome_record` | `tenant_id, intake_id, retained, amount(선택), entered_by, entered_at` | 변호사 입력 |
| `billing_ledger` | `id, tenant_id, request_id, stage, usage, credits, status(RESERVED/SETTLED/RELEASED/UNSETTLED)` | 12장 |

Python 쪽 저장 구조: `CaseRegistry`(경로 매핑), `MemoryStore`(memvid), `PromptStore`(버전 파일). 모두 파일·메모리이고 업무 DB 접속 정보를 갖지 않는다.

### 13.6 DDD 상·중·하 매핑 (의뢰인 상담 요청 → 변호사 예약)

| 층 | 구성 | 이 흐름에서 하는 일 |
|---|---|---|
| 상(진입) | Controller, 인증·DTO, 요청 서명 | C03 접수, 요약 요청, 검토 승인, 예약, 수임 입력, 지표 API |
| 중(업무·정책) | `Intake`, `ScreeningDraft`, `Consultation(예약)` 애그리거트, Guard·비용·권한 정책 | 상태 전이와 규칙. `INTAKE_SUBMITTED → SCREENING_DRAFT_READY → LAWYER_REVIEWED → CONSULT_BOOKED → RETAINED` |
| 하(저장·외부) | JPA 저장소, `FastApiMemoryClient`, 결제·알림 어댑터 | 저장, FastAPI 호출, 정산. Python과 memvid는 이 층 바깥의 실행 영역 |

규칙: 이벤트 발행은 중간 층(애그리거트)에서만 한다. 상 층은 이벤트를 만들지 않고, 하 층은 이벤트를 저장만 한다.

### 13.7 동적 가드 보강 (설계 제안, 미검증)

세션 단위 누적 점수만으로는 세션을 바꾸거나 질의를 쪼개서 들어오는 대량 추출 시도를 막기 어렵다. 아래를 설계한다. 효과는 공격 시나리오 테스트로 측정한 뒤에만 주장한다.

- 위험 상태를 프로세스 메모리 밖의 공유 저장소로 옮기고 만료 시각을 둔다.
- 누적 키를 세션 + 사용자 + 테넌트로 넓힌다. IP는 보조 신호로만 쓴다(프록시·공유 IP 오탐 위험).
- 신호: 짧은 간격의 유사 질의 반복, 서로 다른 사건 ID 시도 횟수, 근거 전문·대량 인용 요구 패턴, 이미 차단된 요청의 반복.
- Python도 토큰 한도(`topK`, 호출 수, 인용 길이)를 **독립적으로** 강제한다. 앞단 필터가 뚫려도 대량 추출이 되지 않게 하기 위함이다.
- 운영자 화면 표시는 먼저 조회(폴링)로 두고, 실시간 푸시는 필요가 확인된 뒤에 추가한다.
- 이벤트 이름(제안): `IntrusionScoreCalculated`, `SecurityThresholdExceeded`, `SessionBlocked`, `OperatorAlertReported`. 발행은 업무 애그리거트 층에서 하고 하 층은 저장만 한다.

### 13.8 NeMo Guardrails Python 액션 제안 (변호사 시장용, 설계 단계)

현재 `nemo-colang/main.co`는 Python 액션 없이 입력·출력 검사를 모델 분류(`gpt-4o-mini`)로만 한다. 아래는 **코드로 판정하는 액션**을 먼저 두고, 애매한 경우에만 모델에 묻는 구조다. 액션은 네트워크를 쓰지 않고, 같은 입력이면 같은 결과이며, 단위 테스트가 쉬워야 한다. 판정 근거가 되는 맥락(`evidenceIds`, `tenantId`)은 Spring 클라이언트가 NeMo 호출 시 함께 넘긴다(현재는 텍스트만 넘김).

| 우선 | 액션 | 하는 일 | 변호사에게 쓸모 | 사유 코드(제안) |
|---|---|---|---|---|
| 1 | `verify_citations` | 출력의 판례·법령 인용(사건번호 형식, 법원명, 조문)이 이번 요청의 근거 목록(`evidenceIds`)에 있는지 확인. 없으면 환각 인용으로 차단 | **판례 환각**이 법률 AI의 가장 큰 사고. 근거 없는 인용을 변호사 화면에 못 올리게 함 | `FABRICATED_CITATION` |
| 2 | `detect_outcome_promise` | "반드시 승소", "100%", "무조건 이긴다" 등 결과 보장·단정 표현을 버전 관리되는 표현 목록과 정규식으로 탐지 | 광고·윤리 규정과 직결. 의뢰인에게 결과를 약속하는 문구 차단 | `OUTCOME_PROMISE` |
| 3 | `check_output_scope` | 출력에 남은 개인정보 패턴(주민번호·계좌·전화·이메일), 다른 사건·테넌트의 식별자, 마스킹 자리표시자 원문 노출을 검사 | **의뢰인 비밀 유지**. 다른 사건 자료가 섞이는 사고를 마지막에 한 번 더 거름 | `SCOPE_LEAK` |
| 4 | `extraction_signals` | 질의 쪼개기·반복, 서로 다른 사건 ID 시도, 근거 전문 요구 패턴을 **신호로 반환**(점수 누적은 Spring 쪽) | 경쟁 로펌·크롤러의 대량 추출 탐지 | `EXTRACTION_PATTERN` |
| 5 | `conflict_hint` | 접수된 상대방 이름의 **해시**(테넌트 키로 HMAC)를 기존 의뢰인 목록 해시와 비교해 이해충돌 가능성을 변호사에게만 알림 | 이해충돌 확인은 실제 의무. 이름 원문을 저장하지 않고 비교 | `CONFLICT_HINT` (차단 아님, 알림) |
| 6 | `legal_judgment_phrase` | 의뢰인용 응답의 법률 판단·진단 문구("~이므로 위법입니다")를 코드로 탐지, 모호하면 모델 보조 | 13.2의 "진단 제외" 규칙을 코드로 강제 | `LEGAL_JUDGMENT` |

설계 규칙:
- **입력 쪽 신호만 Dynamic Guard 점수에 더한다.** 출력 쪽 차단(1·2·3·6)은 모델이 낸 문제이지 사용자의 공격이 아니므로 세션 누적에 넣지 않고 기록·지표만 남긴다(무고한 사용자가 차단되는 것을 막기 위해).
- 누적(세션·사용자·테넌트)은 NeMo 안이 아니라 Spring의 Dynamic Guard가 한다. 액션은 판정만 하고 상태를 갖지 않는다.
- 점수표에는 새 사유 코드를 추가한다(예: `EXTRACTION_PATTERN` 40, `SCOPE_LEAK`은 점수 없음·즉시 차단 후 알림). 값은 시험으로 조정한다.
- 표현 목록과 인용 패턴은 변호사의 검토를 받아 확정한다. 지금 목록은 **초안이고 정확도를 측정하지 않았다.**
- 비용 효과(모델 호출 감소)는 가설이다. 적용 전후의 호출 수로 측정한 뒤 말한다.
- Colang 2.x에서 Python 액션을 호출하는 문법과 컨텍스트 전달 방식은 사용 중인 NeMo 버전의 문서로 확인한 뒤 구현한다(미확인).
