# NightCoder 야간 명세 (2026-11-09 → 11-10 아침)

이 폴더의 명세 3개를 NightCoder `inbox/`에 복사한다. 순서는 `after:` 헤더로 이어진다: P1 → P3 → P2. 레인은 이 저장소 하나.

| 파일 | 내용 | 우선 |
| --- | --- | --- |
| `rra-p1-cli-inputs.md` | 명령줄 `rra`, 입력(txt·md·docx·pdf·웹·구글 문서·깃허브, X는 붙여넣기) | 1 |
| `rra-p3-lint.md` | 프로필·골든룰 검사기 `rra check` | 2 |
| `rra-p2-graph.md` | LangGraph 어댑터 + 로컬 기록 | 3 |

## 시작: 명령 한 줄 (v5, 2026-11-10)

**평일 밤 (매일 같은 명령):**
```powershell
powershell -ExecutionPolicy Bypass -File C:\work\rra-codex\nightcoder_specs\start_night.ps1 -Supervise -ScreenOff
```

**금요일 저녁 → 일요일 낮 (끝나는 시각만 붙임):**
```powershell
powershell -ExecutionPolicy Bypass -File C:\work\rra-codex\nightcoder_specs\start_night.ps1 -Supervise -StopAt 2026-11-15T12:00 -ScreenOff
```

**확인:** `C:\Users\Codelab\nc2-rra-codex\LATEST.txt`에 적힌 폴더의 `SUMMARY.html` 한 장(명세별 성공·실패, 커밋, 시험 개수, 감시 기록).

**감시 모드(`-Supervise`):** NightCoder는 명세 하나가 실패하면 큐를 멈춘다. 감시 모드는 남은 명세가 있고 끝나는 시각 전이면 NightCoder를 다시 시작한다(실패한 명세는 다시 하지 않음, 최대 12회). 다시 시작하자마자 2분 안에 또 멈추면(시작 답변 24시간 만료, 사용량 소진 등) 억지로 반복하지 않고 끝낸다. 실행마다 `SUMMARY.html`을 갱신한다. **제약:** NightCoder의 안전장치상 시작 답변은 24시간 뒤 만료되므로, 금요일 저녁 시작이면 토요일 저녁 이후의 재시작은 되지 않는다(계속 돌고 있는 동안은 일요일까지 간다).

**잘못 쓴 옵션은 멈춘다:** 예) `-Superviseee` → `STOP: unknown option(s)`.

옵션: `-DryRun`(④까지), `-SkipSmoke`, `-Only "rra-c5*,rra-c6*"`, `-StopAt 07:30`, `-Sandbox full-auto|workspace-write`, `-NoStart`(큐까지만).

**커밋 보장(v3):** Codex는 `codex_wrap.py`를 거쳐 실행된다. Codex가 파일을 고쳤는데 커밋하지 않았으면(어제의 `NO_COMMIT`) 래퍼가 그 변경을 커밋한다. 범위·비밀·시험 게이트는 NightCoder가 그대로 판정한다. 실행마다 `wrap.log`에 종료 코드와 커밋 여부가 한 줄씩 남는다.

**자동 이름·보관(v4):** 대표가 넣는 이름은 없다. 레인 폴더·브랜치는 고정, 명세 파일명은 자동 번호, 실행마다 결과 폴더 `C:\Users\Codelab\nc2-rra-codex\runs\<날짜-시각>\outbox`를 새로 만들고 위치를 `LATEST.txt`에 적는다. 레인 브랜치에 main에 없는 커밋이 남아 있으면 맞추기 전에 `nc/archive/<날짜-시각>`으로 자동 보관한다. 스크립트가 main에서 바뀌었으면 1단계 직후 새 버전으로 자동 재시작한다(예전 버전이 끝까지 도는 문제 방지).

**리허설(2026-11-10, 클라우드):** PowerShell 7 + 가짜 NightCoder + 커밋하지 않는 가짜 Codex로 ①~⑦을 끝까지 실행: 옵션 자동 판별(`--sandbox workspace-write`), 스모크 통과(래퍼 커밋), 명세 2개 큐 구성과 `--yes` 시작, 명세마다 패치 수집까지 확인. Windows PowerShell 5.1·실제 nc2·실제 Codex로는 아직 실행 전.

## 출발 전 점검 (수동으로 할 때, Windows PC, 10분)

1. **저장소 최신화:** `cd C:\myLectureWs\python-memvid-guardrail` (로컬 폴더 이름은 예전 그대로) → `git checkout main` → `git pull`. 미커밋 변경이 없어야 한다(`git status` 깨끗). 있으면 Codex 작업 브랜치에 커밋하거나 따로 보관.
2. **시험 기준선:** 그 저장소 `.venv`에서
   `.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider`
   → **실패 0**이어야 한다. NightCoder가 명세마다 전체 시험을 다시 돌리므로, 여기서 실패가 있으면 모든 명세가 실패·롤백된다. 실패가 있으면 걸지 말고 결과를 Claude에게 보낸다.
3. **NightCoder 레인 설정:** 레인 저장소 = 위 폴더, 시험 명령 = 2번 명령, 코더 = codex(구독 로그인 확인).
4. **명세 넣기:** 이 폴더의 `rra-*.md` 3개를 NightCoder `inbox/`에 복사.
5. **사용량 마법사:** Codex 남은 % · 리셋 시각 · 마감(내일 08:30 등) · 여유분(기본 15%)을 입력. 주간 사용량이 적으면 P1만 끝나도 성공이다.
6. **시작 후 확인:** 상태 페이지에서 레인이 `running`이 되고 첫 명세가 P1인지 본다.

## 아침에 볼 것

`outbox/<task>/REPORT.md` 3개(또는 끝난 것까지) → 패치 적용 후 시험 → PR. 실패한 명세는 `nc2/failed/<task>`.

## 2026-11-10 백로그 (Codex 레인, 번호 순)

| 순서 | 파일 | 내용 |
| --- | --- | --- |
| 1~3 | `rra-p1`, `rra-p3`, `rra-p2` | 명령줄·입력, 검사기, LangGraph |
| 4~7 | `codex/rra-c1` ~ `c4` | 인과 쌍, 골든셋 도구, 문장 분할, 의미 관련도 |
| 8 | `codex/rra-c5-store-stability` | 저장소 쓰기 재시도 + 반복 시험 스크립트 |
| 9 | `codex/rra-c6-library-incremental` | 서재 증분 추가·삭제 |
| 10 | `codex/rra-c7-number-table` | 수치 추출표 |
| 11 | `codex/rra-c8-wire-links-relevance` | C1·C4를 조립에 연결 (전제 없으면 멈춤) |
| 12 | `codex/rra-c9-board-diff` | 필터 차이 보드 + 실행 추이 |
| 13 | `codex/rra-c10-prediction-log` | 예측 기록장 뼈대 |
| 14 | `codex/rra-c11-cue-suggester` | 신호 표현 추천 도우미 |
| 15 | `codex/rra-c12-real-embedders` | 실제 임베딩(E5 기본, BGE-M3 후보), 모델 준비 스크립트, 오프라인 강제 |
| 16 | `codex/rra-c13-embedder-compare` | 임베딩 비교 + τ 보정 (M2) |
| 17 | `codex/rra-c14-kiwi-lab` | Kiwi 형태소 키워드 실험 (O5) |
| 18 | `codex/rra-c15-guard-package-legal` | **legal-intake 저장소**에서 보안 코어 패키지 분리 (새 클론에서) |
| 19 | `codex/rra-c16-guard-adapter-research` | 리서치 저장소에 보안 패키지 연결 (M3, C15 전제) |

대표가 직접 할 단계: 모델 내려받기(`scripts/prepare_models.py`, C12 뒤), Kiwi 설치(`pip install -e .[kiwi]`, C14 뒤).
| 20 | `codex/rra-c17-golden-v2-tooling` | 검색 골든셋 v2 도구(등급·근거 구절·유형별·신뢰구간·끝-끝 평가) |
| 21 | `codex/rra-p2b-graph-stages` | P2 보류 해제: `brief.py` 단계 분리 허용 + LangGraph 어댑터 + 로컬 기록 |
| 22 | `codex/rra-c15b-guard-mirror-legal` | **legal-intake**: 패키지 = 정본과 바이트 동일한 미러 + 동일성 시험 (C15 차단 해제) |
| 23 | `codex/rra-e1-langchain-exits` | LangChain 출구: Retriever·Runnable·Tool·LCEL 체인 |
| 24 | `codex/rra-e2-retry-loop` | 근거 부족 시 재검색 루프 (LangGraph, 규칙 기반, 최대 2회) |
| 25 | `codex/rra-e3-langsmith-export` | 골든셋·결과를 LangSmith 형식으로 내보내기 (업로드는 대표 실행 시만) |
