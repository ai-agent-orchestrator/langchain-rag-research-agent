"""Alternate import path for the public research package facade."""
MATURITY = "incubating"

from rag_research_agent.research import API_VERSION, __all__, run_research
from rag_research_agent.research import __getattr__ as _public_export


def __getattr__(name: str):
    return _public_export(name)
