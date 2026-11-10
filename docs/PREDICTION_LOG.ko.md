# 예측 기록장

예측은 직접 쓰고, 브리프 근거 ID와 기한을 함께 기록합니다. 생성 모델은 호출하지 않습니다.

```powershell
python scripts/predictions.py add --statement "6개월 내 가상 지표가 하락한다" --profile macro --evidence-ids s01 s03 --brief-path .runs/sample/brief.md --due 2027-05-10 --confidence 0.6 --tags 금리
python scripts/predictions.py list --open-only
python scripts/predictions.py resolve ID --outcome partial --note "일부 조건에서만 성립"
python scripts/predictions.py summary
```

기본 `.runs/predictions.jsonl`에 추가만 합니다. `--path 경로`는 하위 명령 앞에 넣습니다.
정정은 같은 ID를 다시 resolve하여 새 줄로 남기며, 목록·요약은 최신 결과를 사용합니다.
결과는 `hit`, `miss`, `partial`, `void`입니다. 적중률은
`(hit + 0.5 × partial) / (hit + miss + partial)`이며 void·미해결은 분모에서 뺍니다.
프로필·태그별 집계와 기한 지난 미해결 수를 보여 줍니다.
날짜만 쓰면 UTC 날짜 끝을 기한으로 사용합니다. 정확한 한국 시각은
`2027-05-10T18:00:00+09:00`처럼 시간대를 붙이세요.
실제 예측·본문·개인정보는 로컬 `.runs/`에서 관리하고 커밋하지 마세요.
