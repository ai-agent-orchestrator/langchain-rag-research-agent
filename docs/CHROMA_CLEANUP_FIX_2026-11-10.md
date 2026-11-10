# Chroma 임시 서재 정리 실패 처리 — 2026-11-10 KST

AGENTS.md를 먼저 읽었다. 승인 범위에서 ChromaIndex.close와 평가 스크립트의 보고서 저장·정리 순서만 수정했다. **평가는 보고서를 저장하고 정상 종료하며, 남은 정리 실패는 경고로 보존한다. 모든 파일 잠금이 해소된 것은 아니다.** 실제 모델·다운로드·새 설치·LLM·LangSmith 업로드 없음.

## 확인된 것

기존 `.runs/chroma-recheck-20261110/run_recheck.py cli` wrapper로 fake E5(64/16, compare)를 다시 실행했다. 수정 전에도 TemporaryDirectory 정리에서 HNSW `data_level0.bin` 삭제가 WinError 32로 실패했고 report.json은 없었다. SDK 내부 속성은 **진단에서 읽기만** 했으며 수정 코드에서는 SDK 비공개 API를 호출하거나 공유 캐시를 비우지 않았다.

- 수정 전 ChromaIndex.close 직전: 클라이언트·컬렉션 참조 모두 있음, SDK `_closed=false`, 공유 refcount 4.
- 기존 close 직후: 컬렉션만 None, 클라이언트는 남고 SDK `_closed=false`, refcount 4.
- factory에서 만든 클라이언트 2개(각각 SDK 내부 admin 참조도 생성). 진단 함수 종료·gc 이후 Python client weakref는 모두 소멸했지만 SDK 공유 refcount는 4로 유지됐다.
- 수정 후 같은 Library.build 경로에서 close: 어댑터의 클라이언트·컬렉션은 모두 None, refcount 4→2. gc 이후도 2이며 같은 프로세스에서 폴더 삭제는 WinError 32로 실패했다. `publish_chroma`의 별도 쓰기 클라이언트에는 close 호출이 없는 것을 소스에서 확인했다. 해당 함수는 승인 범위 밖이므로 변경하지 않았다.
- 반대로 **다른 소유자를 명시적으로 닫은 단독 ChromaIndex**는 close 후 Windows에서 같은 경로를 즉시 삭제할 수 있었다. close 두 번 호출도 통과했다. 이는 전체 Library.build의 모든 소유자를 닫았다는 증거가 아니다.

증거: `.runs/chroma-recheck-20261110/cleanup-fix/before-references.json`, `before-traceback.txt`, `after-references.json`, `unit.log`.

## 후보 비교와 적용

| 후보 | 확인·판단 | 적용 |
| --- | --- | --- |
| (a) 공개 client.close + 참조 해제 | 설치된 1.5.9에서 지원. 마지막 소유자가 닫혀야 공유 리소스를 종료하므로, 자신의 close만으로 다른 누락 소유자를 해결하지 못함 | 적용. ChromaIndex 소유 client.close를 호출하고 finally에서 client/collection 참조 해제. 반복 close는 무동작 |
| (b) gc / 짧은 재시도 | gc 후에도 SDK refcount 2가 유지됨. 기다리면 해결된다는 근거 없음 | 미적용. 공용 retry 정책·대기 시간 변경 없음 |
| (c) ignore_cleanup_errors + 경고 | 평가 성공과 삭제 성공을 구분할 수 있음. flag만 사용하면 어떤 파일 정리가 실패했는지 남기기 어려움 | 동등한 좁은 처리 적용: 명시 cleanup 호출의 OSError를 잡고 경고 원문을 보존. 무조건 무시하는 flag는 사용하지 않음 |

공개 close의 공유 소유권 동작은 [Chroma 1.5.9 공식 소스](https://github.com/chroma-core/chroma/blob/1.5.9/chromadb/api/client.py#L590-L624)와 설치된 파일에서 확인했다. 생산 코드는 공개 close만 사용한다.

`eval_retrieval_v2.py`는 기존 점수·검색 계산을 그대로 수행하고, report.json/md/html을 **close와 임시 폴더 정리 전에** 저장한다. finally에서 소유 클라이언트 close를 시도하고 이어 임시 디렉터리를 정리한다. close 예외 또는 삭제 OSError는 단계·경로·예외명·원문·winerror를 표준 경고 로그와 결과 폴더 `cleanup_warnings.jsonl`에 기록한다. 경고 파일 쓰기 자체가 실패하면 로그에 그 오류도 기록한다. 평가·검색·보고서 쓰기 오류는 잡지 않으므로 원래 오류와 비정상 종료가 유지된다. 정리 오류가 그 원래 오류를 덮어쓰지 않는다.

`compare_embedders.py`도 calibration JSON과 비교 문서를 close 전에 저장하고 같은 정리 경고 처리를 사용한다. 모델별 서재는 원래부터 임시 디렉터리가 아닌 결과 디렉터리이므로 삭제를 새로 추가하지 않았다. `compare_retrieval_fusion.py`에는 별도 클라이언트나 임시 폴더 정리 코드가 없고 evaluate를 호출하므로 소스를 바꾸지 않았다. 같은 경로의 경고는 각 evaluate 결과 폴더에 남는다.

평가 계산 본문과 Chroma의 close 외 함수가 변경되지 않았는지 AST 비교도 수행했다(`cleanup-fix/summary.json`).

## 추가 시험과 반복 경로 시험

기존 시험은 수정·삭제·skip하지 않았다. 새 `tests/test_chroma_cleanup.py`의 6개 시험:

1. 임시 폴더 삭제 실패 직전에 report.json 존재를 확인하고, 실패 후에도 JSON/md/html과 경고가 남는지 확인.
2. close 실패에도 같은 보고서 보존·경고 기록 확인.
3. 평가 오류와 close/삭제 오류가 겹쳐도 원래 평가 오류가 전달되고 성공 보고서를 만들지 않는지 확인.
4. fusion 네 설정에서 close 오류가 있어도 개별 보고서와 fusion 집계가 남는지 확인.
5. compare_embedders의 JSON/비교 문서가 close 전에 저장되는지 확인.
6. 실제 ChromaIndex의 공개 close 이후 Windows에서 같은 경로 삭제 및 두 번 close 확인. 다른 소유자는 먼저 닫는 조건.

새 시험: **6 passed (1.52s)**. 실제 Chroma 1.5.9 + fake 임베더, 기존 네트워크·모델 import 차단 wrapper로 6개 경로를 각각 10회 실행했다. 각 반복은 별도 CLI 프로세스/결과 디렉터리를 사용했다. 종료 코드 0뿐 아니라 보고서 JSON, fake/실모델 분리, compare 문항, 옵션, E3의 ID·metric 전달을 확인했다. E3는 같은 반복의 실제 E7-vector report.json을 이어서 입력했다. 아래 성공률은 **평가·내보내기 경로 성공률**이며 삭제 성공률이 아니다.

| 경로 | 보고서·정상 종료 성공 / n | 성공률, Wilson 95% | 삭제 경고가 남은 실행 / n |
| --- | --- | --- | --- |
| E5 chunk-size 64 / overlap 16 | 10/10 | 100%, 72.2–100% | 10/10 |
| E7 lex | 10/10 | 100%, 72.2–100% | 10/10 |
| E7 vector | 10/10 | 100%, 72.2–100% | 10/10 |
| E7 rrf (k=60) | 10/10 | 100%, 72.2–100% | 10/10 |
| E7 weighted (α=.5) | 10/10 | 100%, 72.2–100% | 10/10 |
| E3 E7-vector 연속 로컬 내보내기 | 10/10 | 100%, 72.2–100% | 해당 없음: E3 자체 서재 없음; 선행 vector 경고는 위 행에 포함 |

E5/E7 임시 폴더의 **프로세스 내 삭제 완료는 각각 0/10 (0%, Wilson 95% 0–27.8%)**이다. 50개 정리 경고를 모두 보존했다. 60/60 경로 성공은 이 환경의 소표본 관찰이며 보장이 아니다. 실제 모델 검색 품질이나 장기 실행 성능을 뜻하지 않는다. confirm 설정 선택·실모델 실행은 하지 않았다.

반복별 전체 명령·exit code·검증 결과·경고 원문: `cleanup-fix/repeats.json`. 각 원본 결과: `cleanup-fix/repeats/trial-01`부터 `trial-10`. 요약: `cleanup-fix/summary.json`.

## 재현·검증 명령

저장소 루트에서 실행한다. 모든 결과 경로는 `.runs/chroma-recheck-20261110/` 아래다. 기존 wrapper는 fake 실행에서 모델 import와 네트워크를 차단한다.

```powershell
# 수정 전 실행 결과는 before-* 파일로 보존. 현재 소스로는 수정 후 동작을 확인한다.
.\.venv\Scripts\python.exe .runs/chroma-recheck-20261110/run_recheck.py cli scripts/eval_retrieval_v2.py --set data/golden_retrieval/terms_v2.json --embedder fake --split compare --chunk-size 64 --overlap 16 --out .runs/chroma-recheck-20261110/cleanup-fix/manual-e5

# 6개 경로 × 10회. 개별 전체 명령은 repeats.json.
.\.venv\Scripts\python.exe .runs/chroma-recheck-20261110/cleanup-fix/repeat_paths.py

.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_chroma_cleanup.py --basetemp=.runs/chroma-recheck-20261110/cleanup-fix/unit-tmp

# tracing 환경변수를 설정하거나 삭제하지 않은 기본 환경 그대로 실행.
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=.runs/chroma-recheck-20261110/cleanup-fix/full-tmp --junitxml=.runs/chroma-recheck-20261110/cleanup-fix/full-pytest.xml
```

## 전체 시험·보호 파일

전체 시험 한 번: **266 passed, 0 failed, 0 error, 1 skipped (31.95s)**. memvid 기존 시험도 이번 실행에서는 통과했으나 안정화의 증거는 아니다. 실패를 지우기 위한 재시험은 없었다. 기존 skip은 `tests/test_kiwi_lab.py::test_real_kiwi_particles_when_available`의 선택 Kiwi 의존성 미설치다. tracing 환경변수는 전체 시험 실행 명령에서 설정·삭제하지 않았다. 로그와 JUnit: `cleanup-fix/full-pytest.log`, `full-pytest.xml`.

보호 파일 18개는 기준 `C:/myLectureWs/rra-p1-stage/merged-protected-before.json`의 SHA-256과 **18/18 동일**. 개별 비교: `cleanup-fix/protected-sha256.json`. README의 사용자 변경은 보존하고 커밋에서 제외했다. memvid 코드·data/profiles/frozen masking·기존 시험·legal-intake·공용 retry 정책 변경, 새 패키지 설치, 모델 다운로드, main 병합 없음.

## 미확정·미검증·잔여 위험

- 정확한 네이티브 OS 파일 핸들 소유자와 SDK 내부의 모든 참조 관계는 미확정이다. SDK refcount 누락과 실제 삭제 실패를 함께 관찰했지만 Windows 보안 프로그램 등 모든 요인을 배제하지 않았다.
- 전체 Library.build 소유권 누락은 미해결이다. publish_chroma와 Library._collection 등 다른 클라이언트 생성·종료 수명은 이번 수정 범위 밖이다. 관련 비공개 stop/cache 조작이나 다른 클라이언트 강제 종료는 하지 않았다.
- 정리 실패한 디렉터리와 파일은 남는다. 특히 같은 프로세스에서 평가를 오래 반복하면 디스크·메모리·핸들이 누적될 수 있다. 이번 반복은 별도 프로세스이므로 장기 단일 프로세스에서의 안정성은 **미검증**이다. 프로세스 종료 후 남은 디렉터리를 자동 삭제하는 기능은 추가하지 않았다.
- Chroma 1.5.9의 공개 close를 사용한다. 다른 SDK 버전/OS, 별도 프로세스가 같은 서재를 연 상황, 경고 파일을 쓸 수 없는 실제 운영 장애의 완전한 관측성은 **미검증**이다.
- E5/BGE-M3 실제 임베딩 품질·실행 성능은 **미검증**이다. 이 보고서는 fake 경로 시험만 다룬다.
