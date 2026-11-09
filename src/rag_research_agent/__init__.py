"""Reusable RAG, retrieval and guard components. See docs/MODULE_DESIGN.ko.md."""
__version__ = "0.1.0.dev0"


def __getattr__(name):          # lazy, so importing the package stays cheap
    if name in ("Equalizer", "load_profile", "list_profiles"):
        from rag_research_agent.rag import profile
        return getattr(profile, name)
    raise AttributeError(name)
