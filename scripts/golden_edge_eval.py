"""Compatibility entry point for the packaged golden rule evaluator."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from rag_research_agent.rag.score import *  # noqa: F401,F403,E402

if __name__ == "__main__":
    raise SystemExit(main())
