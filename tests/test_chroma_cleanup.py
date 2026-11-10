"""Cleanup failures must preserve reports and the original evaluation exception."""
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from rag_research_agent.core.contracts import Chunk
from rag_research_agent.store.chroma_store import ChromaIndex
from scripts import eval_retrieval_v2 as evaluation
from scripts.compare_embedders import compare_models
from scripts.compare_retrieval_fusion import compare


class LocalLibrary:
    def __init__(self, path, embedder):
        self.path, self.embedder = Path(path), embedder
        self.index = SimpleNamespace(close=lambda: None)

    def build(self, docs, **kwargs):
        self.chunks = [Chunk(id, id + ':c01:v1', 'v1', 'synthetic', title, text, 3, 'v1', 'm1', 'p1')
                       for id, title, text in docs]
        return self

    def search(self, query, k, mode):
        return [(c, 0.75, i) for i, c in enumerate(self.chunks[:k], 1)]


@pytest.fixture
def synthetic(tmp_path):
    corpus = [{"id": "one", "title": "합성", "text": "합성 비용 근거다."}]
    dataset = tmp_path / 'set.json'
    dataset.write_text(json.dumps({"schema": "golden-retrieval/2", "name": "SYNTHETIC cleanup",
        "items": [{"id": "q1", "question": "비용", "type": "paraphrase", "split": "compare",
                   "answerable": True, "relevant": [{"source": "one", "quote": "합성 비용 근거다.", "grade": 2}]}]}), encoding='utf-8')
    return dataset, corpus


@pytest.mark.parametrize('stage', ['temporary.cleanup', 'client.close'])
def test_report_is_saved_before_cleanup_failure(synthetic, tmp_path, monkeypatch, caplog, stage):
    dataset, corpus = synthetic
    out = tmp_path / 'out'
    original = evaluation.TemporaryDirectory
    def fail():
        assert json.loads((out / 'report.json').read_text(encoding='utf-8'))['rows']
        raise PermissionError('simulated WinError 32')
    class LockedTemporary:
        def __init__(self, **kwargs):
            self.inner = original(**kwargs)
            self.name = self.inner.name
        def cleanup(self):
            self.inner.cleanup()
            if stage == 'temporary.cleanup':
                fail()
    class Library(LocalLibrary):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if stage == 'client.close':
                self.index.close = fail
    monkeypatch.setattr(evaluation, 'TemporaryDirectory', LockedTemporary)
    result = evaluation.evaluate(dataset, out=out, library_factory=Library, corpus=corpus, policy=None)
    assert result == json.loads((out / 'report.json').read_text(encoding='utf-8'))
    assert (out / 'report.md').is_file() and (out / 'report.html').is_file()
    warning = json.loads((out / 'cleanup_warnings.jsonl').read_text(encoding='utf-8'))
    assert warning['stage'] == stage and warning['error'] == 'PermissionError'
    assert 'Chroma cleanup warning' in caplog.text


def test_evaluation_error_survives_close_and_cleanup_errors(synthetic, tmp_path, monkeypatch):
    dataset, corpus = synthetic
    out = tmp_path / 'out'
    class BrokenLibrary(LocalLibrary):
        def search(self, *args, **kwargs):
            raise ValueError('original evaluation error')
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.index.close = lambda: (_ for _ in ()).throw(RuntimeError('close failed'))
    original = evaluation.TemporaryDirectory
    class LockedTemporary:
        def __init__(self, **kwargs):
            self.inner = original(**kwargs)
            self.name = self.inner.name
        def cleanup(self):
            self.inner.cleanup()
            raise PermissionError('cleanup failed')
    monkeypatch.setattr(evaluation, 'TemporaryDirectory', LockedTemporary)
    with pytest.raises(ValueError, match='original evaluation error'):
        evaluation.evaluate(dataset, out=out, library_factory=BrokenLibrary, corpus=corpus, policy=None)
    assert not (out / 'report.json').exists()
    assert [json.loads(line)['stage'] for line in (out / 'cleanup_warnings.jsonl').read_text().splitlines()] == ['client.close', 'temporary.cleanup']


def test_fusion_keeps_reports_when_close_fails(synthetic, tmp_path):
    dataset, corpus = synthetic
    class BrokenClose(LocalLibrary):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.index.close = lambda: (_ for _ in ()).throw(PermissionError('locked'))
    out = tmp_path / 'fusion'
    results = compare(dataset, out, alphas=[.5], rrf_ks=[60], library_factory=BrokenClose, corpus=corpus, policy=None)
    assert len(results) == 4 and (out / 'fusion.json').is_file()
    assert len(list(out.glob('*/cleanup_warnings.jsonl'))) == 4


def test_embedder_comparison_saves_before_close_failure(tmp_path):
    out = tmp_path / 'comparison'
    corpus, gold, negative = [tmp_path / f'{name}.json' for name in ('corpus', 'gold', 'negative')]
    corpus.write_text(json.dumps([{'id':'one', 'title':'합성', 'text':'합성 비용 근거다.'}]), encoding='utf-8')
    gold.write_text(json.dumps([{'question':'비용', 'source':'one', 'type':'paraphrase'}]), encoding='utf-8')
    negative.write_text(json.dumps([{'question':'날씨', 'source':None, 'type':'off_topic'}]), encoding='utf-8')
    class BrokenClose(LocalLibrary):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            def close():
                assert (out / 'calibration/fake.json').is_file()
                assert (out / 'compare/comparison.html').is_file()
                raise PermissionError('locked')
            self.index.close = close
    result = compare_models(['fake'], gold, negative, corpus, out, library_factory=BrokenClose)
    assert result[0]['status'] == 'ready'
    assert json.loads((out / 'cleanup_warnings.jsonl').read_text())['stage'] == 'client.close'


def test_closed_chroma_index_directory_can_be_deleted(tmp_path):
    # Runs on Windows as well: keep the closed index alive while removing its path.
    import chromadb
    from chromadb.config import Settings
    path = tmp_path / 'chroma'
    chunk = Chunk('one', 'one:c01:v1', 'v1', 'synthetic', '합성', '비용 근거', 3, 'v1', 'm1', 'p1')
    with chromadb.PersistentClient(path=str(path), settings=Settings(anonymized_telemetry=False, allow_reset=False)) as client:
        collection = client.create_collection('cleanup_test', metadata={'hnsw:space':'cosine'})
        collection.add(ids=[chunk.chunk_id], documents=[chunk.safe_text], embeddings=[[1., 0., 0.]],
                       metadatas=[{'document_id':chunk.document_id, 'content_hash':chunk.content_hash}])
    del collection, client
    index = ChromaIndex(path, 'cleanup_test', [chunk], 3)
    assert index.search_vector([1., 0., 0.], 1)[0][0] == chunk
    index.close()
    index.close()
    shutil.rmtree(path)
    assert not path.exists()
