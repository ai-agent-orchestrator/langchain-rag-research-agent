# 인코딩·경로 이식성 점검

2026-11-10 KST. 정적 소스 점검이며 코드 수정이나 장애 재현 결과가 아니다. 경로는 저장소 상대 경로, 행 번호는 점검 시점 기준이다. 개발 기본값은 Chroma다. memvid 항목은 기존 코드의 참고 목록으로만 보존하며 실행·수정하지 않았다.

## 범위와 판정 방법

`rg --files src scripts`의 112개 파일(모두 Python)을 대상으로 `open(`, `read_text(`, `write_text(`, `json.dump(`를 검색했다. 여러 줄 호출은 닫는 괄호까지 읽어 encoding 인자를 확인했다. 역슬래시, 드라이브 경로, replace/unlink/rmtree, 임시 디렉터리 정리, SDK 삭제 및 경로 기준점도 검색했다. 후보 목록은 `.runs/n17/encoding-candidates.txt`, `.runs/n17/path-candidates.txt`에 보관한다. 동적 호출·SDK 내부 구현까지 완전하게 분석한 것은 아니다.

## 1. encoding 미지정 위치

**텍스트 파일 읽기·쓰기에서 encoding을 생략한 호출은 검색 범위에서 발견하지 못했다.** `read_text`/`write_text` 및 텍스트 모드 `open`은 `utf-8` 또는 `utf-8-sig`를 명시한다. 아래는 검색에 걸리지만 인코딩 누락 결함으로 분류하지 않는 위치의 전체 목록이다.

| 파일:행 | 호출·방향 | 한글 포함 가능성 / 위험 | 권장 조치 |
| --- | --- | --- | --- |
| `src/rag_research_agent/store/memvid_store.py:44` | `path.open("rb")`, 바이너리 읽기 | 인덱스 바이트 해시용. 텍스트 디코딩 없음 | encoding 추가 불필요. 기존 memvid 코드 보존 |
| `scripts/diagnose_memvid_writes.py:236` | `old.open("rb")`, 바이너리 읽기 | 파일 핸들 유지 진단. 한글 디코딩 없음 | encoding 추가 불필요 |
| `scripts/diagnose_memvid_writes.py:258` | `lock.open("rb")`, 바이너리 읽기 | 교체 잠금 대조군. 한글 디코딩 없음 | encoding 추가 불필요 |
| `src/rag_research_agent/ingest/sources.py:155` | HTTP opener의 `open(req, timeout=20)`, 응답 읽기 | 파일 open이 아님. 응답 한글의 디코딩 정책은 별도 | 파일 encoding 인자를 붙이지 말고 응답 처리 정책 별도 검토 |
| `src/rag_research_agent/rag/library.py:68,129`, `scripts/library_board.py:93` | `Library.open` 정의·호출 | 서재를 여는 도메인 API. 실제 manifest 읽기는 `library.py:72`에서 UTF-8 명시 | encoding 누락 목록에서 제외 |

`json.dump(` 호출은 **0개**다. 사용 중인 `json.dumps`는 문자열을 반환하며 encoding 인자를 받지 않는다. 문자열을 파일로 쓰는 외부 호출에서 encoding을 확인했다. 예를 들어 `scripts/compare_retrieval_fusion.py:37–39`는 여러 줄에 걸쳐 있지만 마지막에 `encoding="utf-8"`가 있다. `ensure_ascii=False`는 한글을 그대로 직렬화하는 옵션이며 파일 인코딩 지정의 대체물이 아니다.

### models.json과 표시 인코딩

| 파일:행 | 확인 사실 | 위험·권장 조치 |
| --- | --- | --- |
| `scripts/prepare_models.py:24,28` | 기존 JSON 읽기와 한글 메타데이터 쓰기 모두 UTF-8 명시 | 코드의 기본 인코딩 의존 근거 없음. 열람 시 `Get-Content -Encoding UTF8 -LiteralPath .runs/models.json` 사용 |
| `src/rag_research_agent/embed/registry.py:13–18,29` | 메타데이터에 한글이 있고, 준비 파일은 UTF-8로 읽음 | PowerShell 표시 깨짐과 실제 저장 바이트 손상을 구별해야 함 |
| `scripts/prepare_models.py:38` | `ensure_ascii=False` JSON을 stdout에 출력 | stdout/리다이렉션 인코딩은 파일 쓰기와 별도. 후속 작업에서 콘솔·파이프 인코딩 정책을 명시 |

이번 세션에서도 AGENTS.md를 PowerShell 기본 `Get-Content`로 읽으면 한글이 깨져 보였고 `-Encoding UTF8`로 읽으면 정상 표시됐다. 이것은 해당 문서의 열람 관찰이며, 배경의 models.json 바이트 손상 여부는 **미검증**이다. 모델 준비 스크립트는 실행하지 않았다.

## 2. Windows 경로·역슬래시·경로 기준점

| 파일:행 | 방향·내용 | 위험 / 한글 가능성 | 권장 수정 또는 운영 조치(미적용) |
| --- | --- | --- | --- |
| `src/rag_research_agent/guard/intake_guard_adapter.py:18` | 오류 안내의 `C:\\work\\legal-intake-guard\\packages\\intake_guard` | 하드코딩된 Windows 절대 경로 1곳. 파일 접근 자체는 아니지만 PC 이전·WSL에서 설치 안내가 맞지 않음 | 플랫폼 중립 설치 안내와 사용자가 지정하는 로컬 경로로 교체. 외부 저장소는 수정 금지 |
| `scripts/prepare_models.py:25` | `cache_path=str(path)`를 JSON에 기록, 쓰기 | Windows 절대 경로·역슬래시·한글 사용자명 가능. 다른 PC/WSL에서 그대로 사용 불가 | 호스트별 캐시 위치로 취급하고 이전 시 캐시 확인. `registry.py:29–35`는 이 필드를 로더 경로로 전달하지 않음 |
| `src/rag_research_agent/ingest/sources.py:33,41,59,70` | 절대 경로를 origin에 넣고 문서 ID 해시에 반영, 읽기 | 같은 한글 문서도 드라이브·구분자·마운트 위치 변경 시 ID가 달라질 수 있음 | 이전 시 ID 정책을 정하고 논리적 출처/이전 매핑 검토. 기존 ID의 임의 변경 금지 |
| `src/rag_research_agent/embed/registry.py:10`; `src/rag_research_agent/rag/brief.py:25–27`; `src/rag_research_agent/rag/profile.py:21` | `__file__.parents[3]` 기준 모델·data·profiles 읽기 | 체크아웃 구조 가정. wheel 설치 위치에는 저장소 자료가 없을 수 있음. 한글 내용 가능 | 명시적 자료 루트/패키지 리소스 설계 후속 연결 필요 |
| `src/rag_research_agent/rag/library.py:34,36`; `src/rag_research_agent/observe/metrics.py:52–53` | CWD 기준 `.runs` 읽기·쓰기 | 다른 작업 디렉터리에서 다른 서재·로그 루트를 선택. 한글 문서/메타데이터 가능 | CLI 기준 루트와 절대 경로 전달 정책 통일 |
| `src/rag_research_agent/observe/golden_v2.py:55–57`; `src/rag_research_agent/rag/profile.py:68` | JSON 내 경로를 `Path`에 결합해 읽기 | 외부 설정이 Windows 절대 경로/역슬래시를 담으면 POSIX에서 의미가 다름. 실제 data/profiles 내용은 조사하지 않음 | 설정의 상대 경로 표기 규약과 유효성 검사 검토 |
| `scripts/diagnose_memvid_writes.py:27–30,41–50,190,200–202` | Windows DLL 진단과 다른 볼륨·임시 루트 선택 | `os.name` 분기로 비 Windows DLL 호출을 피함. Windows drive anchor와 WSL mount는 동등하지 않음 | 플랫폼별 진단 항목을 구분해 표시하고 볼륨 판정을 별도 설계. memvid 진단은 실행 금지 유지 |

추가로 발견한 역슬래시들은 정규식(`\w`, `\d` 등), 개행/탭, Markdown escape였다. 예: `rag/citations.py:14`, `compose/numbers.py:47`, `scripts/board_diff.py:73`, `scripts/suggest_cues.py:86`, `rag/lint.py:179`는 경로 구분자가 아니다. `embed/providers.py:4`의 `\\n`도 프롬프트 설명이다. 검색 범위에서 그 외 하드코딩된 드라이브/UNC 경로는 발견하지 못했다.

## 3. 교체·삭제와 Windows 잠금 민감 위치

아래 위험은 코드로 추론한 검토 대상이며 이번 작업에서 잠금 장애를 재현한 결과가 아니다. 쓰기 대상 내용은 UTF-8이어도 파일 핸들 잠금은 별개다. 한글 파일명 역시 잠금을 해결하지 않는다.

| 파일:행 | 방향·작업 | 위험 / 한글 가능성 | 권장 수정 또는 확인(미적용) |
| --- | --- | --- | --- |
| `scripts/prepare_models.py:27–29` | 고정 `.tmp`에 쓰고 `Path.replace(out)` | 대상 파일 열림 시 실패 가능, 동시 실행 시 임시 파일명 충돌. 한글 모델 메타데이터 포함 | 고유한 같은 디렉터리 임시 파일·제한된 교체 재시도·실패 진단 검토 |
| `src/rag_research_agent/rag/library.py:91–93` | manifest `.tmp` 쓰기·교체 | 같은 잠금/동시 쓰기 위험. 본문·제목·문서 정보 한글 포함 | writer 직렬화 및 교체 실패 시 기존 manifest 보존 시험 검토 |
| `src/rag_research_agent/store/chroma_store.py:49–51,117–126` | collection 삭제 및 client close | 삭제 오류를 넓게 잡고 계속 진행. close는 finally에서 참조 제거하지만 실제 SDK 핸들 해제는 미검증. DB에 한글 문서 포함 | 삭제 실패 유형을 구분하고 Windows 실제 열린 DB의 정리 검증 후속 연결 필요 |
| `src/rag_research_agent/rag/library.py:100–102,150,167` | 별도 PersistentClient 생성과 collection 문서 삭제 | SDK 쓰기·추가 client 소유권 수명 검토 필요. 인덱스와 manifest 사이 실패 복구도 미검증 | 공용 client 수명 관리와 실패 진단 검토. 파일 unlink와 SDK delete는 구별 |
| `scripts/eval_retrieval_v2.py:40,46,53–60` | index close 후 TemporaryDirectory.cleanup | 이미 close→cleanup 순서와 오류 로그가 있음. 외부 핸들 잔존 시 정리 실패 가능 | 기존 진단 유지, Windows/WSL에서 실제 핸들 해제 및 잔여 디렉터리 검증 |
| `scripts/compare_lex_terms.py:45–50` | TemporaryDirectory 종료 시 자동 삭제 | index.close가 finally에 있지 않아 중간 예외 시 정리 충돌 가능. 한글 코퍼스 포함 | 예외 경로에도 close가 먼저 실행되도록 후속 검토 |
| `scripts/store_stress.py:39–55` | TemporaryDirectory 자동 삭제와 index.close | 중간 예외·SDK 핸들 잔존 시 Windows 삭제 실패 가능. 현재 fixture 내용과 무관하게 경로는 한글 가능 | 성공·실패 양쪽의 소유권 종료 및 임시 파일 정리 검토 |
| `src/rag_research_agent/store/memvid_store.py:136,194` | retry_io로 포인터 os.replace, 오래된 파일 unlink | 열린 파일 잠금. 재시도가 영구 잠금을 해결한다는 근거 없음 | 기존 코드 보존, 승인된 별도 memvid 작업에서만 검증 |
| `scripts/probe_memvid.py:103,111,118` | 포인터/인덱스 교체, rmtree(ignore_errors=True) | 열린 인덱스 교체 진단. 정리 실패가 조용히 남을 수 있음 | 기존 진단 보존, 실행하지 않음. 후속 승인 시 정리 실패 기록 검토 |
| `scripts/diagnose_memvid_writes.py:236,246,258–260,268–273` | 열린 read handle 상태 교체 및 rmtree | 의도적 잠금 대조군. 삭제 대상 부모/이름 검사와 오류 기록 존재 | 잠금 대조군을 일반 교체와 구분하고 현재 안전 검사 보존 |

`src/rag_research_agent/store/retry.py:21–36`는 제한 재시도 공통 구현이다. 이를 모든 삭제/교체에 자동 적용한 상태가 아니며 이번 감사에서 정책을 변경하지 않았다. memvid의 버전 발행·롤백·해시 manifest 기능에 대한 대체 구현은 하지 않았다. 해당 버전 관리 기능은 **Chroma 경로에 없음**이다.

## 4. 우선순위 상위 10개

발생 빈도 측정 없이 기본 Chroma 경로의 쓰기 일관성, 이전 시 식별자/경로 변화, 운영 가독성 순으로 정한 검토 순서다. 모두 후속 작업 제안이며 결함 재현·수정 완료를 뜻하지 않는다.

| 순위 | 파일:행 | 우선 검토 이유 | 권장 후속 작업 |
| --- | --- | --- | --- |
| 1 | `src/rag_research_agent/rag/library.py:91–93` | manifest 교체 실패/동시 쓰기로 서재 상태 불일치 가능 | writer 소유권·임시 이름·실패 보존 계약 검토 |
| 2 | `src/rag_research_agent/store/chroma_store.py:49–51` | collection 삭제 실패 원인 구분 부족 | 잠금·없는 collection·그 외 실패를 구분해 진단 |
| 3 | `src/rag_research_agent/rag/library.py:100–102`; `src/rag_research_agent/store/chroma_store.py:117–126` | DB client 수명과 Windows 핸들 해제 | 실제 SDK의 예외 경로 포함 close/cleanup 검증 |
| 4 | `src/rag_research_agent/ingest/sources.py:33,41,59,70` | PC/WSL 이전 시 출처 기반 ID 변화 | 논리적 출처·기존 ID 이전 정책 설계 |
| 5 | `scripts/prepare_models.py:27–29` | 모델 준비 파일 교체의 잠금·동시 실행 위험 | 고유 tmp와 교체 실패 진단 검토 |
| 6 | `src/rag_research_agent/embed/registry.py:10`; `src/rag_research_agent/rag/brief.py:25–27` | 체크아웃/설치 위치에 따른 자료 탐색 | 명시적 자료 루트 계약 검토 |
| 7 | `src/rag_research_agent/rag/library.py:34`; `src/rag_research_agent/observe/metrics.py:52–53` | 실행 위치별 `.runs` 분산 | 루트 정책과 CLI 절대 경로 전달 통일 |
| 8 | `scripts/compare_lex_terms.py:45–50`; `scripts/store_stress.py:39–55` | 예외 시 임시 DB 삭제 충돌 | finally 종료와 정리 실패 진단 검토 |
| 9 | `scripts/prepare_models.py:24–28,38`; `src/rag_research_agent/embed/registry.py:29` | 한글 JSON 표시와 저장 손상 혼동 | UTF-8 열람 절차·stdout 정책 문서화 |
| 10 | `src/rag_research_agent/guard/intake_guard_adapter.py:18` | 이전 후 설치 안내 경로 불일치 | 플랫폼 중립 안내로 후속 연결 |
