"""Retrieval metrics and opt-in integration exercise the production evaluator."""
import json

import pytest

from rag_research_agent.rag.eval_retrieval import aggregate_retrieval, score_retrieval
from scripts import domain_eval as de


def test_cutoffs_and_full_ranking_mrr():
    score = score_retrieval(["doc-a1", "doc-b1"], ["noise-c1", "doc-a1", "noise-d1", "doc-b1"])
    assert [score[f"hit@{k}"] for k in (1, 3, 5)] == [0, 1, 1]
    assert [score[f"recall@{k}"] for k in (1, 3, 5)] == [0, .5, 1]
    assert score["mrr"] == .5
    late = score_retrieval(["doc-a1"], ["noise-b1"] * 5 + ["doc-a1"])
    assert late["hit@5"] == 0 and late["mrr"] == pytest.approx(1 / 6)


@pytest.mark.parametrize("ranked,hit,recall", [([], 0, 0), (["doc-a1"], 1, .5), (["noise-c1"], 0, 0)])
def test_fewer_results_than_k(ranked, hit, recall):
    score = score_retrieval(["doc-a1", "doc-b1"], ranked)
    assert score["hit@5"] == hit and score["recall@5"] == recall


def test_duplicate_ids_do_not_inflate_recall_or_compress_ranks():
    score = score_retrieval(["doc-a1", "doc-a1", "doc-b1"], ["noise-c1", "noise-c1", "doc-a1", "doc-a1"])
    assert score["n_gold"] == 2 and score["n_results"] == 4
    assert score["mrr"] == pytest.approx(1 / 3)
    assert score["recall@5"] == .5


@pytest.mark.parametrize("gold", [None, []])
def test_absent_gold_is_skipped(gold):
    assert score_retrieval(gold, None) is None
    stats = aggregate_retrieval([None])
    assert stats["n"] == 0 and stats["mrr"] == {"n": 0, "mean": None}
    assert stats["hit@1"]["wilson95"] is None


def test_aggregate_wilson_denominators_and_mrr():
    scores = [score_retrieval(["doc-a1", "doc-b1"], ["noise-c1", "doc-a1"]),
              score_retrieval(["doc-d1"], []), None]
    stats = aggregate_retrieval(scores)
    assert stats["n"] == 2 and stats["mrr"] == {"n": 2, "mean": .25}
    hit, recall = stats["hit@3"], stats["recall@3"]
    assert (hit["ok"], hit["n"], hit["rate"]) == (1, 2, .5)
    assert (recall["ok"], recall["n"], recall["rate"]) == (1, 3, 1 / 3)
    assert hit["wilson95"] == pytest.approx([.09453120573423074, .9054687942657693])
    assert 0 < stats["hit@1"]["wilson95"][1] < 1


@pytest.mark.parametrize("ks", [(), (0,), (-1,), (True,), (1.5,), (1, 1)])
def test_invalid_cutoffs(ks):
    with pytest.raises(ValueError, match="positive integers"):
        score_retrieval(["doc-a1"], [], ks)
    with pytest.raises(ValueError, match="positive integers"):
        aggregate_retrieval([], ks)


@pytest.mark.parametrize("gold,ranked", [("doc-a1", []), ([""], []), (["doc-a1"], "doc-a1"),
                                         (["doc-a1"], [None])])
def test_invalid_id_lists(gold, ranked):
    with pytest.raises(ValueError, match="source IDs"):
        score_retrieval(gold, ranked)


METRICS = [{"name": "coverage", "kind": "contains", "field": "body", "safety": False, "values": ["ok"]}]


def test_opt_in_skips_unlabelled_and_injection_and_keeps_default():
    cases = [
        {"id": "case-a1", "gold_sources": ["doc-a1"], "output": {"body": "ok", "retrieved_ids": ["doc-a1"]}},
        {"id": "case-b1", "output": {"body": "ok"}},
        {"id": "case-c1", "gold_sources": [], "output": {"body": "ok"}},
        {"id": "case-d1", "type": "injection", "gold_sources": ["doc-a1"], "output": {"body": "ok"}},
        {"id": "case-e1", "split": "confirm", "gold_sources": ["doc-a1"]},
    ]
    original = de.evaluate(cases, METRICS)
    result = de.evaluate(cases, METRICS, retrieval=True)
    assert result["retrieval"]["n"] == 1
    assert all("retrieval" not in row for row in result["cases"][1:])
    assert "retrieval" not in original
    result.pop("retrieval")
    result["cases"][0].pop("retrieval")
    assert result == original


def test_labelled_case_requires_explicit_ranking():
    with pytest.raises(ValueError, match="retrieved_ids"):
        de.evaluate([{"id": "case-a1", "gold_sources": ["doc-a1"], "output": {"body": "ok"}}],
                    METRICS, retrieval=True)


def test_cli_appends_retrieval_fields(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(de, "OUT", tmp_path / ".runs")
    pack = tmp_path / "sample"
    pack.mkdir()
    (pack / "metrics.json").write_text(json.dumps(METRICS), encoding="utf-8")
    cases = [{"id": "case-a1", "gold_sources": ["doc-a1"],
              "output": {"body": "ok", "retrieved_ids": ["noise-b1", "doc-a1"]}}]
    (pack / "cases.json").write_text(json.dumps(cases), encoding="utf-8")
    de.main(["--domain", "sample", "--packs", str(tmp_path), "--retrieval"])
    summary = json.loads(capsys.readouterr().out)
    persisted = json.loads((de.OUT / "sample/runs.jsonl").read_text(encoding="utf-8"))
    assert summary["retrieval"] == persisted["retrieval"]
    assert summary["retrieval"]["mrr"]["mean"] == .5
    de.main(["--domain", "sample", "--packs", str(tmp_path)])
    assert "retrieval" not in json.loads(capsys.readouterr().out)


def test_sidecar_and_real_research_ranking(tmp_path, monkeypatch):
    from rag_research_agent.rag.research_graph import keyword_search

    original, _ = de.research_pack()
    source_case = original[0]
    folder = tmp_path / "evals/research"
    folder.mkdir(parents=True)
    (folder / "cases.ko.json").write_text(json.dumps({"cases": [source_case]}), encoding="utf-8")
    monkeypatch.setattr(de, "ROOT", tmp_path)
    assert "gold_sources" not in de.research_pack(retrieval=True)[0][0]
    sid = next(iter(source_case["docs"]))
    sidecar = folder / "gold_sources.json"
    sidecar.write_text(json.dumps({source_case["id"]: [sid]}), encoding="utf-8")
    assert "gold_sources" not in de.research_pack()[0][0]
    cases, metrics = de.research_pack(retrieval=True)
    output = de.research_output(cases[0], retrieval=True)
    assert output["retrieved_ids"] == [sid for sid, _ in keyword_search(source_case["docs"])(source_case["question"], 5)]
    assert "retrieved_ids" not in de.research_output(cases[0])
    result = de.evaluate(cases, metrics, lambda case: output, retrieval=True)
    assert result["retrieval"]["n"] == 1
    sidecar.write_text(json.dumps({source_case["id"]: ["absent-doc-a1"]}), encoding="utf-8")
    with pytest.raises(ValueError, match="source IDs"):
        de.research_pack(retrieval=True)


def test_custom_cutoffs():
    score = score_retrieval(["doc-a1"], ["noise-b1", "doc-a1"], ks=(2,))
    assert aggregate_retrieval([score], ks=(2,))["hit@2"]["rate"] == 1
