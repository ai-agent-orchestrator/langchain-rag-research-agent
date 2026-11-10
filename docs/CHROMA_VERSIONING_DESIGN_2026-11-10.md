# Chroma 버전 발행·롤백 설계 비교 — 2026-11-10

상태: 대표의 필요 여부 결정을 위한 설계 제안. 구현·도입 결정 없음. AGENTS.md 및 NightCoder 규칙을 적용한다. 개발 기본값은 Chroma이며 기존 memvid 코드·시험은 보존한다.

## 1. 근거와 확인 수준

- **소스 확인**: 아래 memvid 계약과 현재 Chroma 어댑터의 호출 순서는 이 저장소 소스를 읽어 확인했다. 실제 실행 검증과 구분한다.
- **기존 보고서 관찰**: `CHROMA_CLEANUP_FIX_2026-11-10.md`의 WinError 32 및 클라이언트 소유권 관찰은 해당 보고서의 결과를 인용한다. 이번 작업에서 재현하지 않았다.
- **SDK 미검증**: 이 샌드박스에는 저장소 `.venv/Lib/site-packages/chromadb`가 없고 Python/py가 PATH에 없다. 따라서 요청된 설치 버전 **1.5.9의 소스는 직접 확인하지 못했다**. 기존 보고서가 설명한 SDK close 동작을 이번 작업의 SDK 확인 사실로 승격하지 않는다. 아래의 체크포인트·읽기 전용 열기·스냅샷·파일 안정성·컬렉션 트랜잭션은 SDK가 제공한다고 단정하지 않는다.
- **제안/추정**: 후보의 비용·원자성·구현 크기와 단계별 계약은 앞으로 입증해야 할 설계다. 지연 시간·용량 벤치마크는 없다. 설치·다운로드·네트워크·실제 모델 실행은 하지 않았다.

`MEMVID_DEPENDENCY_INVENTORY_2026-11-10.md`가 지적한 불변 버전, active/previous, 전체 파일 해시 manifest, 롤백, prune의 동일 계약은 **Chroma 경로에 없음**. 이 문서는 그것을 추가하지 않는다.

## 2. memvid 경로의 현재 계약

소스: `src/rag_research_agent/store/memvid_store.py` 및 `src/rag_research_agent/core/contracts.py`. 아래는 코드가 수행하는 검사이며 동시 실행·전원 장애까지 증명한 보장이 아니다.

| 계약 | 소스에서 확인한 동작 |
| --- | --- |
| `publish_index` (61행) | 비어 있지 않은 chunks/vectors, 수·차원, 단일 collection/chunker를 검사한다. `<version>.mv2` 또는 `<version>.manifest.json`이 이미 있으면 거절한다. 외부 벡터와 `enable_embedding=False`로 배치 기록, seal 후 close, `.mv2` SHA-256과 manifest를 쓴다. 다시 열어 모든 chunk의 벡터 검색 top-1을 확인한 뒤 포인터를 바꾼다. 실패 전 생성된 파일 자동 정리는 없다. |
| `_write_pointer` (128행) | `active.json.tmp`에 기록하고 `os.replace`로 `active.json`을 교체한다. indexVersion/file/manifest/sha256/previous를 한 JSON에 담는다. 새 버전 활성화 시 직전 active가 previous이고 같은 버전 재활성화 시 기존 previous를 유지한다. |
| `open_active` (201행) | 포인터·manifest 읽기, pointer SHA와 manifest SHA 일치, 파일 존재·실제 SHA, 임베더 identity를 검사하고 `MemvidIndex`를 반환한다. 오류는 `RetrievalUnavailable`로 전달한다. `MemvidIndex`는 SDK에 `read_only=True`, `mode="open"`을 전달한다. |
| `activate` (157행) | 지정 버전 manifest를 읽어 파일 해시와 identity를 검사하고 읽기 전용 재개방·close 후 포인터를 바꾼다. 롤백과 roll-forward는 같은 함수다. 검사 실패 시 포인터 쓰기에 도달하지 않는다. |
| `list_versions` (139행) | manifest를 열거하고 포인터와 비교해 active/previous/retired로 표시, 읽기·JSON 오류는 unreadable로 표시한다. created_at 기준 정렬이다. 모든 manifest 스키마 오류를 포괄 처리하거나 모든 파일 해시를 검증하는 함수는 아니다. |
| `prune` (179행) | retired만 대상으로 `.mv2`, `.mv2.*`, manifest를 삭제 시도한다. active/previous는 남긴다. PermissionError인 파일은 kept_locked에 기록한다. removed에는 삭제 시도한 버전이 들어가므로 kept_locked가 있으면 실제 완전 삭제를 뜻하지 않는다. manifest도 별도로 삭제 시도해 부분 삭제 후 재발견에 한계가 있다. |
| `IndexManifest` (`contracts.py:59`) | index_version, file, sha256, collection_id, embedding_model, pinned_revision, dimension, normalization, chunker_version, created_at, chunks를 가진 frozen dataclass. 양의 차원과 중복 chunk ID를 검사한다. accepts는 model/revision/dimension/normalization의 정확한 일치다. Chunk는 safe_text의 content_hash를 검증한다. |

현재 해시는 `.mv2` 한 파일의 바이트 전체를 대상으로 한다. manifest 자체의 서명이나 `.mv2.*` 전체의 해시가 아니다. 포인터·manifest까지 함께 바꿀 수 있는 공격자를 막는 인증 계약도 없다. `os.replace` 호출은 확인했으나 fsync, writer 간 잠금, 고유 임시 파일, compare-and-swap은 없다. 기존 계약을 Windows 장애·동시 writer에 대한 완전한 원자성 보장으로 설명하지 않는다.

현재 `chroma_store.py:29,35`는 PersistentClient 생성 후 같은 이름 collection을 삭제 시도하고 재생성·배치 add한다. 반환용 ChromaIndex는 별도 client를 만든다. `verify`는 요청한 ID와 content_hash metadata를 검사하며 DB 전체 바이트·벡터·모든 추가 레코드의 무결성 검증이 아니다. `close`는 소유 client의 공개 close 호출 후 참조를 비운다. 이 호출 사실만으로 SDK가 디렉터리를 불변으로 연다고 추론할 수 없다.

## 3. 후보 비교

모든 후보는 새 버전을 완성·검증하기 전 active를 바꾸지 않고, 포인터 하나에 active/previous를 함께 기록하는 **제안**이다. D는 한 버전의 DB 크기, V는 보존 버전 수, B는 대상 버전 파일 총 바이트다. 수치는 측정값이 아니다.

| 항목 | (a) 버전별 persist 디렉터리 + 포인터 + 파일 manifest | (b) 한 persist DB에서 컬렉션 이름에 버전 부여 | (c) 별도 불변 export + 버전별 재구축 |
| --- | --- | --- | --- |
| 배치 | `versions/v1/db/`, `v1.manifest.json`, `active.json` | `corpus_v1`, `corpus_v2`와 외부 포인터·manifest | canonical chunks/외부 벡터 export와 해시를 보존하고 선택 버전을 새 Chroma 디렉터리에 재구축 |
| 원자성·Windows | 고유 경로에 구축하고 전체 소유자 종료 후 파일 안정성을 확인, 마지막에 작은 포인터만 교체. 열린 디렉터리 rename을 필수로 삼지 않는다. 포인터 잠금/공유 모드 때문에 교체 실패 가능, 실패 시 기존 active 유지가 합격 조건 | 새 이름으로 구축해 배치 실패를 active에서 격리할 수 있다는 설계 의도. 공유 DB의 쓰기가 다른 collection의 파일에도 영향을 주는지는 SDK 소스 확인 필요. 이름 변경·복수 배치의 원자성을 가정하지 않는다. 외부 포인터와 DB 쓰기는 별도 커밋 경계 | export 완성과 재구축 완료 뒤 포인터 교체. 실행 DB 손상 시 재생성 가능하나 export/DB/포인터의 단일 트랜잭션은 없음. Windows 열린 파일의 삭제·이동 문제는 여전히 별도 처리 |
| 디스크 비용 추정 | 약 V×D + 구축 중 D, 디렉터리별 DB 부대 비용. 데이터 중복 큼 | 버전별 벡터·문서 중복 + 공유 DB 비용. 삭제 후 물리 공간 회수 시점·절감량 미검증 | export 보존량 + 재구축 DB + staging. 벡터를 export하면 크기가 클 수 있음 |
| 롤백 시간 추정 | 전체 해시 O(B) + 재개방·검증 + 포인터 교체. 미리 있는 버전으로 이동하며 재임베딩 없음 | 논리 해시 검증 O(레코드/벡터 수) + collection 열기 + 포인터 교체. 작은 포인터 변경만으로 전체 무결성이 입증되지는 않음 | export 해시 + 전체 재구축·검증 시간. 미리 구축해 두면 (a)와 유사 |
| 변조 탐지 범위 | 고정된 DB 디렉터리의 모든 상대 경로·크기·SHA 및 파일 집합을 검사하면 변경·추가·삭제 탐지. 재개방 중 파일 변경 여부가 선결 과제 | 논리 export의 ID/문서/metadata/벡터를 canonical hash하면 그 논리 데이터 범위. HNSW/SQLite 등 DB 바이트 변조 전체를 뜻하지 않음. 공유 디렉터리 해시는 다른 버전 쓰기에도 무효화될 수 있어 버전별 전체 파일 계약과 충돌 | export 바이트 변조 탐지. 재구축 DB 자체의 전체 바이트 탐지는 별도 (a) 계약을 붙여야 함 |
| 구현 크기 추정 | 중~대: manifest/포인터, 빌더 격리, 소유권·안정화, reader pin, prune, 장애 복구 | 중: 수명 관리·논리 manifest. 전체 파일 계약까지 요구하면 대~미정이며 단순 이름 부여로 충족 불가 | 대: 벡터 포함 export 스키마·canonical 직렬화·재구축·호환성까지 필요 |

### Windows 잠금과 원자성의 공통 조건

정리 보고서에서는 Library.build의 close·gc 이후에도 HNSW `data_level0.bin` 삭제가 WinError 32로 실패했다. 다른 소유자를 닫은 단독 ChromaIndex 시험은 삭제에 성공했다. 둘을 구분해야 한다. 정확한 네이티브 핸들 소유자는 미확정이며 공개 close 한 번, gc, 고정 대기만으로 해결됐다고 볼 수 없다.

따라서 (a)에서도 구축 완료 후 디렉터리 rename/delete 성공을 발행의 필수 조건으로 삼지 않는 구조를 제안한다. 단일 builder 프로세스 종료를 소유권 경계 후보로 삼되, 종료 후에도 외부 프로세스/보안 프로그램 잠금이나 데이터 flush 문제가 없는지는 **미검증**이다. 실패하면 활성화하지 않고 staging을 남기며 원인과 경로를 보고한다.

포인터 교체의 제안 조건은 같은 디렉터리의 고유 임시 파일, 파일 flush/fsync 후 닫기, writer 간 OS 수준 잠금 아래 현재 generation 재확인 후 replace다. 활성화와 prune은 같은 잠금을 사용한다. reader는 포인터를 한 번 읽어 버전을 고정하고, pin 확보와 prune 사이 경쟁도 잠금으로 막는다. 교체 실패 시 강제 unlink나 기존 포인터 선삭제를 하지 않는다. 성공한 교체의 전원 장애 내구성, Windows 공유 모드, 실제 파일시스템에서 reader가 이전 또는 새 JSON만 보는지는 장애 주입 시험 전까지 **미검증**이다. 제한된 재시도와 실패 보고의 정책도 별도 명세가 필요하다.

## 4. 조건부 권장안 (a)

대표가 memvid와 같은 **전체 파일 바이트 검증 및 재구축 없는 롤백**이 필요하다고 판단하면 (a)를 권장한다. 버전별 파일 경계를 명시하기 쉽고 (b)의 공유 DB와 버전별 파일 해시 충돌을 피하는 방향이기 때문이다. 다만 Chroma 1.5.9가 재개방·검색 과정에서 파일을 변경하는지 확인하는 것이 선행 중단 조건이다. 확인 없이 현재 ChromaIndex를 불변 저장소로 감싸지 않는다.

제안하는 발행 순서:

1. 단일 writer 잠금 아래 버전 이름·중복을 검증하고 새 고유 디렉터리를 예약한다. 경로 탈출, symlink/junction/reparse point를 거절하는 경계도 명세한다. 기존 버전은 덮어쓰지 않는다.
2. builder가 새 디렉터리에 실제 Chroma 클래스와 외부 벡터로 구축·재개방·검색 검증한다. 모든 소유자 종료와 builder 종료를 확인한다. 현재 publish_chroma의 별도 쓰기 client 소유권 처리는 **후속 연결 필요**다.
3. 종료된 DB의 파일 집합을 정렬하고 상대 경로·크기·SHA-256을 기록한다. manifest는 DB 밖에 두어 자기 해시 순환을 피한다. 기존 IndexManifest의 identity/chunks 의미를 유지하되 별도 schema_version/store_kind/SDK 버전/files/root_digest를 정의하는 후속 명세가 필요하다. 단일 file 필드에 디렉터리 문자열을 끼워 넣지 않는다.
4. 깨끗한 reader 프로세스에서 열기·검색·close 전후의 파일 집합·해시가 유지되는지 확인한다. 파일 변경이 정상 동작이면 전체 파일 불변 계약은 불성립이다. 변하는 파일을 근거 없이 manifest에서 제외하지 말고 대표에게 계약 축소 또는 후보 변경을 요청한다.
5. 전체 해시·identity·검색 검증에 성공한 버전만 준비 완료로 표시한다. writer 잠금 아래 active/previous/generation/manifest digest를 한 포인터에 교체한다. 교체 전 실패는 기존 active 유지, 교체 후 정리 실패는 발행 성공과 구분해 기록한다. 포인터 없는 준비 버전·미완성 디렉터리는 재시작 시 구분해 표시한다.

open_active/activate는 같은 manifest 검증기를 사용하고 오류를 RetrievalUnavailable로 전달하는 제안이다. 해시는 O(B)이므로 롤백이 포인터 쓰기만큼 빠르다고 약속하지 않는다. 기존 reader는 고정한 버전으로 끝까지 처리하고 이후 open부터 새 버전을 쓴다. 해시 검사와 SDK open 사이의 외부 변경(TOCTOU)을 막는 접근 제어·쓰기 차단 수단은 별도 검증이 필요하다.

prune은 active/previous와 모든 살아 있는 reader pin을 보호하고 retired만 대상으로 한다. Windows 잠금은 kept_locked로 보존하며, 부분 삭제 시 manifest/삭제 journal을 마지막까지 남겨 재시도 가능하게 한다. 완전 삭제 뒤에만 removed로 기록한다. 이것은 현재 memvid prune의 단순 복제가 아니라 제안하는 개선 계약이다. 죽은 reader pin 회수 기준과 프로세스 재사용 식별도 명세해야 한다.

신뢰 경계: 파일 manifest와 포인터의 해시는 신뢰할 기준에 대한 차이를 찾는다. 공격자가 DB·manifest·포인터 모두를 교체할 수 있으면 검출을 보장하지 않는다. 서명/외부 신뢰 저장소는 별도 승인 범위이며 이번에는 설계·구현하지 않는다.

## 5. 단계별 후속 명세 단위

각 단계는 별도 작업/커밋, 보고서, 전체 시험을 요구하는 제안이다. 이번 N9에서는 실행하지 않는다. 새 시험은 실제 Chroma 클래스를 사용하고 네트워크·모델 없이 외부 결정적 벡터로 경로 동작을 검사한다. 검색 품질 평가는 아니다.

| 단계 | 범위와 완료 조건 |
| --- | --- |
| V0: SDK 확인 및 중단 판단 | 실제 설치된 1.5.9의 배포 메타데이터, PersistentClient 생성, client.close, 공유 소유권, backend persist/open/종료 경로 소스 위치를 기록한다. 실제 Windows 별도 프로세스로 build→exit→hash→open/query→close→hash를 비교한다. 파일 변경·잠금·지원되는 flush/read-only 여부 확인에 실패하면 (a) 구현을 중단하고 계약 결정을 받는다. |
| V1: 계약 명세와 manifest | 버전 경로·준비/미완성 상태·canonical files digest·identity·신뢰 경계·예외를 확정한다. 실제 DB 파일 변경/추가/삭제, 잘못된 identity, 경로 탈출을 거절하는 새 시험. 기존 IndexManifest 소비자와 충돌 여부 및 Library 연결은 후속 범위로 명시한다. |
| V2: 격리 발행과 open | builder 소유권·프로세스 종료, 준비 완료 검사, 단일 포인터 교체, reader 고정 구현. 실제 Chroma로 중복 버전 거절, 모든 chunk 검색, 빌드/검증 실패 시 이전 active 유지, 불완전 버전 재시작 복구를 검증한다. |
| V3: 활성화·목록·롤백 | activate/list_versions와 generation 충돌 정책 구현. v1→v2→v3→v2에서 active/previous, 같은 버전 재활성화, 변조·누락·identity 불일치 시 포인터 불변을 검증한다. Windows reader/writer 병행과 교체 직전·직후 프로세스 종료 시험 포함. |
| V4: prune와 복구 | reader pin·active/previous 보호, 부분 삭제 journal, kept_locked/removed 구분. 실제 열린 Windows 파일에서 삭제 실패·다음 실행 재개, activate/prune 경쟁, builder 고아 디렉터리와 죽은 pin 회수 시험. 디스크 부족·권한 실패·손상 포인터에서 조용한 fallback 금지 확인. |

공통 통합은 현재 검색용 VectorStore에 수명 관리 API가 없다는 점을 고려해 별도 경계로 결정한다. Library의 CRUD가 활성 버전을 직접 수정하지 않도록 새 버전 발행으로 이어지는 규칙도 **후속 연결 필요**다. 처리량·보존 수·해시 지연·허용 중단 시간은 대표 요구와 실제 측정 후 정한다.

## 6. 하지 않을 경우의 위험과 결정 항목

현재 상태를 유지하면 구현 비용과 버전별 디스크 중복을 피할 수 있다. 대신 같은 collection 재생성 중 실패 시 이전 내용을 계속 제공하는 계약, 한 번의 포인터 변경으로 검증된 과거 버전으로 복귀하는 계약, DB 전체 바이트 변조 탐지 및 active/previous를 보호하는 prune은 **Chroma 경로에 없음**이다. Library content hash만으로 이를 대신 입증할 수 없다. 운영 복구는 보관 원문/외부 벡터/백업 가용성에 따라 재구축이 필요하며 소요 시간은 미검증이다. 정리 잠금으로 디스크가 누적될 위험도 남는다.

대표 결정은 (1) 버전 수명 관리가 지금 필요한지, (2) 전체 파일 검증이 필수인지 논리 데이터 검증이면 되는지, (3) 재구축 롤백 시간을 허용하는지다. 필요하다면 먼저 V0만 승인 가능한 명세로 진행한다. 1.5.9 직접 소스 확인과 Windows 파일 안정성 입증 전에는 후속 구현 착수의 근거가 완성되지 않았다.
