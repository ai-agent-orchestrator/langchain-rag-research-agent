# 골든셋 (임베딩 모델 비교용)

합성 학습 자료이며 실제 법령·약관이 아닙니다.

| 파일 | 내용 |
| --- | --- |
| `articles.json` | 합성 "상담 준비 안내 서비스 이용 약관" 조문 10개 (`id` = 제1조~제10조) |
| `golden_set.json` | 예상 질문 20개(조문당 2개)와 정답 조문 번호 `source`, 질문 유형 `type` |
| `golden_no_evidence.json` | 근거가 없는 질문 9개(`source: null`). `off_topic` 4개는 주제 밖, `hard_negative` 5개는 비슷한 조문은 있지만 답은 없는 질문 |

- `paraphrase`: 조문 제목 단어를 거의 쓰지 않은 일상 표현 → 의미 검색 능력을 봅니다.
- `legal_term`: 조문 제목과 같은 단어를 쓴 짧은 질의 → 키워드처럼 쉬운 경우입니다.
- `off_topic`·`hard_negative`: 근거 게이트가 "자료 없음"으로 거절해야 하는 질문입니다. 두 파일을 합치면 29문항 중 9개(31%)가 무근거입니다.
- 헷갈리는 짝: 제3조(예약 취소) ↔ 제4조(환불), 제6조(수집·이용) ↔ 제7조(보관·파기), 제1조(목적) ↔ 제9조(AI 안내의 한계).

비교 실행(설계 단계에서는 실행하지 않음 · 명령은 Draft PR #5의 프로토타입 기준):

```bash
python scripts/compare_embedders.py --golden data/golden_set.json --corpus data/articles.json --models fake
HF_HUB_OFFLINE=1 python scripts/compare_embedders.py --golden data/golden_set.json --corpus data/articles.json --models fake,e5@<revision>
```

`1위 정답`은 1위로 고른 조문이 정답과 같은 질문 수, `3위 안 정답`은 상위 3개 안에 정답이 있는 질문 수입니다.
`data/` 아래 다른 파일(색인, 벡터)은 Git에 올라가지 않습니다.
