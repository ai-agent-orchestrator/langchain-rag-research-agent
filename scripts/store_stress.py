"""Repeat local publish/reopen/search with synthetic text and fake embeddings."""
import argparse
import logging
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from rag_research_agent.core.contracts import Chunk
from rag_research_agent.embed.providers import FakeEmbedder
from rag_research_agent.store.retry import logger


class RetryCounter(logging.Handler):
    def __init__(self):
        super().__init__()
        self.retries = 0

    def emit(self, record):
        self.retries += 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--store", choices=["chroma", "memvid"], required=True)
    ap.add_argument("--runs", type=int, default=10)
    args = ap.parse_args(argv)
    if args.runs < 1:
        ap.error("runs must be positive")
    counts = RetryCounter()
    logger.addHandler(counts)
    success = failed = 0
    emb = FakeEmbedder(dimension=64)
    chunks = [Chunk("SYNTH", "SYNTH:c01:v1", "v1", "synthetic", "synthetic", "합성 비용 금리 자료", 11, "v1", "m1", "p1")]
    vectors = emb.encode_documents([c.safe_text for c in chunks])
    try:
        for n in range(args.runs):
            try:
                with TemporaryDirectory(prefix="rra-stress-") as temp:
                    path = Path(temp)
                    if args.store == "chroma":
                        from rag_research_agent.store.chroma_store import publish_chroma, ChromaIndex
                        publish_chroma(chunks, vectors, path=path, collection="rra_stress", dimension=64).close()
                        index = ChromaIndex(path, "rra_stress", chunks, 64)
                    else:
                        from rag_research_agent.store.memvid_store import publish_index, open_active
                        identity = dict(embedding_model=emb.model_id, pinned_revision=emb.revision, dimension=64)
                        publish_index(chunks, vectors, index_dir=path, index_version="v1", **identity)
                        index = open_active(path, **identity)
                    try:
                        hits = index.search_vector(emb.encode_query(chunks[0].safe_text), 1)
                        if not hits or hits[0][0].chunk_id != chunks[0].chunk_id:
                            raise RuntimeError("self retrieval mismatch")
                    finally:
                        index.close()
                success += 1
            except Exception as exc:
                failed += 1
                print(f"run {n + 1}: {type(exc).__name__}: {exc}", file=sys.stderr)
    finally:
        logger.removeHandler(counts)
    print("| store | success | retries | failed |\n| --- | --- | --- | --- |")
    print(f"| {args.store} | {success} | {counts.retries} | {failed} |")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
