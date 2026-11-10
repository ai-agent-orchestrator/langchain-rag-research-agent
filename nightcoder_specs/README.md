# NightCoder 야간 명세 (2026-11-09 → 11-10 아침)

이 폴더의 명세 3개를 NightCoder `inbox/`에 복사한다. 순서는 `after:` 헤더로 이어진다: P1 → P3 → P2. 레인은 이 저장소 하나.

| 파일 | 내용 | 우선 |
| --- | --- | --- |
| `rra-p1-cli-inputs.md` | 명령줄 `rra`, 입력(txt·md·docx·pdf·웹·구글 문서·깃허브, X는 붙여넣기) | 1 |
| `rra-p3-lint.md` | 프로필·골든룰 검사기 `rra check` | 2 |
| `rra-p2-graph.md` | LangGraph 어댑터 + 로컬 기록 | 3 |

## 시작: 명령 한 줄 (v2, 2026-11-10)

```powershell
powershell -ExecutionPolicy Bypass -File C:\work\rra-codex\nightcoder_specs\start_night.ps1 -ScreenOff
```

처음 한 번은 레인 폴더가 없으면 스크립트가 직접 만든다(그 경우엔 저장소에서 스크립트를 먼저 받아 실행: `git clone https://github.com/ai-agent-orchestrator/langchain-rag-research-agent C:\work\rra-codex`).

순서와 멈춤 지점: ① 레인 폴더·브랜치(최신 main 위로 자동 정렬)·깨끗함 → ② 전체 시험(한 번 재시도) → ③ Codex CLI 옵션 자동 판별(`--full-auto` 없으면 `--sandbox workspace-write`) → ④ 설정 파일 생성(기존 `nc2.refactor.json`의 `codex_cmd`를 바탕으로) → ⑤ **스모크 실행**: 파일 하나 고치고 커밋하는 1~2분짜리 명세를 NightCoder로 실제로 돌려 패치가 나와야 통과 → ⑥ 백로그 순서로 큐 구성(main에 보고서가 이미 있는 명세는 건너뜀) → ⑦ `--yes`로 시작. 어느 단계든 실패하면 원인과 고치는 법을 한 줄로 보여 주고 멈춘다.

옵션: `-DryRun`(④까지), `-SkipSmoke`, `-Only "rra-c5*","rra-c6*"`, `-StopAt 07:30`, `-Sandbox full-auto|workspace-write`.

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
