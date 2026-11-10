# rra 명령줄 사용법

저장소 루트에서 설치합니다(Python 3.12 이상).

```powershell
pip install -e ".[pdf,docx]"
```

다음 명령은 LLM 없이 프로필 규칙으로 문장을 골라 브리프를 만듭니다.

```powershell
rra brief --profile litigation --file sample.txt --budget 600
rra brief --profile litigation --file sample.pdf --out .runs
rra brief --profile research --url "https://docs.google.com/document/d/DOCUMENT_ID/edit" --allow-network
rra brief --profile tech --url "https://github.com/OWNER/REPO/blob/main/README.md" --allow-network
rra brief --profile macro --text "핵심은 비용이다. 다만 범위는 한정된다." --focus 비용:2 --auto-focus 2
rra board --profiles litigation politics --sets "data/golden_sets/*.json" --out .runs
```

`rra profiles`는 프로필 이름과 설명을 출력합니다.
`rra score --set data/golden_sets/macro_synthetic_v1.json --packs macro`는
기존 골든룰 평가기를 실행하고 `.runs/last_report.md`에 결과를 남깁니다.

`brief`의 마지막 줄은 결과 폴더 경로입니다. 기본 위치는
`.runs/<UTC시각>-<프로필>/`입니다.

- `brief.md`: 설정, 상태, 남긴 문장, 생략 번호·사유, 감량 기록.
- `trace.json`: 문서 정보, 문장별 분류·점수·보호·매칭 규칙·사유, 규칙 버전과 프로필 파일 SHA-256.
- `input.txt`: 가져온 원문(UTF-8).

`--file a.txt b.md` 또는 `--url URL1 URL2 --allow-network`처럼 여러 입력을
주면 문서별 하위 폴더와 `index.md`를 만듭니다. 같은 옵션을 반복해도 됩니다.
`--task "질문"`으로 관련도를 지정하고 `--budget`으로 글자 예산을 조절합니다.
`--auto-focus 2`는 두 번 이상 나온 단어로 집중 키워드 빈자리를 채웁니다(최대 5개).
보드는 `<out>/board.html`과 `board.md`, 비교용 `board_history.jsonl`을 만듭니다.

URL은 `--allow-network`가 있을 때만 가져옵니다. X는 자동 수집하지 않으므로
본문을 복사해 `--text` 또는 파일로 넣으세요. 구글 문서는 링크 공유를 켠
공개 문서만 지원합니다. 비공개 문서는 txt/docx로 내려받아 사용하세요.
GitHub는 공개 저장소만 지원하며 blob 주소와 저장소 루트의 README를 가져옵니다.
루트 README는 `README.md`, `README.ko.md`, `readme.md` 순으로 찾습니다.
일반 웹페이지와 이슈·PR은 HTML 본문을 추출합니다. OAuth·GitHub 인증은 없습니다.
PDF는 글자 레이어가 있어야 하며 스캔 PDF의 OCR은 지원하지 않습니다.
텍스트·마크다운은 UTF-8(BOM 허용)로 저장하세요.

종료 코드: 정상 0, 입력·설정 오류 2, 입력 정책 차단 `BLOCKED` 3.
원문을 포함하는 결과는 `.runs/`에 로컬 보관하고 커밋하지 마세요.
