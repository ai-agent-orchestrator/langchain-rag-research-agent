# 골든셋 만들기

1. UTF-8 텍스트에서 남길 문장 줄 앞에 `+ `, 버릴 클리셰에는 `- `를 붙이세요.
   일반 줄은 그대로 두고, 주석은 `# `로 시작합니다. 각 문장은 문장부호로 끝내세요.
2. `python scripts/make_golden_set.py marked.txt --name my_set --check`를 실행하세요.
   여러 문장인 표시 줄은 경고 후 각각 같은 표시로 넣습니다.
   기본 저장 위치는 `.runs/golden/my_set.json`입니다. `data/`에는 쓰지 않습니다.
3. `rra board --profiles research litigation --sets .runs/golden/my_set.json`을 실행하고
   `.runs/board.html`에서 비교하세요. 실제 자료는 `.runs/`에만 보관하세요.
