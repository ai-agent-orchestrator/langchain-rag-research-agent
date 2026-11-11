# 데이터 기반 도메인 평가 팩

`python scripts/domain_eval.py --domain research`는 기존
`evals/research/cases.ko.json`을 읽는 내장 어댑터와 실제 `ResearchRunner`의
규칙 경로를 실행한다. 모델·네트워크 호출은 없다. 기존 research_eval은 변경하지 않는다.

새 팩은 `evals/domains/<domain>/cases.json`과 `metrics.json`으로 정의한다.
도메인 이름은 영문자로 시작하고 영문·숫자·밑줄·하이픈만 허용한다.
팩의 Python 파일은 실행하거나 import하지 않는다.

cases.json 예:

```json
{"cases": [{"id": "doc-a1", "split": "compare", "output": {
  "answer": "근거 있는 결론", "citations": ["source-a1"]
}, "gold": {"required": ["근거", "결론"]}}]}
```

metrics.json 예:

```json
[
  {"name": "coverage", "kind": "contains", "field": "answer",
   "safety": false, "values_field": "gold.required"},
  {"name": "prohibited", "kind": "forbidden", "field": "answer",
   "safety": true, "values": ["금지 표현"]},
  {"name": "citation_count", "kind": "count", "field": "citations",
   "safety": false, "expected": 1}
]
```

- 이름은 고유해야 한다. `field`는 출력 객체 안의 점으로 구분한 사전 키다.
  누락 필드는 오류이며 조용히 통과시키지 않는다.
- `contains`(포함)와 `forbidden`(금지)은 문자열의 대소문자를 구분하는 부분 문자열 검사다.
  `values` 또는 문항 안의 기대값 경로 `values_field` 중 하나를 지정한다.
  각 값은 문자열 또는 문자열 그룹이다. 그룹은 기본 `match: "all"`이며
  `"any"`도 가능하다. 금지는 그룹 일치의 부정이다.
  빈 기대값 배열은 해당 지표의 분모에서 제외한다.
- `count`(개수)는 리스트 항목 수 또는 문자열 문자 수를 `expected`와 비교한다.
  숫자 필드를 개수로 해석하거나 정규식을 실행하지 않는다.
- 품질 지표별 성공 수·분모·비율·Wilson 95% 구간을 기록한다.
  `quality_mean`은 분모가 있는 품질 지표 비율들의 산술 평균이며 신뢰구간 추정치가 아니다.
- 안전 지표는 별도 `safety_metrics`에 기록한다. `errors`는 하나 이상의 검사에
  실패한 문항 수, `n`은 검사가 있는 문항 수다. 위반률·Wilson 95% 구간·상한을
  함께 제공한다. `count`는 금지/포함 표현 출현 수(그룹 간 중복 가능),
  개수 지표에서는 대상 길이의 합이다. 0건은 안전 보장을 뜻하지 않는다.
- `type: "injection"` 문항은 품질 분모에서 제외하고 안전 집계에는 포함한다.
- split 생략 시 compare다. CLI는 compare만 실행한다. confirm 선택·일회성 적용의
  영속 관리와 실험 보드 연결은 후속 연결 필요다. 설정 선택은 compare로만 한다.

`python scripts/domain_eval.py --domain <domain>`은 저장된 `output`을 평가한다.
Python 호출자는 `run(domain, evaluator=callable)`에 문항을 받아 출력 사전을 반환하는
실제 실행기를 주입할 수 있다. 러너가 모델을 로드하지 않는다.
출력은 `.runs/domain_eval/<domain>/runs.jsonl`에 누적되며 원문 대신 지표 집계만 기록한다.

리서치 내장 지표는 포함 4종(수치·인과·조건·균형)과 안전 개수 1종(미지원 수치)이다.
기존 정답을 포함 그룹으로 변환한다. 수치 지표는 본문 안의 이름·숫자 부분 문자열을
검사하므로 기존 research_eval의 같은 문장·숫자 토큰 검증과 점수가 같다고 볼 수 없다.
이 결과는 합성 규칙 **경로 시험**이며 실제 모델 품질은 미검증이다.
허용 파일 범위 때문에 research 폴더의 JSON 복제본은 만들지 않고 코드에 등록했다.
