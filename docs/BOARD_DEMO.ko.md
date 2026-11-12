# 보드 데모

저장소 루트에서 의존성이 준비된 Python 환경으로 실행한다. 네트워크, 모델 다운로드,
실제 모델 호출 없이 기존 합성 문항과 규칙 노드를 실행한다.

```powershell
python scripts/board_demo.py --out .runs/board_demo/index.html
```

마지막에 출력된 HTML 경로를 브라우저로 연다. HTML 하나에 스타일과 스크립트가
포함되어 있다. 기본 데이터는 리서치 cases.ko.json의 compare 문항과 법률 평가 팩의
compare 문항이다. confirm은 실행하지 않는다. 실행 시간 목표는 1분 이내이며
환경별 실측은 필요하다.

## 읽는 법

맨 위 설정 비교에는 도메인과 k별로 네 행이 있다. baseline_single은 최초 검색과
첫 문장 요약, graph_basic은 관점 분리·빈칸 검색·재작성 없이 실행하는 그래프,
graph_full은 RuleGrader를 주입한 전체 그래프다. 마지막 행은 기존 FakeLLMGrader에
골드와 무관한 고정 승인 응답을 주입한 경로 시험이다. 성능 순위를 확정하는 자료가 아니다.

- 품질: 리서치는 지표·인과·조건·반대 근거 골드 항목의 충족률, 법률은 필수 조문
  포함률이다. 도메인마다 정의가 다르므로 서로 합산하지 않는다. 막대는 이 비율을 보여 준다.
- 종료: 실제 ResearchResult의 END/give_up/cutoff를 기록한다. legal 필터의 추가 감사
  결과는 guard에 기록하며 그래프 종료 유형을 바꾸지 않는다. human은 현재 RunEvent
  스키마에서 지원하지 않아 미검증이다.
- 루프·토큰·원가: 루프 평균은 rewrite/gap/verify 재시도 합계다. 토큰은 규칙 노드의
  추정량이고 원가는 입력 100, 출력 200 KRW/백만 토큰이라는 가상 요율이다.
  실제 청구 금액이 아니다. 평균은 n을 표시하고 Wilson은 적용하지 않는다.
- hit@k: 최초 질문 검색 순위의 R48 점수다. 그래프의 관점별 검색을 합친 순위가 아니다.
  법률은 필수 조문을 포함한 문서 ID를 골드로 사용한다. 리서치 파일에 gold_sources가
  없으면 미검증으로 표시하며 임의의 정답 문서를 만들지 않는다.
- 근거성 탐지율·과차단률: 연구 도메인의 별도 R44 고정 오류 문항에서 실제 보고서
  검증기와 해당 grader를 함께 실행한 결과다. 그래프가 생성한 답변의 탐지율이 아니다.
  baseline/basic 행도 동일한 독립 평가를 병기한다. 법률용 R44 라벨은 없어 미검증이다.
- 판정 점수: FakeJudge의 참조 어휘 포함도 점수(1~5)와 정답률이다. 연구 참조는
  지표명·반대 근거, 법률 참조는 팩의 gold.answer다. 의미적 정답성은 미검증이다.

모든 비율은 분자/분모와 Wilson 95% 구간을 표시한다. 골드 항목은 독립 표본이
아닐 수 있다. 0건은 안전 보장이 아니다. R39 목표 파일이 있으면 기존 판정기로
목표 위반을 표시한다. 목표 파일 부재는 목표 달성을 뜻하지 않는다.

아래 R38 네 패널은 도메인 탭으로 바꿔 본다. 실행 궤적은 경로·종료·재작성 분포,
비용 통제는 호출·토큰·가상 원가, 환각 방어는 R37 집계와 감사 코드,
성능·레이턴시는 노드별 평균과 표본 수를 보여 준다. 규칙 노드는 실제 모델 호출이
아니므로 호출 수 0일 수 있다. 전체 그래프의 실제 RELEVANCE 로그를 이용해 R37
문서 탈락률을 집계한다(반복 채점도 각각 집계). baseline/basic에는 이 채점 로그가
없고 gold 감사 라벨도 제공하지 않으므로 검색 과차단 의심률은 미검증이다.

## 옵션과 다시 실행

| 옵션 | 기본값 | 용도 |
| --- | --- | --- |
| `--out` | `.runs/board_demo/index.html` | `.runs/` 내부 HTML 경로 |
| `--cases` | `evals/research/cases.ko.json` | 기존 연구 스키마 문항 파일 |
| `--legal-cases` | `evals/domains/legal/cases.json` | 기존 법률 팩 스키마 문항 파일 |
| `--k` | `1 3` | 양의 정수 검색 개수 목록, 중복 불가 |
| `--configs` | 네 설정 전부 | 실행할 설정 이름 목록, 중복 불가 |

```powershell
python scripts/board_demo.py --k 3 --configs graph_full "graph_full + FakeLLMGrader" --out .runs/board_demo/full.html
python scripts/board_demo.py --cases evals/research/cases_v2.ko.json --out .runs/board_demo/v2.html
```

HTML은 해당 실행만 비교한다. 이벤트는 `.runs/events/research/events.jsonl`과
`.runs/events/legal/events.jsonl`에 추가되며 config에 설정과 k를 기록한다.
기존 이벤트는 지우지 않는다. 평가 sidecar는 HTML 옆의 고유한 `index-<id>.json`에
남는다. 민감한 입력 파일을 넣지 않는다. HTML 이스케이프는 개인정보 마스킹이 아니다.

sidecar를 다시 연결하려면 해당 실행의 이벤트와 함께 다음을 사용할 수 있다.
추가 실행의 다른 이벤트는 아래 네 패널에 함께 들어갈 수 있다.

```powershell
python scripts/metrics_board.py --events .runs/events --comparison .runs/board_demo/index-<id>.json --output .runs/board_demo/rebuilt.html
```

빈 입력도 HTML을 만들며 표본이 없는 값은 미검증이다. injection 실행 ID를 별도로
지정하는 기존 metrics_board 옵션을 쓰면 비교 품질 분모에서 제외된다.
