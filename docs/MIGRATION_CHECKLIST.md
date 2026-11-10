# PC / WSL 이전 체크리스트

2026-11-10 KST. 저장소 소스·설정으로 확인한 준비 절차다. 이번 작업에서 설치·다운로드·실제 이전은 실행하지 않았다. 개발 기본 저장소는 **Chroma**다. 기존 memvid 코드·시험은 보존하며 신규 개발에 memvid를 요구하지 않는다.

## 1. 이전 전 기록

- [ ] 저장소 루트에서 `git status --short`, `git branch --show-current`, `git rev-parse HEAD`로 브랜치·커밋·미커밋 작업을 기록한다. 미커밋 파일과 ignored 파일은 clone만으로 옮겨지지 않는다.
- [ ] `git ls-files`와 `.gitignore`를 대조해 실제 추적 범위를 확인한다. ignore 규칙은 이미 추적 중인 파일을 제거하지 않는다.
- [ ] Python·uv·선택 의존성 버전, OS, 모델별 ID·40자리 revision, 사용 프로필·합성 데이터 버전을 비밀값 없이 기록한다. 결과·점검 기록은 `.runs/` 아래에만 둔다.
- [ ] data에 실제 자료가 있으면 Git에 올리지 않는다. 아래 예외 디렉터리에도 실제 자료를 넣지 않는다. 이전이 필요하면 별도 승인된 비공개 절차를 사용한다.

## 2. Git으로 옮겨지는 것과 별도 준비할 것

| 대상 | 현재 규칙 / 이전 방법 |
| --- | --- |
| src, tests, scripts, docs, pyproject.toml, 추적 중인 profiles | Git 추적 파일을 같은 커밋으로 가져온다. 보호 파일·프로필·기존 시험은 변경하지 않는다. |
| `.venv*/` | ignore. 환경 디렉터리를 복사하지 않고 대상 OS에서 다시 만든다. |
| `.runs/` | ignore. 실행 결과·서재·로컬 로그·`.runs/models.json`은 clone에 없다. 필요한 비밀값 없는 리비전 기록을 별도로 확보한다. |
| `data/*` | 기본 ignore. 예외는 `golden_set.json`, `articles.json`, `golden_no_evidence.json`, `README.md`, `golden_rules/`, `equalizer/`, `golden_sets/`, `golden_retrieval/`. 실제 포함 여부는 `git ls-files data`로 확인한다. 예외 하위 파일은 추가될 수 있으므로 실제 자료를 올리지 않는다. |
| `*.mv2`, `*.mv2.*`, `*.npy`, `*.npz` | ignore. 기존 색인·배열은 clone에 없다. 새 환경에서 필요한 서재를 재구축한다. memvid로 개발 경로를 전환하지 않는다. |
| `.env` | ignore. 비밀값 파일을 복사하지 않고 대상 환경의 승인된 설정 방식으로 재설정한다. 값을 출력·요청·보고서에 기록하지 않는다. `.env.*` 전체를 막는 규칙은 없으므로 변형 이름도 안전하다고 가정하지 않는다. |
| `__pycache__/`, `*.pyc`, `.pytest_cache/`, `*.egg-info/`, build, dist | ignore. 새 환경에서 재생성한다. |
| 모델 캐시 | 저장소 외부 캐시는 Git 이전 대상이 아니다. 새 OS의 캐시에 동일 모델·리비전을 준비한다. |

## 3. uv 환경 재구성

- [ ] Python 3.12 이상과 uv를 대상 PC에 별도로 준비한다(`pyproject.toml`의 requires-python). 설치는 대표 실행 작업이며 이 체크리스트 작성 중 실행하지 않았다.
- [ ] 현재 체크아웃에는 추적된 `uv.lock`이 없다. 완전히 같은 전이 의존성 버전 재현은 미검증이다. `uv sync --frozen`으로 잠금 재현이 가능하다고 가정하지 않는다. 필요한 버전 기록을 먼저 확보한다.
- [ ] 대표가 설치를 승인한 환경에서 루트 기준으로 실행한다. 아래 설치는 패키지 다운로드를 수반할 수 있으므로 오프라인 시험 단계와 구분한다.

```powershell
uv venv --python 3.12 .venv
uv pip install --python .venv/Scripts/python.exe -e ".[test,chroma,embeddings]"
```

WSL에서는 Linux 환경을 별도로 만든다:

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e '.[test,chroma,embeddings]'
```

- [ ] LangChain 연결·로컬 평가가 필요하면 `langchain`, `langsmith`, 문서 입력에는 `pdf`, `docx`, Kiwi 실험에는 `kiwi` extra를 용도에 따라 준비한다. 설치와 서비스 업로드는 별도 행위다.
- [ ] `all` extra는 memvid를 포함하므로 Chroma 개발용 설치 명령으로 쓰지 않는다. 기존 memvid 시험에 필요한 별도 환경은 NightCoder/대표의 관리 범위다. 의존성 미설치를 시험 수정·skip 추가로 감추지 않는다.
- [ ] `guard` extra는 별도 저장소의 고정 커밋 의존성이다. C16의 `C:\work\legal-intake-guard` editable 설치 경로는 새 PC에 자동 생성되지 않는다. 다른 저장소나 그 미커밋 변경을 수정하지 않고 승인된 패키지 준비 여부를 확인한다.

## 4. 모델·서재 재준비

- [ ] 이전 PC의 `.runs/models.json`에서 e5 / bge-m3 각각의 `model_id`, `revision`을 비밀값 없이 확보한다. 이 파일은 `.runs/` 규칙으로 Git에 없다. 기록이 없으면 이전과 같은 리비전 재현은 미검증이다.
- [ ] `scripts/prepare_models.py`는 공개 모델의 정확한 커밋을 조회·다운로드하고 `.runs/models.json`에 `revision` 및 `cache_path`를 기록한다. 다운로드는 대표가 승인한 준비 단계에서만 수행한다. `--revision`을 생략하면 당시 main을 조회하므로 이전 리비전 보존용으로 생략하지 않는다.

대표 실행 예시(이번 작업에서는 미실행, `<...>`는 확보한 실제 리비전으로 대체):

```powershell
.venv/Scripts/python.exe scripts/prepare_models.py --model e5 --revision <E5_40자리_커밋>
.venv/Scripts/python.exe scripts/prepare_models.py --model bge-m3 --revision <BGE_40자리_커밋>
$env:HF_HUB_OFFLINE='1'
```

WSL은 `.venv/bin/python`과 `export HF_HUB_OFFLINE=1`을 사용한다. 네트워크 없는 환경은 승인된 캐시 이전·오프라인 준비 절차를 별도 확인한다. 이 스크립트 자체는 네트워크 준비 도구이며 오프라인 전용 가져오기 절차는 여기서 검증하지 않았다.

- [ ] `cache_path`의 Windows 절대 경로를 WSL 경로로 그대로 재사용하지 않는다. 현재 registry는 기록의 모델 ID·revision을 읽고 provider가 로컬 캐시에서 해당 revision을 찾는다. JSON만 옮겨서는 가중치가 준비되지 않는다.
- [ ] 일반 provider는 `local_files_only=True`, `trust_remote_code=False`로 로드하며 명시적인 `HF_HUB_OFFLINE=0`은 거절한다. 정확한 모델 준비 계약은 [MODELS.ko.md](MODELS.ko.md)를 참조한다.
- [ ] Chroma 서재는 동일 모델·revision·청커·프로필 조건을 확인해 재구축하고 Library 검증·검색을 확인한다. 원본 입력 없이 ignored 색인만으로 재구축할 수 있다고 가정하지 않는다. 실행 산출물은 `.runs/` 안에 둔다.
- [ ] 버전 발행·active/previous·롤백·DB 전체 SHA-256 manifest·prune의 memvid와 같은 계약은 **Chroma 경로에 없음**이다. [설계 제안](CHROMA_VERSIONING_DESIGN_2026-11-10.md)은 구현 완료 기능이 아니다.

## 5. Windows / WSL 차이와 이전 후 확인

- [ ] 문서의 `C:\work\...`, 과거 `C:\myLectureWs\...`는 해당 PC의 경로다. 상대 경로 명령은 저장소 루트에서 실행하고, WSL에서는 실제 Linux 경로를 사용한다. 드라이브 마운트를 쓰는 경우 경로를 별도로 확인한다.
- [ ] PowerShell의 `$env:...`와 Linux shell의 `export`, `.venv/Scripts/python.exe`와 `.venv/bin/python`을 구분한다. 파일명 대소문자, 권한·실행 비트, 줄바꿈 차이는 대상 환경에서 확인한다. Windows와 WSL의 가상환경을 공유하지 않는다.
- [ ] DB를 사용하는 프로세스를 종료한 뒤 이전·재구축한다. [Chroma 정리 보고서](CHROMA_CLEANUP_FIX_2026-11-10.md)는 Windows HNSW 파일의 WinError 32와 평가 성공/삭제 성공의 차이를 기록한다. close 한 번으로 모든 핸들이 해제된다고 가정하지 않는다.
- [ ] [X0 후속 진단](X0_MEMVID_DIAGNOSIS_FOLLOWUP_2026-11-10.md)의 memvid MV999 / os error 5 직접 원인은 미확정이다. WSL/Linux에서의 해결·SDK 호환성·파일 잠금·교체 내구성·성능은 이번 작업에서 미검증이다. `/mnt/c`와 Linux 파일시스템의 동작이 같다고 가정하지 않는다.
- [ ] 비밀값을 출력하지 않고 대상 실행 환경의 설정 완료 여부를 확인한다. `.env` 원본·API 키·토큰·비밀번호를 Git이나 이전 보고서에 넣지 않는다.
- [ ] 준비가 끝나면 외부 네트워크 없이 전체 시험을 실행한다. 기존 시험·기대값·skip을 변경하지 않는다. 결과를 passed/failed/error/skipped 그대로 기록하며 실행 불가도 미실행으로 남긴다.

```powershell
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --basetemp=.runs/migration/full-tmp --junitxml=.runs/migration/full-pytest.xml
```

WSL에서는 실행 파일만 `.venv/bin/python`으로 바꾼다. Chroma 개발 게이트의 memvid 표식 제외 정책은 AGENTS.md 5절과 NightCoder 지시에 따르고, 필터 실행은 필터를 결과와 함께 기록한다. 실제 모델 평가와 fake 경로 시험을 같은 결과로 합치지 않는다.

- [ ] 보호 파일 18개 SHA-256과 Git 변경 범위를 비교한다. 기준 manifest 자체는 이 저장소에 포함된다고 가정하지 말고 승인된 별도 기준을 확보한다.
- [ ] Windows/WSL 실제 재구성·모델 로드·검색·잠금 재현·백업 복구는 별도 대표 확인 항목이다. 확인 전에는 이전 완료나 재현성을 보장하지 않는다.
