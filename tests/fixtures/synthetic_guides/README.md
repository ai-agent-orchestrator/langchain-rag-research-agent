# 합성 학습 자료 (RAG v1, B01)

합성 학습 자료이며 법률 자문이 아닙니다. 실명·실제 사건·실제 의뢰인 데이터를 넣지 않습니다.

| 파일 | 내용 |
| --- | --- |
| `guides/GUIDE-001.md` ~ `GUIDE-010.md` | 상담 준비 안내문 10개. 첫 줄 면책 문구, 본문에는 출처 ID를 넣지 않음 |
| `guides.json` | 출처 정보(documentId, caseType, title, 제목 단어)와 헷갈리는 주제 쌍 3쌍 |
| `eval/intakes.json` | 접수 DTO 형태 평가 30개: compare 20(무근거 6), confirm 10(무근거 4) |

- caseType 분포: CIVIL 4, CRIMINAL 2, FAMILY 2, OTHER 2.
- 평가 유형: `paraphrase`(정답 문서 제목 단어 금지), `legal_term`, `pii`(가짜 전화·이메일·이름), `no_evidence`.
- `confirm`은 기준값을 정한 뒤 한 번만 적용합니다. 이 자료로 기준값을 조정하지 않습니다.
- 출처 정보를 본문에 넣지 않는 이유: memvid는 metadata를 검색 본문에 합치므로, 출처는 `title`(= chunkId)과 우리 manifest로 찾습니다.
- 형식 규칙은 `tests/test_rag_corpus.py`가 확인합니다. 실제 E5 토큰 수(문서당 600~1,200 목표)는 `scripts/ingest_guides.py` 실행 결과의 `document_tokens_in_600_1200`으로 확인합니다.
