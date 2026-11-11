# 리서치 그래프 실험과 평가 보드

2026-11-11 KST · 실험용(한 번 만들고 끝내지 않고, 설정을 바꿔 가며 계속 돌린다)

## 돌리는 법 (PC PowerShell, 레포 루트)

```powershell
.venv\Scripts\python.exe scripts\research_eval.py --note "무엇을 바꿨는지"        # compare 6문항, 설정 5개, 규모 실험
.venv\Scripts\python.exe scripts\research_eval.py --k 3 --note "k=3"              # 검색 k만 바꿔서
.venv\Scripts\python.exe scripts\research_eval.py --split confirm --configs baseline_single,graph_full --sweep "" --note "confirm"
start .runs\research_eval\board.html
```

- 결과는 `.runs/research_eval/runs.jsonl`에 한 줄씩 **누적**되고, 보드(`board.html`)가 매번 전체 기록으로 다시 만들어진다.
- 선택은 compare 분할로만 하고, confirm은 고른 설정 하나에 한 번만 돌린다(AGENTS.md 3절).
- 문항: `evals/research/cases.ko.json` (합성 9문항, compare 6 / confirm 3). 실제 통계 아님.

## 설정 (`ResearchConfig`)

| 이름 | 찬반·조건 분리 검색 | 지표 재검색 루프 | 재작성 루프 | 체크리스트 |
| --- | --- | --- | --- | --- |
| baseline_single | 단일 검색, 첫 문장 요약(모델 아님), 전체 자료 비용 | | | |
| graph_basic | | | | O |
| graph_split | O | | | O |
| graph_full | O | O | O | O |
| graph_full_auto | O | O | O | 자동 추출만 |

## 보드에서 보는 것

- **설정별 요약:** 품질(필수 지표·인과·조건·반대 근거 반영 평균), 추정 토큰, 기준선 대비 배수, 루프 수, 검수 통과.
- **비용–품질 지도:** 왼쪽 위가 목표. 기준선 세로선보다 왼쪽이면 검색 절감이 루프 비용보다 크다.
- **자료 규모별 손익분기:** 배경 문서를 늘릴 때 두 비용 곡선과 교차점.
- **항목별 성적:** 개수/분모, 비율, Wilson 95% 구간.
- **문항별 결과:** 빠진 항목, 남은 검수 코드, 펼치면 보고서와 노드 경로.
- **실행 기록:** 실행마다 설정별 품질 추이.

## 첫 결과 (2026-11-11, 규칙 기반·합성·추정 토큰)

compare 6문항: 기준선 41% → graph_full 97% (필수 지표 16/16, 인과 9/10, 조건 6/6, 반대 근거 5/5), 토큰은 기준선의 약 1.7배.
confirm 3문항(1회): 기준선 32% → graph_full 96%.
표본이 작아 구간이 넓다(예: 조건 6/6의 Wilson 95% 하한 61%). 경향으로만 읽는다.
규칙을 compare 문항을 보며 보정했으므로 compare 점수는 낙관적이다. confirm이 더 정직한 수치다.
