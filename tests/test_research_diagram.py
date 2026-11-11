"""Diagram exports use the real graph compiler and Mermaid renderer, offline."""
import re
import subprocess
import sys

import pytest

from rag_research_agent.rag.research_graph import (
    ResearchConfig, build_research_graph, keyword_search,
)
from scripts.research_graph_diagram import OUTPUT, ROOT, write_diagram


@pytest.mark.parametrize("parallel", [False, True])
@pytest.mark.parametrize("stance_split", [False, True])
def test_export_contains_every_real_node(tmp_path, parallel, stance_split):
    cfg = ResearchConfig(parallel_branches=parallel, stance_split=stance_split)
    graph = build_research_graph(keyword_search({}), cfg).get_graph()
    output = tmp_path / "diagrams" / "research_graph.mmd"

    mermaid = write_diagram(output, cfg)

    assert output.read_text(encoding="utf-8") == mermaid == graph.draw_mermaid()
    for name in graph.nodes:
        assert re.search(r"(?m)^\s*" + re.escape(name) + r"[\[(]", mermaid), name
    expected = {"__start__", "__end__", "plan", "refine", "extract", "compare", "coverage",
                "retrieve_gap", "write", "verify", "rewrite", "stop_no_con"}
    expected |= ({"retrieve_base", "join_retrieval"} if parallel else {"retrieve"})
    if parallel and stance_split:
        expected |= {"retrieve_pro", "retrieve_con", "retrieve_limits"}
    assert set(graph.nodes) == expected


def test_script_entry_point(tmp_path):
    output = tmp_path / "cli" / "research_graph.mmd"
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "research_graph_diagram.py"),
         "--output", str(output)],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert output.read_text(encoding="utf-8") == build_research_graph(
        keyword_search({}),
    ).get_graph().draw_mermaid()
    assert OUTPUT == ROOT / "docs" / "diagrams" / "research_graph.mmd"
