files: src/rag_research_agent/embed/providers.py, src/rag_research_agent/embed/registry.py, src/rag_research_agent/rag/library.py, scripts/prepare_models.py, scripts/library_board.py, pyproject.toml, tests/test_embed_registry.py, docs/MODELS.ko.md, docs/C12_REPORT_2026-11-10.md
forbid: data/**, profiles/**, src/rag_research_agent/store/**, .env*
effort: high
coder: codex

# C12: 실제 임베딩 모델 연결 (E5 기본 + BGE-M3 후보) — 결정 D8

## 배경
`embed/providers.py`에 `E5Embedder`(sentence-transformers, 리비전 고정 필수, query/passage 접두어)와 `make_embedder`가 있다. 서재(`rag/library.py`)는 `FakeEmbedder`만 쓴다.

## 내용
- `embed/registry.py`: 이름으로 임베더 생성. `"fake"`, `"e5"`(기존 `E5Embedder`), `"bge-m3"`(새 `BgeM3Embedder`: sentence-transformers `BAAI/bge-m3`, 접두어 없음, 정규화, 리비전 고정 필수). 각 항목에 `model_id`, 리비전, 차원, 접두어 규칙, 대략 크기·VRAM 메모.
- **오프라인 강제:** 모델 로드 시 `HF_HUB_OFFLINE=1`을 기본으로 켜고(`embed.providers.require_offline` 활용), 캐시에 없으면 "`scripts/prepare_models.py`로 먼저 내려받으세요" 오류. 다운로드는 그 스크립트에서만.
- `scripts/prepare_models.py --model e5|bge-m3 [--revision <hash>]`: 대표가 한 번 실행해 캐시에 내려받고 리비전 해시를 `.runs/models.json`에 기록. 리비전을 안 주면 현재 해시를 조회해 기록하고 이후엔 그 값으로 고정.
- `Library(embedder="e5"|"bge-m3"|"fake"|객체)`: 문자열이면 registry로 생성(리비전은 `.runs/models.json`에서). manifest의 임베더 식별자에 리비전 포함.
- `scripts/library_board.py --embedder e5` 옵션.
- `docs/MODELS.ko.md`: 대표용 1쪽(설치 명령, 다운로드 명령, 용량, GPU/CPU 선택, 오프라인 확인 방법).
- `pyproject`: `e5` extra를 `embeddings`로 넓히거나 `bge` extra 추가(sentence-transformers 하나면 둘 다 됨; 기존 extra 이름은 유지).

## 시험 (모델 로드 없음)
registry 이름·식별자, 오프라인에서 캐시 없음 → 안내 오류(로드 함수를 가짜로 주입), 리비전 미고정 거절, Library가 문자열 임베더로 manifest 기록, 다른 임베더로 재오픈 거절.

## 공통 규칙
- 레인 브랜치에서 이전 명세 결과 위에 이어서 작업. 맥락: `docs/EQUALIZER_V0.ko.md`, `docs/DESIGN.ko.md` (결정 D8~D11).
- 데이터 내용 수정 금지: `data/golden_rules/**`, `profiles/*.json`, `data/equalizer/**`, `data/golden_sets/**`.
- `tests/test_structure.py` 통과 유지. `KNOWN_DEBT` 증가 금지. 무거운 라이브러리 import는 어댑터 파일 안에서만.
- 기존 시험 기대값 수정·skip·삭제 금지. 시험에서 네트워크·모델 다운로드 금지. LLM·`.env` 금지. push 금지.
- **끝나면 반드시 `git add` + `git commit`.** 막히면 원인만 보고서에 적고 그 보고서를 커밋한 뒤 멈춘다.
- 보고서: 구현·시험 통과 구분, 전체 시험 `n passed`, 대표가 직접 실행해야 하는 단계(모델 다운로드 등)를 명령과 함께 목록으로.
