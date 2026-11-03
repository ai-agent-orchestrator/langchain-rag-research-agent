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
| M3 | `POST /internal/v1/tasks/{taskType}` | 도메인이 정의한 작업 실행(예: 요약 생성). 코어는 서명·범위·예산·검증 훅만 담당 | `caseId, input(구조화·마스킹됨), stagePlan` | `result`, `claims[]`(각 주장 → evidence 참조), `reviewRequired` |
| M4 | `DELETE /internal/v1/memory/cases/{caseId}` | 사건 파일 삭제·보존 만료 | `reason, requestedBy` | `deleted(bool), backupsPurgedAt` |
| M5 | `GET /internal/v1/health` | 상태 | - | `status, memvidVersion, embeddingModel, openHandles` |

`evidence[]` 한 건의 필드: `evidenceId, caseId, documentId, documentVersion, chunkId, quote(원문 일부), offsets, docDate, ingestedAt, score`.
**출처와 갱신일이 없는 근거는 반환하지 않는다.** `evidenceSufficient=false`면 Spring이 답변 범위를 제한하고(예: "자료가 부족해 확인할 수 없습니다") 모델 호출을 생략할 수 있다.

M3의 규칙(코어가 강제하는 것):
- 결과의 모든 주장(`claims[]`)은 `evidenceId` 하나 이상을 가져야 한다. 없으면 `unsupported`로 표시한다.
- 코드가 검증한다: JSON 스키마, 출처 존재 여부, 수치·날짜가 근거에 실제로 있는지. 모델의 자기 평가는 쓰지 않는다.
- 사람 검토가 필요한 작업은 `reviewRequired=true`로 고정하고, 승인 전에는 최종 사용자에게 나가지 않는다.
- 작업 종류(`taskType`)별 프롬프트·검증 규칙은 도메인 플러그인이 제공한다. 코어는 도메인 지식을 갖지 않는다.

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
6. 충분하면 승인된 단계만 모델 호출 → 도메인 작업 검증(스키마·출처·수치).
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
| H5 | 도메인 작업(M3)과 검증기(스키마·출처·수치) | H3 |
| H6 | 검토 화면과 승인 상태 | H4, H5 |
| H7 | 삭제·보존 만료·백업 정리(M4) | H3 |
| H8 | 운영 준비: HTTPS, 비밀값 관리, 영속 DB·예산 장부, 회원 DB, 관리자 인증 강화 | 별도 |
| H9 | 사용 현황 대시보드(실측 기반) | 실데이터 |

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

## 11. 멀티테넌시 (고객 조직이 둘 이상이면 필수, 2장·4장 보강)

테넌트 = 서로 데이터가 섞이면 안 되는 고객 조직 하나(예: 로펌 하나). 아래는 "토큰에서 Tenant ID만 확인하면 끝"이 아니라 **데이터가 지나가는 모든 곳**에서 격리를 지키는 목록이다.

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

## 12. 동적 가드 보강 (설계 제안, 미검증)

세션 단위 누적 점수만으로는 세션을 바꾸거나 질의를 쪼개서 들어오는 대량 추출 시도를 막기 어렵다. 아래를 설계한다. 효과는 공격 시나리오 테스트로 측정한 뒤에만 주장한다.

- 위험 상태를 프로세스 메모리 밖의 공유 저장소로 옮기고 만료 시각을 둔다.
- 누적 키를 세션 + 사용자 + 테넌트로 넓힌다. IP는 보조 신호로만 쓴다(프록시·공유 IP 오탐 위험).
- 신호: 짧은 간격의 유사 질의 반복, 서로 다른 사건 ID 시도 횟수, 근거 전문·대량 인용 요구 패턴, 이미 차단된 요청의 반복.
- Python도 토큰 한도(`topK`, 호출 수, 인용 길이)를 **독립적으로** 강제한다. 앞단 필터가 뚫려도 대량 추출이 되지 않게 하기 위함이다.
- 운영자 화면 표시는 먼저 조회(폴링)로 두고, 실시간 푸시는 필요가 확인된 뒤에 추가한다.
- 이벤트 이름(제안): `IntrusionScoreCalculated`, `SecurityThresholdExceeded`, `SessionBlocked`, `OperatorAlertReported`. 발행은 업무 애그리거트 층에서 하고 하 층은 저장만 한다.
