# Chroma 통합 경로 재확인 — 2026-11-10 KST

AGENTS.md와 결정 문서를 먼저 읽고 개발 기본 저장소 Chroma를 유지했다. 생산 코드·기존 시험·retry·데이터·프로필·frozen masking 변경 없이 경로만 재확인했다. 런타임 결과·임시 서재·재현 harness는 `.runs/chroma-recheck-20261110/`에만 저장했다. 새 설치/다운로드/실제 모델/LLM/LangSmith 업로드 없음.

## 커밋 전제 및 동시 작업

요청한 AGENTS.md, DECISION_STORE_CHROMA_2026-11-10.md, FUTURE_MEMVID_BUFFER_SPIKE_2026-11-10.md는 시작 시 이미 ce9c8c9에 커밋되어 있었다(당시 커밋에는 다른 보고서 2개도 포함). 세 파일에 미커밋 diff가 없어 새 커밋으로 재작성하거나 내용 수정하지 않았다. 작업 중 별도 진단 작업의 fd36ca0 커밋이 생겼으며 그 변경을 되돌리거나 이번 문서 커밋에 다시 넣지 않았다. README는 작업 시작 SHA-256과 같으며 이번 커밋에서 제외했다.

## 환경과 실행 통제

Python 3.12.10, Chroma 1.5.9, sentence-transformers 6.2.0(설치 메타데이터만 조회), langchain-core 1.7.6. 경로 재확인 프로세스에서 sentence_transformers/transformers/memvid_sdk import를 차단하고 socket connect/connect_ex/getaddrinfo를 차단했다. HF_HUB_OFFLINE=1, TRANSFORMERS_OFFLINE=1 및 tracing 비활성 설정을 사용했다. Chroma는 외부 fake 임베딩만 받는다. 모든 E5/E7 설정은 split compare이며 confirm 선택·실행은 하지 않았다.

## 경로 결과

| 경로 | 실제 Chroma 서재 + fake 임베더 | 근거/한계 |
| --- | --- | --- |
| E5 --chunk-size 64 --overlap 16 | 실패 | 평가 후 TemporaryDirectory 정리에서 WinError 32; report.json 저장 전 중단 |
| E7 --retrieval lex | 실패 | 같은 정리 오류; CLI exit 1 |
| E7 --retrieval vector | 실패 | 같은 정리 오류; CLI exit 1 |
| E7 --retrieval rrf | 실패 | 같은 정리 오류; CLI exit 1 |
| E7 --retrieval weighted | 실패 | 같은 정리 오류; CLI exit 1 |
| E3 E7-vector 보고서 → 내보내기 | 실패 | E7 실패로 report.json 없음; 내보내기 CLI exit 2. E3 자체 결함이라는 뜻 아님 |
| E3 독립 로컬 내보내기 | 통과 | E1 persisted Chroma 서재를 fake로 재열기·vector 검색 → score_item → 실제 export CLI. 합성 문항 1개 dataset/experiment JSONL과 ID/metric 확인. 업로드 없음 |
| E1 LibraryRetriever | 통과 | 실제 서재 build/close/open 후 lex/vector/hybrid 각각 공개 Library.search와 본문·chunk/document/title/score/rank 비교 |

## 실패 원인과 재현

E5/E7 traceback은 `scripts/eval_retrieval_v2.py:51`의 TemporaryDirectory 종료 → tempfile/shutil 정리 → Chroma HNSW `data_level0.bin` unlink에서 PermissionError [WinError 32]다. 현재 ChromaIndex.close는 `_col = None`만 수행한다. 관찰로 입증되는 것은 정리 시 파일 사용 중이라는 사실이며, 정확한 핸들 소유자/SDK 내부 원인은 미검증이다. 다른 프로세스 때문이라고 단정하지 않는다. 오류는 모델·memvid import·네트워크 차단에서 발생한 것이 아니다. 소스/close/retry/정리 정책을 고치거나 우회해 통과로 바꾸지 않았다. E5/E7 실패 경로는 재시험하지 않았다.

저장소 루트에서 다음은 결과에 기록한 실제 명령이다. 첫 명령 전체 harness 재실행은 실패 경로도 다시 돌리므로 **이 작업에서 재실행하지 않았다**. 개별 CLI 명령은 네트워크·모델 import 차단 wrapper를 포함한다.

```powershell
.\.venv\Scripts\python.exe .runs/chroma-recheck-20261110/run_recheck.py
.\.venv\Scripts\python.exe .runs/chroma-recheck-20261110/check_export.py
.venv\Scripts\python.exe .runs\chroma-recheck-20261110\run_recheck.py cli scripts/eval_retrieval_v2.py --set data/golden_retrieval/terms_v2.json --embedder fake --split compare --chunk-size 64 --overlap 16 --out .runs/chroma-recheck-20261110/e5
.venv\Scripts\python.exe .runs\chroma-recheck-20261110\run_recheck.py cli scripts/eval_retrieval_v2.py --set data/golden_retrieval/terms_v2.json --embedder fake --split compare --retrieval lex --out .runs/chroma-recheck-20261110/e7-lex
.venv\Scripts\python.exe .runs\chroma-recheck-20261110\run_recheck.py cli scripts/eval_retrieval_v2.py --set data/golden_retrieval/terms_v2.json --embedder fake --split compare --retrieval vector --out .runs/chroma-recheck-20261110/e7-vector
.venv\Scripts\python.exe .runs\chroma-recheck-20261110\run_recheck.py cli scripts/eval_retrieval_v2.py --set data/golden_retrieval/terms_v2.json --embedder fake --split compare --retrieval rrf --out .runs/chroma-recheck-20261110/e7-rrf
.venv\Scripts\python.exe .runs\chroma-recheck-20261110\run_recheck.py cli scripts/eval_retrieval_v2.py --set data/golden_retrieval/terms_v2.json --embedder fake --split compare --retrieval weighted --out .runs/chroma-recheck-20261110/e7-weighted
.venv\Scripts\python.exe .runs\chroma-recheck-20261110\run_recheck.py cli scripts/export_langsmith.py --set data/golden_retrieval/terms_v2.json --results .runs/chroma-recheck-20261110/e7-vector/report.json --out .runs/chroma-recheck-20261110/e3
```

원본 traceback·exit code·전체 명령: `results.json`, `e5.log`, `e7-*.log`, `e3.log`. E1 본문/metadata 비교: `results.json`; E3 독립 검증: `export-isolated.json`, `e3-isolated/set.json`, `results.json`, `export/*.jsonl`. 보고서 수치나 fake 검색 품질로 실제 모델 품질을 주장하지 않는다.

## 전체 시험과 환경 영향

필터 없는 전체 시험을 한 번 실행했다. **257 passed, 2 failed, 1 error, 1 skipped (26.97s)**. JUnit 총 261개. 로그: `pytest.log`, `pytest.xml`, `pytest-summary.json`.

```powershell
$env:HF_HUB_OFFLINE='1'
$env:TRANSFORMERS_OFFLINE='1'
$env:LANGSMITH_TRACING='false'
$env:LANGCHAIN_TRACING_V2='false'
$env:PYTHONDONTWRITEBYTECODE='1'
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=.runs/chroma-recheck-20261110/pytest-tmp --junitxml=.runs/chroma-recheck-20261110/pytest.xml
```

- ERROR: tests/test_memvid_store.py::test_publish_verifies_every_chunk_and_activates_pointer setup. MV999 Tantivy index writer unavailable → RetrievalUnavailable.
- FAILED: tests/test_memvid_store.py::test_many_chunks_survive_batched_writes. 동일한 MV999 write failure.
- FAILED: tests/test_rag.py::test_control_environment_alone_would_trace. 내가 설정한 LANGCHAIN_TRACING_V2=false가 fixture의 LANGSMITH_TRACING=true 대조를 막았다. 실행 환경을 설정한 내 실수이며 생산 코드 회귀라고 해석하지 않는다.

tracing 대조 시험 하나만 LANGCHAIN_TRACING_V2를 제거한 뒤 단독 실행: **1 passed (0.72s)** (`tracing-control.log`). 해당 기존 시험은 가짜 키/localhost:9를 사용하고 업로드 메서드와 외부 소켓을 차단한다. 이후 localhost:9 `/info` 접속 거부 로그가 있었으며 원격 LangSmith 업로드는 하지 않았다. 이 단독 결과로 위 전체 시험 결과를 덮어쓰지 않는다. memvid 실패·error는 재시험·skip·기대값 변경 없이 그대로 유지했다.

```powershell
Remove-Item Env:LANGCHAIN_TRACING_V2 -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_rag.py::test_control_environment_alone_would_trace --basetemp=.runs/chroma-recheck-20261110/tracing-tmp
```

| 전체 시험의 비통과 항목 | 상태 | 메시지 |
| --- | --- | --- |
| `tests.test_kiwi_lab::test_real_kiwi_particles_when_available` | skipped | needs optional kiwi extra; installation is owner-run |
| `tests.test_memvid_store::test_publish_verifies_every_chunk_and_activates_pointer` | error | failed on setup with "rag_research_agent.core.contracts.RetrievalUnavailable: memvid write failed: MemvidError" |
| `tests.test_memvid_store::test_many_chunks_survive_batched_writes` | failure | rag_research_agent.core.contracts.RetrievalUnavailable: memvid write failed: MemvidError |
| `tests.test_rag::test_control_environment_alone_would_trace` | failure | AssertionError: tracing did not activate; the guard test below would be meaningless; assert [] |

## 보호 파일과 미검증

기준 `C:/myLectureWs/rra-p1-stage/merged-protected-before.json`의 보호 18개 모두 작업 전·후 SHA-256 동일. 개별 값: `.runs/chroma-recheck-20261110/protected-sha256.json`. 지침·결정·보류 세 파일 및 README도 시작 SHA-256과 동일하다. 생산 src·기존 시험·data/profiles/frozen masking·legal-intake를 수정하지 않았다. 이번 변경은 조사 문서 2개뿐이다. main 병합 없음.

**미검증**: 실제 E5/BGE-M3 임베딩·E4~E8 모델 품질/성능/선택, 다른 chunk-size/overlap 조합, E5/E7의 보고서 저장까지 완결된 실행, 실패한 E7 보고서를 입력으로 한 E3 연속 성공, 파일 잠금의 직접 원인, memvid 안정화, Chroma와 memvid의 점수/오류/생명주기 전체 동등성. 버전 발행·활성화 포인터·전체 파일 해시 manifest·롤백·동일 파일 변조 거절 계약은 Chroma 경로에 없음. 대표 모델 실행 명령은 기존 LEARNING_E4/E5/E7 및 MODELS.ko.md를 따르며 이 작업에서는 실행하지 않았다.
