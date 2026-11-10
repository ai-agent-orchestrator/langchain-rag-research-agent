# LangSmith 평가와 로컬 평가

| 수업 개념 | 로컬 대응 | 파일 |
| --- | --- | --- |
| 데이터셋 | 검색 골든셋 v2 | data/golden_retrieval/terms_v2.json |
| 평가자 | quote·등급 기반 golden_v2 지표 | observe/golden_v2.py |
| 실험 | eval_retrieval_v2 실행 | .runs/eval_v2/report.json |
| 데이터셋 예제 내보내기 | inputs/outputs/metadata JSONL | .runs/langsmith/dataset.jsonl |
| 실험 결과 내보내기 | 문항 ID별 수치 지표 JSONL | .runs/langsmith/experiment.jsonl |

기본 실행은 파일만 만듭니다. note 또는 name에 SYNTHETIC 표시가 없는 파일은 거절합니다.

```powershell
python scripts/export_langsmith.py --set data/golden_retrieval/terms_v2.json --results .runs/eval_v2/report.json --out .runs/langsmith
```

대표가 내용을 확인한 뒤 직접 업로드할 때만 `--upload`를 추가하세요.
LANGSMITH_API_KEY가 환경에 있어야 하며 .env 파일을 읽지 않습니다.

```powershell
python scripts/export_langsmith.py --set data/golden_retrieval/terms_v2.json --results .runs/eval_v2/report.json --upload
```

기존 allowlist를 바꾸지 않았습니다. 따라서 **업로드에는 문항 ID·유형·split·상태·출처 ID·hit만**
포함됩니다. 질문/quote/등급 전체와 nDCG 등 추가 지표는 로컬 JSONL에만 남습니다.
LangSmith에는 별도의 ID 중심 데이터셋과 요약 실행을 만듭니다. 전체 질문·근거를 포함한
클라우드 평가가 필요하면 허용 목록 변경 범위를 별도로 검토해야 합니다.
SYNTHETIC 표시는 작성자의 선언이며 실제 개인정보 자동 검증을 대체하지 않습니다.
서비스 경로는 계속 serving_trace_guard로 감싸고 업로드 옵션을 사용하지 마세요.
