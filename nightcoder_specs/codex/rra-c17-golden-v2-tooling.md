files: src/rag_research_agent/observe/golden_v2.py, scripts/eval_retrieval_v2.py, tests/test_golden_v2.py, docs/C17_REPORT_2026-11-10.md
forbid: data/**, profiles/**, src/rag_research_agent/rag/**, src/rag_research_agent/store/**, .env*
effort: high
coder: codex

# C17: 검색 골든셋 v2 도구 (등급·근거 구절·유형별·신뢰구간·끝-끝)

## 배경
`docs/GOLDEN_SET_GUIDE.ko.md`가 v2 형식과 지표를 정의한다. 예시: `data/golden_retrieval/terms_v2.json`(43문항, 코퍼스 `data/articles.json`). C13(`observe/calibration.py`, `scripts/compare_embedders.py`)이 있으면 그 위에 얹고, 없으면 독립적으로 동작한다.

## 내용
- `observe/golden_v2.py` (표준 라이브러리): 로드·검증(`quote`가 코퍼스 원문의 부분 문자열인지, 등급 1/2, split, 중복 ID), v1 파일 자동 변환. 지표: Hit@k, Recall@k(정답 근거 여러 개), MRR, nDCG@k(등급), 근거 없음 오수용률, 근거 있음 거절률 — **전체·유형별·split별**. 부트스트랩 95% 신뢰구간(시드 고정). 질문–정답 구절 단어 겹침 비율(난이도) 계산.
- 판정 단위: `quote`가 있으면 "quote를 포함한 조각", 없으면 `source` 문서 단위.
- `scripts/eval_retrieval_v2.py --set data/golden_retrieval/terms_v2.json --embedder fake [--split compare] [--k 3]`: 코퍼스로 서재(`rag/library.py`)를 임시 폴더에 만들고 검색 결과로 채점, Markdown + 어두운 HTML 보고서(`.runs/eval_v2/`). `--e2e --profile research`: 검색 후 Equalizer 브리프에서 `quote` 문장이 남았는지까지 채점(끝-끝).
- `injection` 문항은 `expect_status`와 입력 정책 결과를 비교(가짜 정책이면 "정책 미연결"로 표시, C16 이후 실제 판정).

## 시험
검증 실패 사례(quote 불일치, 잘못된 등급), 지표 손계산 사례(작은 가짜 순위 목록으로 nDCG·MRR), 신뢰구간 재현성(같은 시드 같은 값), fake 임베더로 스크립트 전체 흐름, 끝-끝 모드 1회.

## 공통 규칙
데이터 수정 금지, 구조 시험 통과, 기존 시험 기대값 수정·skip 금지, 네트워크·모델 다운로드·LLM 금지, push 금지. **끝나면 반드시 커밋.** 막히면 원인만 보고서에 적고 커밋 후 멈춤.
