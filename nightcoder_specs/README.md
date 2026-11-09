# NightCoder 야간 명세 (2026-11-09 → 11-10 아침)

이 폴더의 명세 3개를 NightCoder `inbox/`에 복사한다. 순서는 `after:` 헤더로 이어진다: P1 → P3 → P2. 레인은 이 저장소 하나.

| 파일 | 내용 | 우선 |
| --- | --- | --- |
| `rra-p1-cli-inputs.md` | 명령줄 `rra`, 입력(txt·md·docx·pdf·웹·구글 문서·깃허브, X는 붙여넣기) | 1 |
| `rra-p3-lint.md` | 프로필·골든룰 검사기 `rra check` | 2 |
| `rra-p2-graph.md` | LangGraph 어댑터 + 로컬 기록 | 3 |

## 출발 전 점검 (Windows PC, 10분)

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
