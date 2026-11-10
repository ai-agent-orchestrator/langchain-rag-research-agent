"""Compatibility entry point for the packaged filter board."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from rag_research_agent.rag.board import *  # noqa: F401,F403,E402

if __name__ == "__main__":
    raise SystemExit(main())
