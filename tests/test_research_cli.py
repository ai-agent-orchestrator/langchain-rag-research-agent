"""CLI integration tests with real graph, masker, and optional persistent Chroma."""
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from uuid import uuid4

import pytest

from rag_research_agent.rag.research_cli import main


@pytest.fixture
def folder():
    root = Path(".runs/r16/tests")
    root.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=root) as temp:
        yield Path(temp).resolve()


def documents(folder):
    docs = folder / "docs"
    docs.mkdir()
    (docs / "doc-a1.md").write_text(
        "매출은 비용 감소 때문에 18% 증가했다. 성장 기회가 있다. 연락처 [MASKED_EMAIL].", encoding="utf-8")
    (docs / "nested").mkdir()
    (docs / "nested/doc-b1.TXT").write_text("매출 리스크와 손실 위험은 12% 증가했다.", encoding="utf-8")
    (docs / "ignored.csv").write_text("매출은 99% 증가했다.", encoding="utf-8")
    return docs


def test_module_entrypoint(folder):
    docs = documents(folder)
    env = dict(os.environ, PYTHONPATH=str(Path("src").resolve()), PYTHONUTF8="1")
    completed = subprocess.run(
        [sys.executable, "-m", "rag_research_agent.rag.research_cli", "--docs", str(docs),
         "--question", "매출 분석", "--checklist", "매출", "--json"],
        capture_output=True, text=True, encoding="utf-8", env=env, timeout=30)
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert "18%" in result["report"] and "12%" in result["report"]
    assert "99%" not in result["report"]
    assert "[doc-a" in result["report"]
    assert result["path"][0] == "plan" and "verify" in result["path"]
    assert result["estimated_tokens"] > 0
    assert result["required_metrics"] == ["매출"]
    assert isinstance(result["verify_codes"], list)
    assert len(result["sources"]) == 2
    assert {s["location"] for s in result["sources"]} == {"doc-a1.md", "nested/doc-b1.TXT"}


def test_empty_folder_runs_graph(folder, capsys):
    assert main(["--docs", str(folder), "--question", "매출 분석", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["sources"] == []
    assert "NO_EVIDENCE" in result["verify_codes"]
    assert "verify" in result["path"]


def test_unknown_config_rejected(folder, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--docs", str(folder), "--question", "매출", "--config", "missing-config"])
    assert exc.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


@pytest.mark.parametrize("as_json", [False, True])
def test_output_file(folder, capsys, as_json):
    docs = documents(folder)
    out = folder / "output/report.md"
    args = ["--docs", str(docs), "--question", "매출 분석", "--out", str(out)]
    assert main(args + (["--json"] if as_json else [])) == 0
    stdout = capsys.readouterr().out
    assert out.read_text(encoding="utf-8") == stdout
    if as_json:
        assert json.loads(stdout)["search"] == "keyword"
    else:
        assert "Node path:" in stdout and "Verification codes:" in stdout
        assert "Estimated tokens" in stdout and "[doc-a" in stdout


def test_relative_output_is_under_runs(folder, capsys):
    out = folder / "relative.md"
    relative = out.relative_to(Path(".runs").resolve())
    assert main(["--docs", str(folder), "--question", "매출", "--out", str(relative)]) == 0
    assert out.read_text(encoding="utf-8") == capsys.readouterr().out


@pytest.mark.parametrize("option", ["bad-path", "empty-question", "outside-output", "invalid-utf8"])
def test_bad_input(folder, capsys, option):
    docs, question = folder, "매출"
    extra = []
    if option == "bad-path":
        docs = folder / "absent"
    elif option == "empty-question":
        question = " "
    elif option == "outside-output":
        extra = ["--out", str(Path.cwd() / "outside.md")]
    else:
        (folder / "bad.txt").write_bytes(b"\xff")
    with pytest.raises(SystemExit) as exc:
        main(["--docs", str(docs), "--question", question] + extra)
    assert exc.value.code == 2
    assert "Traceback" not in capsys.readouterr().err
    assert not (Path.cwd() / "outside.md").exists()


def test_checklist_and_config_selection(folder, capsys):
    docs = documents(folder)
    main(["--docs", str(docs), "--question", "분석", "--checklist", " 매출, ,매출 ",
          "--config", "graph_basic", "--json"])
    result = json.loads(capsys.readouterr().out)
    assert result["config"] == "graph_basic"
    assert result["required_metrics"] == ["매출"]
    assert "retrieve_gap" not in result["path"] and "rewrite" not in result["path"]


@pytest.mark.parametrize("config", ["graph_full", "graph_basic", "graph_split"])
def test_checklist_deduplicates_in_first_seen_order(folder, capsys, config):
    assert main(["--docs", str(folder), "--question", "분석",
                 "--checklist", " 비용,매출, ,비용,매출,위험 ",
                 "--config", config, "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["required_metrics"] == ["비용", "매출", "위험"]


def test_chroma_requires_existing_library(folder, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--docs", str(folder), "--question", "매출", "--chroma", str(folder / "absent")])
    assert exc.value.code == 2
    assert "CHROMA_LIBRARY_NOT_FOUND" in capsys.readouterr().err


def test_chroma_never_selects_implicit_model(folder, capsys):
    (folder / "library_manifest.json").write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main(["--docs", str(folder), "--question", "매출", "--chroma", str(folder)])
    assert exc.value.code == 2
    assert "CHROMA_REQUIRES_CACHED_E5_REVISION" in capsys.readouterr().err


def test_masker_applies_to_all_inputs(folder, capsys, monkeypatch):
    from rag_research_agent.rag import research_cli

    docs = documents(folder)
    (docs / "doc-a1.md").write_text(
        "매출은 [MASKED_EMAIL] 자료의 비용 감소 때문에 18% 증가했다.", encoding="utf-8")
    calls = []
    original = research_cli.mask_pii

    def record(text):
        calls.append(text)
        return original(text)

    monkeypatch.setattr(research_cli, "mask_pii", record)
    main(["--docs", str(docs), "--question", "매출 분석 [MASKED_EMAIL]", "--checklist", "매출", "--json"])
    result = json.loads(capsys.readouterr().out)
    assert "매출 분석 [MASKED_EMAIL]" in calls
    assert "매출" in calls
    assert any("[MASKED_EMAIL] 자료의 비용 감소" in text for text in calls)
    assert "[MASKED_EMAIL]" in result["report"]


def test_chroma_real_adapter_path(folder, capsys):
    # Path test only: actual Library, ChromaIndex, R5 adapter and ResearchRunner.
    from rag_research_agent.embed.providers import FakeEmbedder
    from rag_research_agent.rag.library import Library

    embedder = FakeEmbedder(dimension=64)
    # Chroma may retain native database handles after client.close() on Windows.
    # Keep its artifacts under .runs, outside TemporaryDirectory's deletion scope,
    # following tests/test_research_chroma.py; all integration assertions still run.
    library = Library(Path(".runs/r16/chroma-tests") / uuid4().hex, embedder=embedder)
    library.build([("doc-a1", "Synthetic", "매출은 비용 감소 때문에 18% 증가했다.")])
    try:
        manifest = (library.path / "library_manifest.json").read_bytes()
        assert main(["--docs", str(folder), "--question", "매출 분석", "--checklist", "매출",
                     "--chroma", str(library.path), "--json"], embedder=embedder) == 0
        result = json.loads(capsys.readouterr().out)
        assert result["search"] == "chroma" and "18%" in result["report"]
        assert result["sources"][0]["location"] == "doc-a1"
        assert (library.path / "library_manifest.json").read_bytes() == manifest
    finally:
        library.index.close()


@pytest.mark.parametrize("wrapped", [False, True])
def test_case_file_runs_one_case(folder, capsys, wrapped):
    cases = [
        {"id": "case-a1", "question": "매출 분석", "checklist": ["매출", "매출"],
         "docs": {"doc-a1": "매출은 비용 감소 때문에 18% 증가했다."}},
        {"id": "case-b1", "question": "비용 분석", "checklist": ["비용"],
         "docs": {"doc-b1": "비용은 99% 증가했다."}},
    ]
    path = folder / "cases.json"
    path.write_text(json.dumps({"cases": cases} if wrapped else cases, ensure_ascii=False), encoding="utf-8")
    assert main(["--cases", str(path), "--case", "case-a1", "--checklist", "매출",
                 "--config", "graph_basic", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert "18%" in result["report"] and "99%" not in result["report"]
    assert result["required_metrics"] == ["매출"]
    assert result["sources"] == [{"source_id": "doc-a1", "location": "doc-a1"}]
    assert result["estimated"] is True
    assert result["end_type"] in {"END", "give_up", "cutoff"}


@pytest.mark.parametrize("change", ["missing-id", "duplicate-id", "blank-question", "bad-checklist",
                                  "bad-docs", "bad-text", "bad-cases", "invalid-json"])
def test_invalid_case_file_has_fixed_error(folder, capsys, change):
    case = {"id": "case-a1", "question": "매출", "checklist": ["매출"],
            "docs": {"doc-a1": "매출은 18% 증가했다."}}
    cases = [case]
    if change == "missing-id":
        case["id"] = "case-b1"
    elif change == "duplicate-id":
        cases.append(dict(case))
    elif change == "blank-question":
        case["question"] = " "
    elif change == "bad-checklist":
        case["checklist"] = "매출"
    elif change == "bad-docs":
        case["docs"] = []
    elif change == "bad-text":
        case["docs"]["doc-a1"] = None
    elif change == "bad-cases":
        cases = [None]
    path = folder / "cases.json"
    path.write_text("PRIVATE_INVALID_JSON" if change == "invalid-json" else json.dumps(cases), encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main(["--cases", str(path), "--case", "case-a1", "--json"])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "RESEARCH_INPUT_OR_STORE_ERROR" in err
    assert "PRIVATE_INVALID_JSON" not in err and "Traceback" not in err


def test_cases_require_explicit_single_selection(folder, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--cases", str(folder / "absent.json")])
    assert exc.value.code == 2
    assert "CASES_REQUIRE_CASE" in capsys.readouterr().err


@pytest.mark.parametrize("node", ["planner", "extractor", "writer"])
def test_llm_requires_injection(folder, capsys, node):
    with pytest.raises(SystemExit) as exc:
        main(["--docs", str(folder), "--question", "매출", f"--{node}", "llm"])
    assert exc.value.code == 2
    assert "LLM_REQUIRES_INJECTED_MODEL" in capsys.readouterr().err


class OfflineModel:
    """Only the model boundary is fake; schemas, fallback and graph remain real."""

    def __init__(self, response):
        self.response, self.schemas, self.prompts = response, [], []

    def with_structured_output(self, schema):
        self.schemas.append(schema)
        return self

    def invoke(self, prompt, config=None):
        assert config is not None and config["callbacks"] == []
        self.prompts.append(prompt)
        return self.response


@pytest.mark.parametrize("node", ["planner", "extractor", "writer"])
def test_injected_model_schema_failure_falls_back_through_real_graph(folder, capsys, node):
    docs = documents(folder)
    model = OfflineModel({"invalid": True})
    assert main(["--docs", str(docs), "--question", "매출 분석", "--checklist", "매출",
                 "--config", "graph_basic", f"--{node}", "llm", "--json"],
                **{f"{node}_model": model}) == 0
    result = json.loads(capsys.readouterr().out)
    assert model.schemas and model.prompts
    assert "18%" in result["report"]
    assert "verify" in result["path"]


def test_injected_writer_valid_output(folder, capsys):
    (folder / "doc-a1.md").write_text("매출은 비용 감소 때문에 18% 증가했다.", encoding="utf-8")
    model = OfflineModel({"sentences": [
        {"text": "매출은 비용 감소 때문에 18% 증가했다.", "claim_ids": ["doc-a0#0"]}]})
    assert main(["--docs", str(folder), "--question", "매출", "--writer", "llm", "--json"],
                writer_model=model) == 0
    result = json.loads(capsys.readouterr().out)
    assert "[doc-a0#0]" in result["report"]
    assert model.schemas[0].__name__ == "ReportOut"


def test_default_config_is_unchanged():
    from rag_research_agent.rag.research_cli import CONFIGS
    from rag_research_agent.rag.research_graph import ResearchConfig

    assert CONFIGS["graph_full"] == ResearchConfig()
