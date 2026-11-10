"""Named, revision-pinned local embedding providers; importing never loads a model."""
from __future__ import annotations

MATURITY = "incubating"

import json
from pathlib import Path
from rag_research_agent.embed.providers import BgeM3Embedder, E5Embedder, FakeEmbedder, EmbeddingError

DEFAULT_MODELS = Path(__file__).resolve().parents[3] / ".runs/models.json"
MODELS = {
    "fake": {"model_id": "fake-char-bigram", "revision": "fake-v1", "dimension": 256,
             "query_prefix": "none", "passage_prefix": "none", "size_note": "모델 파일 없음", "vram_note": "GPU 불필요"},
    "e5": {"model_id": "intfloat/multilingual-e5-large-instruct", "dimension": 1024,
           "query_prefix": "Instruct: <task>\nQuery: <text>", "passage_prefix": "none",
           "size_note": "가중치 수 GB 규모 예상; 다운로드 시 확인", "vram_note": "수 GB 이상 추정; 배치·정밀도에 따라 달라짐"},
    "bge-m3": {"model_id": "BAAI/bge-m3", "dimension": 1024, "query_prefix": "none", "passage_prefix": "none",
               "size_note": "가중치 수 GB 규모 예상; 다운로드 시 확인", "vram_note": "수 GB 이상 추정; 긴 입력은 더 필요"},
}


def create_embedder(name="fake", revision=None, models_file=DEFAULT_MODELS, device="cpu", loader=None):
    if name not in MODELS:
        raise EmbeddingError(f"unknown embedder: {name}; choose {list(MODELS)}")
    if name == "fake":
        return FakeEmbedder(dimension=MODELS[name]["dimension"])
    if revision is None:
        try:
            record = json.loads(Path(models_file).read_text(encoding="utf-8"))[name]
            if record["model_id"] != MODELS[name]["model_id"]:
                raise ValueError("model ID mismatch")
            revision = record["revision"]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise EmbeddingError(f"{name} 미준비: scripts/prepare_models.py --model {name}로 먼저 내려받으세요") from exc
    factory = E5Embedder if name == "e5" else BgeM3Embedder
    return factory(revision=revision, device=device, loader=loader)
