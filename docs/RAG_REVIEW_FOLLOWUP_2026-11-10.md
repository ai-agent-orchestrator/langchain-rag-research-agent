# RAG 검수 후속: 기존 구현과 검색→생성 연결

2026-11-10 KST. 사용자 첨부 R-04~8절과 후속 상태 표를 기준으로 정리했다.
작업: langchain-rag-research-agent, feat/day-2026-11-10, 기준 eac4fda.
기존 보안 action과 B03~B05 뼈대가 있다는 사실을 전체 연결 완료로 표시하지 않는다.
legal-intake 원본 작업 폴더의 미커밋 RAG/앱 조립 변경은 읽기만 했고 수정하지 않았다.

## 이번에 구현·연결한 것

- rag/guidance.py: Library.search → 기존 RelevanceRule/to_result → 검색 결과를
  B03 EvidenceLike로 변환 → 기존 B04 graph/B03 chain → DTO 검증 → answer 조립.
- 입력 정책 후 필드별 마스킹. clientName은 읽거나 질의/모델/그래프 상태에 넣지 않는다.
  검색 자료 정책과 출처/본문 해시를 확인하고, 모델에 보낼 본문·제목과 출력의 모든
  DTO 필드를 검사/마스킹한다. 인용은 실제 검색 근거의 부분집합이어야 한다.
- BLOCKED는 검색/생성 0회. EMPTY/BELOW_THRESHOLD는 고정 안내, 생성 0회,
  model=not-invoked. 검색 장애/출처 불일치는 RetrievalUnavailable로 올라가며
  무근거 안내로 바꾸지 않는다. HTTP 503 매핑은 이후 서비스 어댑터 책임이다.
- 동기 검색·chain은 전용 BoundedWorker에서 실행한다. 대기열/동시성 한도,
  응답 timeout/취소와 실제 슬롯 반환 분리, 늦게 끝난 작업 예외 회수.
  스레드가 실제 끝난 뒤 슬롯을 반환한다. 요청 tracing context도 복사한다.
- ainvoke 전체에 serving_trace_guard 적용. 개인정보를 포함한 합성 입력에서
  동기 worker→검색→graph→chain의 LangSmith 업로드 시도 0을 검증했다.
- 기본 enabled=False. 모델 로딩/선택을 하지 않고 주입만 받는다. 근거가 있지만
  모델이 없으면 BACKBONE_NOT_CONFIGURED로 명시적으로 거절한다. 자동 fake fallback 없음.

## 시험

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

**234 passed, 1 failed, 5 skipped in 25.52s**, 종료 코드 1.
신규 연결 시험 12개 + 전용 worker 시험 3개는 통과했다. 기존 구조 8개 포함.
기존 시험 기대값·skip·KNOWN_DEBT를 바꾸지 않았다.

실패: tests/test_index_lifecycle.py::test_versions_rollback_and_prune.
실제 memvid put_many 재시도 뒤 Tantivy index writer unavailable로 실패했다.
이전부터 관찰된 SDK/Windows 쓰기 문제이며 근본 원인은 미확정이다.
사용자 지시에 따라 수정·재시험하지 않았다. skip은 기존 Chroma 4개/Kiwi 1개다.

새 시험은 fake chat model, 제어된 검색 결과, 실제 Library.search 표면+fake 임베더와
메모리 색인으로 연결을 확인한다. 실제 Llama·실제 E5·실제 Chroma 연결 품질을 뜻하지 않는다.
유료 API·모델 다운로드·NeMo/키위 설치·실제 접수·LangSmith 업로드는 실행하지 않았다.

## R-01~R-21 판단과 상태

R-01~R-03의 지적 본문은 이번 첨부에 없으므로 후속 표와 현재 공개 계약만 근거로 한다.

| 항목 | 판단 | 현재 근거와 남은 범위 |
| --- | --- | --- |
| R-01 보안 선행 | 수용·일부 연결 | legal-intake 정본 action은 기존 구현. 이번 연구 pipeline은 canonical package로 검사/마스킹. 운영 API 연결은 여전히 범위 밖 |
| R-02 질의 계약 | 수용·기존 계약 사용 | core.build_query와 clientName 제외를 연결 시험으로 확인. 원문 누락 부분/실제 접수 적합성은 별도 검토 |
| R-03 실행 환경 | 보류·기존 분리 유지 | 연구 Python 3.12 .venv 사용. legal-intake 환경·lock 통합은 하지 않음 |
| R-04 원격 tracing | 수용·연결 검증 | 기존 serving_trace_guard를 실제 검색/worker/chain/graph 전체에 적용, 합성 PII 업로드 0 시험 통과 |
| R-05 관련성 판정 | 수용·일부 | 절대 점수+상위 두 문서 간격의 명시적 RelevanceRule 사용. 이번에는 임계값을 재보정하지 않음. 실제 모델별 보정은 별도 |
| R-06 평가 통계 | 수용·일부 | 기존 v2 등급/quote/유형·split/부트스트랩 및 무작위 기준선 부품 존재. 실제 모델 비교나 Wilson 보고서까지 완료한 것은 아님 |
| R-07 SDK 스파이크 | 수용·기존 증거 | legal-intake에 B02a/B02b 이력과 memvid 우회 검증이 있음. 이번에 재실행하지 않았고 Windows 쓰기 실패는 계속 관찰됨 |
| R-08 버전·무결성 | 수용·일부 | 기존 버전 manifest/포인터/해시 및 이번 반환 근거 무결성 검사. 청크 ID의 모든 버전 변경 반영·서재 증분 원자성은 별도 과제 |
| R-09 timeout·슬롯 | 수용·연구 실행기 추가 | 전용 풀·대기열·실제 종료 후 슬롯 반환 시험 통과. 실제 Llama 취소/강제 종료·GPU 부하 검증은 O2 이후 |
| R-10 Llama·계약 | 수용·일부 | 기존 chain 하나에 모델 주입, 정상/차단/무근거 결과 계약 시험. 모델 ID/양자화/서빙 방식 O2 미확정 |
| R-11 기본 OFF·회귀 | 수용·일부 | 연구 pipeline 기본 OFF, 생성 chain 지연 구성. 기존 FastAPI/lifespan은 수정하지 않았고 RAG_ENABLED 연결은 하지 않음 |
| R-12 DTO→answer | 수용·연결 검증 | 모든 DTO 출력 필드 검사·마스킹, 실제 검색 출처로 참고자료 조립. 부분집합 검사가 내용 충실성 증명은 아님 |
| R-13 장애≠무근거 | 수용·연결 검증 | EMPTY/BELOW_THRESHOLD는 생성 0회. 장애·출처 불일치는 예외, 실제 HTTP 503 매핑 미연결 |
| R-14 Llama·하드웨어 | 보류 | O2 미확정. 과거 하드웨어 기록을 현재 모델 적합성 실측으로 취급하지 않음 |
| R-15 문서 불일치 | 수용·범위 유지 | 이 후속 보고서에서 현재 연구 범위를 명시. 별도 작업 중인 README와 legal-intake 문서는 수정하지 않음 |
| R-16 미커밋 변경 | 보류·보존 | 원본 legal-intake의 환경/앱 조립 변경과 연구 README 변경을 보존. 임의 커밋·되돌리기 안 함 |
| R-17 적재 시 자료 정책 | 보류 | 이번 연결은 요청 시 위험 자료를 제외. 적재 정책 버전·manifest 결합으로 전환하는 최적화는 미구현 |
| R-18 rail p95 | 보류 | 실제 NeMo 지연 분포·버전 재해결 측정은 이번 범위 밖 |
| R-19 로컬 자원 게이트 | 수용·일부 | USD 예산을 연결하지 않고 물리 동시성/시간 한도만 둠. 실제 모델 토큰·GPU/세션 요청률은 미검증 |
| R-20 tokenizer 한도 | 수용·기존 부품 | E5 최종 입력 토큰 검사 부품은 기존 구현. 이번에 실제 tokenizer를 로드/재분할하지 않음 |
| R-21 API 집계 | 보류·추가 API 0 | 연구 Python 인터페이스만 추가. 사용자 정의 업무 API 집계 규칙/운영 앱 선택은 기존 앱 설계에서 확정할 항목 |
| 4절 학습 실험 | 수용·일부 | 연구 서재 RRF·비교/보정·v2 도구는 기존 구현. 실제 E5/RRF/가중식/Llama 품질 비교를 모두 수행한 것은 아님 |
| 5절 모듈 구조 | 수용·연구 구조 유지 | 재사용 부품은 연구 저장소에 두고 rag에서 조립. legal-intake app/rag로 다시 복사하지 않음 |

## 연구용 호출 계약

```python
from rag_research_agent.rag.guidance import GuidancePipeline
from rag_research_agent.retrieve.gate import RelevanceRule
from rag_research_agent.core.contracts import RetrievalMode

# library는 열린 연구 서재, model은 소유자가 선택해 준비한 BaseChatModel.
# tau_abs/tau_gap은 해당 모델·검색 모드·버전의 compare에서 고정한 값이어야 한다.
rule = RelevanceRule(RetrievalMode.VECTOR, tau_abs, tau_gap, "frozen-rule-version")
pipeline = GuidancePipeline(library, rule, index_version="verified-index-version",
                            model=model, model_id="explicit-model-version", enabled=True)
try:
    reply = await pipeline.ainvoke({"caseType": "CIVIL", "coreStatement": "합성 상담 자료"})
finally:
    await pipeline.aclose()
```

작업 스레드는 강제 종료하지 않는다. 무한 정지 작업이면 슬롯과 aclose 대기도 계속될 수
있으므로 실제 Llama의 provider timeout/프로세스 격리·종료 정책은 O2 결정 시 확정해야 한다.
한 worker는 한 이벤트 루프에서 사용하며 외부 worker를 주입했으면 소유자가 종료한다.
실제 데이터 투입·기존 guidance API 연결·Llama 운영 완료로 표시하지 않는다.
