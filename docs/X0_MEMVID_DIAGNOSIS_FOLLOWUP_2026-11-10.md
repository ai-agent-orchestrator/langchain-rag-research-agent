# X0 확장 진단 — 2026-11-10 KST

## 결과를 보기 전에 고정한 프로토콜

생산 코드·기존 시험·retry 정책은 변경하지 않는다. 이번 명시 지시의 진단에서만 SDK를 사용하며 Chroma 개발 경로와 분리한다. 보류된 버퍼 spike는 구현하지 않는다.

```powershell
.\.venv\Scripts\python.exe scripts/diagnose_memvid_writes.py --suite followup --trials 30 --locations workspace temp --wait-ms 0 100 500 --previous-handle closed hold-reader --count 24 --label baseline --out .runs/x0
```

대표의 백신 제외 전후 비교에는 같은 OS/Python/SDK·명령·trials를 유지한다. label만 before/after로 바꿔 구분할 수 있다. protocol_sha256에는 label과 실행 UUID가 들어가지 않는다. 환경/조건이 달라지면 같은 프로토콜로 보지 않는다. 이 작업에서 보안 설정은 조작하지 않는다.

12조건 = 위치 2 × 대기 3 × 직전 reader 상태 2. 조건마다 30회, 매회 합성 1024차원 벡터 24개, batch 8, lex 활성화. 조건 순서는 매 라운드 고정된 round-robin이다. 조건마다 seed 1회를 만들어 직전 파일을 확보하되 seed는 성공률에서 제외하고 별도로 저장한다. 실패를 재시도하지 않고 최초 실패와 close 오류를 구분한다.

Wilson 구간은 조건 내 시험이 독립적인 Bernoulli 관찰이라는 가정의 명목 95% 구간이다. 같은 프로세스·OS에서 반복하고 순서도 고정되어 시간적 상관/순서 효과를 배제하지 못한다. 여러 조건 탐색의 다중 비교 보정은 하지 않는다. 구간이 겹치면 차이 불확실로 기록하고, 겹치지 않더라도 인과관계가 확정됐다고 쓰지 않는다.

대기는 sdk.use의 파일 생성 완료 직후부터 첫 put 사이에 적용한다. SDK 내부 생성 중 쓰기에는 적용되지 않는다. hold-reader는 직전 시험의 **다른 파일**에 자체 읽기 핸들을 유지하는 대조군이다. SDK writer는 항상 close를 시도한다. 이를 SDK 내부 핸들 누수의 직접 재현으로 단정하지 않는다. reader를 열지 못한 시험은 조건 미성립으로 분모에서 따로 집계한다.

## 읽기 전용 점유 조사

실패한 경우에만 Windows Restart Manager의 StartSession/RegisterResources/GetList/EndSession으로 같은 .mv2 경로의 점유 프로세스를 조회한다. shutdown/restart/설정 변경/외부 도구 설치는 하지 않는다. put 실패는 close 전후, close에서만 실패하면 close 후에 조사한다. RM은 전체 열린 핸들 목록이 아니며 빈 결과도 핸들이 없다는 증거가 아니다. SDK 내부 Tantivy 임시 파일과 커널/보호 프로세스를 식별하지 못할 수 있다. 현재 프로세스의 핸들 총수도 전후 기록하지만 특정 파일의 핸들 수는 아니다.

## 고정 출력 형식

schema=`rra-memvid-write-diagnostics/2`. `.runs/x0/<label>/<uuid>/`에 diagnosis.json(조건·환경·전체 시험·요약·seed·정리 결과), trials.jsonl(시험마다 flush), summary.md(조건별 n/시도·성공률과 Wilson95·최초 실패 단계·close 오류·시간)를 쓴다. 매 라운드 중간 결과를 저장하고 finished=false로 표시하며, 완료 때만 true다. elapsed_ms는 점유 조회를 포함하고, operation_elapsed_ms는 조회를 제외한 open/wait/put/seal/close 합계다.

사용자 Temp의 SDK 재현 파일은 명시적 위치 대조를 위한 임시 입력/색인이다. 생성한 루트의 절대 경로가 예상 위치 안인지 검증한 뒤 종료 시 정리하고, 실패하면 cleanup에 남긴다. 진단 결과 파일은 .runs/x0에만 쓴다. 다른 드라이브가 있으면 --locations에 other와 --other-root를 명시할 수 있으며 다른 볼륨인지 검증한다. 현재 드라이브 조사에서는 C:와 같은 C:의 Temp 별칭만 확인됐다.

## 확인된 것 / 배제된 것 / 미확정

### 확인된 것

실행 결과: `.runs/x0/baseline/70808589578941f5888bdcc5c9ba5d73/diagnosis.json` 및 같은 폴더의 summary.md/trials.jsonl. protocol_sha256=`9d37e8566f18961b622aa2b6094cb0c416f68186cf2540793f594d1d8977f3b4`. schema 2, finished=true다. 환경은 Windows 11 build 26200 / Python 3.12.10 / memvid-sdk 2.0.160이다.

2026-11-10 13:50:55~14:03:29 KST, seed와 조회를 포함한 기록상 소요 시간 약 753.2초. 12조건 각각 n=30, 총 360회 중 성공 329건·실패 31건이다. seed 12회는 별도로 모두 성공했으며 성공률 분모에 넣지 않았다. reader 조건 미성립은 0건, close 오류는 0건이다. 성공은 SDK open/put/seal/close가 예외 없이 끝났다는 정의이며, publish_index의 전수 self-retrieval/manifest 검증 통과를 뜻하지 않는다. 실제 모델은 사용하지 않은 합성 벡터 경로 시험이다.

실패 31건의 최초 오류는 모두 MV999 Tantivy IO 접근 거부(os error 5)였다. put:0에서 20건, put:8에서 4건, put:16에서 7건이다. offset 0/8/16은 batch 8의 첫째/둘째/셋째 put 호출 시작 문서 번호다. 원래 예외를 보존했고 실패한 writer에는 재시도하지 않았다. 각 단계 시간과 close 시도는 trials.jsonl의 timings에 있다. 아래 중앙 시간은 점유 조회가 있으면 그 시간도 포함한다. 조회를 제외한 작업 시간 중앙값과 총/최대 시간은 diagnosis.json의 summary에 있다.

| 조건 | n | 성공 | 성공률 | Wilson 95% | 최초 실패 put(offset) | close 오류 | 중앙 시간 ms |
| --- | --- | --- | --- | --- | --- | --- | --- |
| temp-w0-closed | 30 | 24 | 80.00% | [62.69%, 90.49%] | {"put:0":5,"put:8":1} | 0 | 1835.6 |
| temp-w0-hold-reader | 30 | 27 | 90.00% | [74.38%, 96.54%] | {"put:0":2,"put:16":1} | 0 | 1851.5 |
| temp-w100-closed | 30 | 29 | 96.67% | [83.33%, 99.41%] | {"put:16":1} | 0 | 1943.7 |
| temp-w100-hold-reader | 30 | 27 | 90.00% | [74.38%, 96.54%] | {"put:16":1,"put:0":1,"put:8":1} | 0 | 1945.2 |
| temp-w500-closed | 30 | 27 | 90.00% | [74.38%, 96.54%] | {"put:8":1,"put:16":1,"put:0":1} | 0 | 2298.1 |
| temp-w500-hold-reader | 30 | 28 | 93.33% | [78.68%, 98.15%] | {"put:0":2} | 0 | 2337.2 |
| workspace-w0-closed | 30 | 26 | 86.67% | [70.32%, 94.69%] | {"put:0":4} | 0 | 1824.3 |
| workspace-w0-hold-reader | 30 | 28 | 93.33% | [78.68%, 98.15%] | {"put:0":2} | 0 | 1801.4 |
| workspace-w100-closed | 30 | 29 | 96.67% | [83.33%, 99.41%] | {"put:16":1} | 0 | 1924.6 |
| workspace-w100-hold-reader | 30 | 29 | 96.67% | [83.33%, 99.41%] | {"put:16":1} | 0 | 1913.4 |
| workspace-w500-closed | 30 | 28 | 93.33% | [78.68%, 98.15%] | {"put:0":1,"put:8":1} | 0 | 2295.8 |
| workspace-w500-hold-reader | 30 | 27 | 90.00% | [74.38%, 96.54%] | {"put:0":2,"put:16":1} | 0 | 2312.4 |
성공률 Wilson 구간은 전 조건에서 공통으로 겹친다(공통 교집합 약 83.33%~90.49%). 성공 건수 차이를 근거로 위치/대기/reader 설정의 승자를 선언하지 않는다. 차이 불확실이다. 어떤 조건도 30/30이 아니며, 향후 0건 실패가 나오더라도 보장으로 해석하면 안 된다.

실패 31건의 close 전후 RM 조회는 모두 정상 종료했다. close 전에는 현재 진단 Python PID만 보고됐고 close 후 목록은 모두 비었다. 외부 점유 프로세스는 이 경로 조회에서 보고되지 않았다. 이것은 실제 조회 가능성을 확인한 것이며 모든 OS 핸들을 수집했다는 뜻은 아니다. 자체 프로세스 핸들 총수도 각 시험 전후 기록했다. 파일 생성 직후 대기, 위치 및 명시적인 직전 reader 상태는 조건 메타데이터에 남겼다.

사용자 Temp의 일회용 SDK 파일 루트는 절대 경로 검증 후 정상 정리됐다. 결과 파일은 .runs/x0에만 있다. 다른 드라이브는 OS 열거에서도 C:만 있어 미실행이다.

### 배제된 것 — 이번 관찰의 필요조건/충분조건 수준

- 저장소 .runs에만 특유한 현상이라는 설명: 사용자 Temp에서도 실패했다.
- 파일 생성 후 100/500ms 대기만으로 실패가 없어졌다는 설명: 두 대기 조건에서도 실패했다.
- 명시적으로 유지한 직전 reader가 있어야 실패한다는 설명: closed 조건에서도 새 파일 쓰기가 실패했다.
- 최초 put에서만 실패한다는 설명: 둘째/셋째 put에서도 최초 오류가 났다.

이는 특정 조건이 유일한 필요조건이 아니라는 관찰이다. Windows/SDK/백신/파일 잠금이 원인이 아니라는 결론은 아니다.

### 미확정·미검증

- Windows 파일 교체 의미, SDK 내부 Tantivy 핸들/임시 파일, 백신·검색 색인기의 순간 개입 중 직접 원인은 미확정이다. RM이 exact .mv2 파일만 보므로 native 임시 경로나 보호 프로세스의 짧은 점유를 놓칠 수 있다.
- hold-reader는 직전의 다른 파일을 읽는 자체 핸들 대조다. SDK 내부 실제 핸들 누수 유무, 같은 파일 재사용 잠금의 영향은 직접 입증하지 못했다.
- 다른 OS/SDK 버전/드라이브는 미검증이다. 단일 프로세스 반복의 독립성, 무작위 순서에서의 재현도 미검증이다.
- **동시 환경 변화가 관찰됐다.** 진단 전 `.runs/store-import-audit.json`에서는 chromadb가 없었으나 최종 시험에서는 Chroma 시험이 실행됐고, chromadb 1.5.9 디렉터리 수정 시각(13:58~14:02 KST)이 진단 시간대와 겹쳤다. 본 작업은 패키지 설치 명령을 실행하지 않았다. 변경 주체와 정확한 설치 시점/부하는 미확정이지만 외부 파일 IO·스캐너 부하가 섞였을 가능성이 있다. 따라서 이번 결과는 실패 재현 자료이며, 백신 제외 전후의 엄밀하게 고정된 환경 기준선으로 단정할 수 없다. protocol_sha256은 기록한 조건의 일치만 나타내며 외부 활동의 부재까지 보증하지 않는다. 대표 비교 때는 외부 설치/작업을 통제하고 같은 명령으로 별도 기준선을 확보해야 한다. 자동 재진단은 하지 않았다. 종료 시점 패키지 메타데이터는 같은 결과 폴더의 environment-end.json에 읽기 전용으로 기록한다.
- 백신 제외 전후 비교는 하지 않았다. 대표가 같은 명령·trials·프로토콜로 별도 실행해야 한다. 시스템 설정과 보안 프로그램은 변경하지 않았다.
- 개발 기본 저장소 Chroma 결정은 그대로다. 이번 결과로 memvid 개발 경로 복귀나 버퍼/retry 구현을 제안·적용하지 않았다.

## 전체 시험·보호 파일

새 진단 harness 사전 시험은 fake SDK로 `3 passed`였다. 최종 전체 시험(필터 없음)은 `260 passed, 0 failed, 0 error, 1 skipped` (39.06s), `.runs/x0/followup-pytest.txt`다. 기존 memvid 시험이 이번 전체 시험에서는 실패하지 않았지만, 별도 SDK 진단에서 발생한 31건은 위에 그대로 기록했다. 재시험/skip/기대값 변경은 하지 않았다. 환경 변화로 선택 의존성 시험 수가 이전 단계와 달라졌다.

보호 파일 18개 SHA-256은 기준 `C:/myLectureWs/rra-p1-stage/merged-protected-before.json`과 모두 동일하다. 개별 Expected/Actual/Unchanged는 `.runs/x0/baseline/70808589578941f5888bdcc5c9ba5d73/protected-sha256.json`에 있다. 생산 src 코드, 기존 시험, data/profiles/frozen masking은 변경하지 않았다. 신규 진단 시험만 추가했고 README 미커밋 변경을 보존하며 커밋에서 제외한다. legal-intake 수정, 새 설치, retry 변경, main 병합은 하지 않았다.
