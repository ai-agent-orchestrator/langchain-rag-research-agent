files: scripts/make_golden_set.py, tests/test_make_golden_set.py, docs/GOLDEN_SET_MAKER.ko.md, docs/C2_REPORT_2026-11-09.md
forbid: data/**, profiles/**, src/**, pyproject.toml, .env*
effort: medium
coder: codex

# C2: 골든셋 만들기 도구 (대표가 표시만 하면 JSON 생성)

저장소 `langchain-rag-research-agent`, main 최신. 골든셋 형식: `data/golden_sets/macro_synthetic_v1.json`(`name`, `note`, `draft`, `must_keep`, `cliche`). 사용처: `scripts/golden_edge_eval.py`, `scripts/filter_board.py`.

## 목표
대표가 텍스트 파일에서 줄 앞에 표시만 하면 골든셋 JSON이 만들어진다. 문장을 손으로 복사할 필요가 없게.

## 입력 형식 (마크된 텍스트, UTF-8)
- 한 줄에 한 문장 또는 문단. 줄 앞 표시: `+ ` = 꼭 남길 문장, `- ` = 버릴 클리셰, 표시 없음 = 일반.
- 한 줄에 여러 문장이 있으면 그 줄 전체를 하나로 본다(문장 분할은 `golden_edge_eval.py`와 같은 규칙으로 맞춤: 표시된 줄이 분할 후 여러 문장이 되면 경고하고, 각 문장을 모두 같은 표시로 넣는다).
- `# `로 시작하는 줄은 주석(무시).

## 명령 `scripts/make_golden_set.py`
```
python scripts/make_golden_set.py marked.txt --name macro_real_v1 --out .runs/golden/macro_real_v1.json [--note "..."]
```
- 출력 JSON의 `draft`는 표시를 뺀 원문을 공백 하나로 이어 붙인 것, `must_keep`/`cliche`는 `draft`에 **그대로 존재하는** 문장(검증해서 없으면 오류).
- 기본 출력 위치는 `.runs/golden/`(git 무시, 실제 자료용). 공개 저장소용 합성 세트만 `data/golden_sets/`에 대표가 직접 옮긴다(스크립트는 `data/`에 쓰지 않음).
- 만든 직후 `golden_edge_eval.evaluate`로 한 번 점수를 계산해 요약(보존 적중·클리셰 위치)을 출력하는 `--check` 옵션.

## 시험·문서
- 합성 마크 텍스트로 생성·검증·주석·여러 문장 줄 경고·`--check` 시험.
- `docs/GOLDEN_SET_MAKER.ko.md`: 대표용 3단계 사용법(표시 → 명령 → 보드).

## 규칙
`src/`·데이터·프로필 수정 금지, 구조 시험 통과, 기존 시험 기대값 수정·skip 금지, 네트워크·LLM 금지, push 금지. 막히면 원인만 `docs/C2_REPORT_2026-11-09.md`에 적고 멈춤.
