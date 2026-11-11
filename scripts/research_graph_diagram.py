"""Export the real default research graph without running retrieval or models.

Run: python scripts/research_graph_diagram.py
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

MATURITY = "incubating"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rag_research_agent.rag.research_graph import (  # noqa: E402
    ResearchConfig, build_research_graph, keyword_search,
)

OUTPUT = ROOT / "docs" / "diagrams" / "research_graph.mmd"


def write_diagram(output: Path = OUTPUT, cfg: ResearchConfig = ResearchConfig()) -> str:
    """Serialize compiled topology only; the real search callable is never invoked."""
    mermaid = build_research_graph(keyword_search({}), cfg).get_graph().draw_mermaid()
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(mermaid, encoding="utf-8", newline="\n")
    return mermaid


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args(argv)
    write_diagram(args.output)


if __name__ == "__main__":
    main()
