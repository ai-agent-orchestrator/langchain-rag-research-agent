import json
import socket
from types import SimpleNamespace
import pytest

from rag_research_agent.observe.tracing import ALLOWED_KEYS
from rag_research_agent.rag.langsmith_export import ExportError, build_exports, export_files, upload
from scripts.export_langsmith import main


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*a, **kw):
        raise AssertionError("test attempted network")
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)


@pytest.fixture
def synthetic(tmp_path):
    corpus = tmp_path / "corpus.json"
    corpus.write_text(json.dumps([{"id": "one", "title": "合成", "text": "합성 근거 문장이다."}]))
    dataset = tmp_path / "set.json"
    dataset.write_text(json.dumps({"schema": "golden-retrieval/2", "name": "test", "note": "SYNTHETIC only",
                                    "corpus": str(corpus), "items": [{"id": "q1", "question": "합성 질문",
                                    "type": "paraphrase", "split": "compare", "answerable": True,
                                    "relevant": [{"source": "one", "grade": 2, "quote": "합성 근거 문장이다."}]}]}))
    results = tmp_path / "results.json"
    results.write_text(json.dumps({"rows": [{"id": "q1", "hit": 1.0, "ndcg": 0.75, "source_text": "ignored"}]}))
    return dataset, results


def test_local_dataset_and_experiment_formats(synthetic, tmp_path):
    dataset, results = synthetic
    value = export_files(dataset, tmp_path / "out", results)
    example = value["examples"][0]
    assert example["inputs"] == {"question": "합성 질문"}
    assert example["outputs"]["relevant"][0]["grade"] == 2
    assert example["metadata"] == {"id": "q1", "type": "paraphrase", "split": "compare"}
    assert value["experiments"][0]["metrics"] == {"hit": 1.0, "ndcg": 0.75}
    assert (tmp_path / "out/dataset.jsonl").is_file()


def test_non_synthetic_set_is_refused(synthetic):
    dataset, _ = synthetic
    raw = json.loads(dataset.read_text())
    raw["note"] = "personal document"
    dataset.write_text(json.dumps(raw))
    with pytest.raises(ExportError, match="SYNTHETIC"):
        build_exports(dataset)


def test_only_fake_client_receives_allowlisted_upload_payload(synthetic):
    exports = build_exports(*synthetic)
    class Client:
        def __init__(self):
            self.examples, self.runs = [], []
        def create_dataset(self, **kwargs):
            return SimpleNamespace(id="synthetic-dataset")
        def create_examples(self, **kwargs):
            self.examples.extend(kwargs["examples"])
        def create_run(self, **kwargs):
            self.runs.append(kwargs)
    client = Client()
    assert upload(exports, api_key="synthetic-test-key", client=client)["runs"] == 1
    for row in client.examples:
        assert all(set(row[field]) <= ALLOWED_KEYS for field in ("inputs", "reference_outputs", "metadata"))
    assert set(client.runs[0]["outputs"]) <= ALLOWED_KEYS
    assert "합성 질문" not in str(client.examples) and "합성 근거" not in str(client.examples)
    assert "ndcg" not in str(client.runs)


def test_missing_key_exits_without_client_creation(synthetic, tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    def forbidden(**kwargs):
        raise AssertionError("client must not be constructed")
    assert main(["--set", str(synthetic[0]), "--out", str(tmp_path / "out"), "--upload"], client_factory=forbidden) == 2
    assert "LANGSMITH_API_KEY" in capsys.readouterr().err
    assert main(["--set", str(synthetic[0]), "--out", str(tmp_path / "out")], client_factory=forbidden) == 0
