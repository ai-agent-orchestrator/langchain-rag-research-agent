# 로컬 임베딩 모델

기본 실험 모델은 E5-instruct, 비교 후보는 BGE-M3입니다. fake는 모델 파일 없이
문자 겹침만 보는 시험용입니다. 실제 모델 품질은 내려받은 뒤 별도 확인해야 합니다.

대표가 저장소 루트에서 실행할 명령(이번 작업에서는 실행하지 않음):

```powershell
pip install -e ".[embeddings,chroma]"
python scripts/prepare_models.py --model e5
python scripts/prepare_models.py --model bge-m3
$env:HF_HUB_OFFLINE='1'
python scripts/library_board.py --embedder e5 --device cpu --add .runs/documents --rebuild
```

다운로드 스크립트는 공개 모델의 현재 커밋 해시를 조회하고 그 리비전을 캐시에 준비해
`.runs/models.json`에 기록합니다. `--revision <40자리 커밋>`으로 지정해도 됩니다.
일반 실행은 `local_files_only=True`, 원격 코드 금지, 오프라인 환경으로 로드합니다.
`HF_HUB_OFFLINE=0`을 명시한 일반 실행은 거절합니다. 캐시가 없으면 준비 명령을 안내합니다.

E5 질의는 Instruct/Query 접두어, 문서는 접두어 없음. BGE-M3는 둘 다 접두어 없음.
두 모델의 dense 벡터는 1024차원, L2 정규화입니다. 가중치는 수 GB 규모,
추론 메모리는 수 GB 이상으로 예상하며 정밀도·배치·입력 길이에 따라 달라집니다.
정확한 다운로드 용량·메모리는 대표 환경에서 확인하세요. CPU가 기본이며
준비된 CUDA 환경에서는 `--device cuda`를 선택합니다. 모델이 바뀌면 서재를 재구축하세요.
