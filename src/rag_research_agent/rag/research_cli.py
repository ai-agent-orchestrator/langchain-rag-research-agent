"""Offline research graph CLI; relative output paths are rooted in .runs/."""
from __future__ import annotations

MATURITY = "incubating"

import argparse
import json
from dataclasses import replace
from pathlib import Path

from rag_research_agent.core.contracts import RetrievalUnavailable
from rag_research_agent.embed.providers import EmbeddingError
from rag_research_agent.guard.masking import mask_pii
from rag_research_agent.rag.research_graph import ResearchConfig, ResearchRunner, keyword_search


CONFIGS = {
    "graph_full": ResearchConfig(),
    "graph_basic": ResearchConfig(name="graph_basic", stance_split=False, gap_loop=False, rewrite_loop=False),
    "graph_split": ResearchConfig(name="graph_split", gap_loop=False, rewrite_loop=False),
    "graph_full_auto": ResearchConfig(name="graph_full_auto", use_checklist=False),
}


class _Masker:
    mask = staticmethod(mask_pii)


def _output_path(value: str) -> Path:
    root = (Path.cwd() / ".runs").resolve()
    path = Path(value)
    target = (path if path.is_absolute() else root / path).resolve()
    if not target.is_relative_to(root):
        raise ValueError("output must be inside .runs")
    return target


def _case_input(path: Path, case_id: str):
    """Select exactly one case; never evaluate/select configurations on confirm data."""
    dataset = json.loads(path.read_text(encoding="utf-8-sig"))
    cases = dataset.get("cases") if isinstance(dataset, dict) else dataset
    if not isinstance(cases, list) or not all(isinstance(c, dict) for c in cases):
        raise ValueError("invalid cases")
    matches = [c for c in cases if c.get("id") == case_id]
    if len(matches) != 1:
        raise ValueError("case ID must select exactly one case")
    case = matches[0]
    question, checklist, docs = case.get("question"), case.get("checklist", []), case.get("docs")
    if (not isinstance(question, str) or not question.strip()
            or not isinstance(checklist, list) or not all(isinstance(m, str) for m in checklist)
            or not isinstance(docs, dict) or not all(
                isinstance(k, str) and k.strip() and isinstance(v, str) for k, v in docs.items())):
        raise ValueError("invalid case")
    corpus = {mask_pii(k): mask_pii(v) for k, v in docs.items() if v.strip()}
    if len(corpus) != sum(bool(v.strip()) for v in docs.values()):
        raise ValueError("masked document ID collision")
    return question, checklist, corpus


def main(argv: list[str] | None = None, *, embedder=None,
         planner_model=None, extractor_model=None, writer_model=None) -> int:
    """Run real graph nodes. An injected embedder permits offline Chroma path tests."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docs", type=Path, help="recursively read UTF-8 .md/.txt files")
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--question")
    inputs.add_argument("--cases", type=Path, help="JSON research case file; requires --case")
    parser.add_argument("--case", help="exact ID of a single case, without evaluation or config selection")
    parser.add_argument("--checklist", default="", help="comma-separated required metrics")
    parser.add_argument("--config", choices=tuple(CONFIGS), default="graph_full")
    parser.add_argument("--chroma", type=Path, help="existing Library directory (library_manifest.json); never rebuilt")
    parser.add_argument("--revision", help="exact cached E5 revision for the existing Chroma library")
    parser.add_argument("--out", help="output file, relative to .runs/ (absolute paths must also be inside it)")
    parser.add_argument("--json", action="store_true", help="emit JSON to stdout and --out")
    for node in ("planner", "extractor", "writer"):
        parser.add_argument(f"--{node}", choices=("rule", "llm"), default="rule",
                            help="llm requires a caller-injected model; CLI never loads one")
    args = parser.parse_args(argv)
    if args.cases is not None and (not args.case or args.docs is not None or args.chroma is not None):
        parser.error("CASES_REQUIRE_CASE_WITHOUT_DOCS_OR_CHROMA")
    if args.cases is None and args.case is not None:
        parser.error("CASE_REQUIRES_CASES")
    if args.cases is None and (args.docs is None or not args.docs.is_dir()):
        parser.error("DOCS_NOT_DIRECTORY")
    if args.question is not None and not args.question.strip():
        parser.error("EMPTY_QUESTION")
    if args.revision and args.chroma is None:
        parser.error("REVISION_REQUIRES_CHROMA")

    library = None
    try:
        out = _output_path(args.out) if args.out else None
        corpus, locations = {}, {}
        question, items = args.question, []
        if args.cases is not None:
            question, items, corpus = _case_input(args.cases, args.case)
            locations = {sid: sid for sid in corpus}
        paths = sorted(p for p in args.docs.rglob("*")
                       if p.is_file() and not p.is_symlink() and p.suffix.lower() in (".md", ".txt")) if args.docs else []
        for number, path in enumerate(paths):
            text = mask_pii(path.read_text(encoding="utf-8-sig"))
            if text.strip():
                sid = f"doc-a{number}"
                corpus[sid] = text
                locations[sid] = mask_pii(path.relative_to(args.docs).as_posix())
        search = keyword_search(corpus)
        mode = "keyword"
        if args.chroma is not None:
            # R5 requires the same embedder identity as the indexed documents.
            # Do not invent embeddings or silently download/load a default model.
            if not (args.chroma / "library_manifest.json").is_file():
                parser.error("CHROMA_LIBRARY_NOT_FOUND")
            if embedder is None:
                if not args.revision:
                    parser.error("CHROMA_REQUIRES_CACHED_E5_REVISION")
                from rag_research_agent.embed.providers import E5Embedder
                embedder = E5Embedder(revision=args.revision)
            from rag_research_agent.rag.library import Library
            from rag_research_agent.rag.research_chroma import make_chroma_search
            library = Library(args.chroma, embedder=embedder)
            library.open()
            search = make_chroma_search(library.index, embedder, masker=_Masker())
            locations = {c.chunk_id: mask_pii(c.document_id) for c in library.chunks}
            mode = "chroma"
        # The graph preserves caller-supplied metrics; normalize this CLI's list
        # before planning, including duplicates that become equal after masking.
        checklist = tuple(dict.fromkeys(
            mask_pii(item.strip()) for item in [*items, *args.checklist.split(",")] if item.strip()))
        cfg = replace(CONFIGS[args.config], planner=args.planner, extractor=args.extractor, writer=args.writer)
        for name, model in (("planner", planner_model), ("extractor", extractor_model), ("writer", writer_model)):
            if getattr(args, name) == "llm" and model is None:
                parser.error("LLM_REQUIRES_INJECTED_MODEL")
        result = ResearchRunner(search, cfg, masker=_Masker(), planner_model=planner_model,
                                extractor_model=extractor_model, writer_model=writer_model).run(
                                    mask_pii(question), checklist)
        payload = {
            "report": result.report,
            "path": list(result.path),
            "verify_codes": list(result.verify_codes),
            "stopped": result.stopped,
            "estimated_tokens": result.shadow_tokens,
            "estimated": True,
            "end_type": result.end_type,
            "config": args.config,
            "search": mode,
            "required_metrics": list(result.plan.required_metrics),
            "sources": [{"source_id": s.source_id, "location": locations.get(s.source_id, "")}
                        for s in result.sources],
        }
        # Mask the final serialization too: persisted index identifiers can contain PII.
        if args.json:
            rendered = json.dumps(payload, ensure_ascii=False, indent=2)
        else:
            sources = "\n".join(f"- {s['source_id']}: {s['location']}" for s in payload["sources"])
            rendered = (f"# Research report\n\n{result.report or 'NO_EVIDENCE'}\n\n"
                        f"## Sources\n\n{sources or 'NO_EVIDENCE'}\n\n"
                        f"Node path: {' -> '.join(result.path)}\n\n"
                        f"Verification codes: {', '.join(result.verify_codes) or 'PASS'}\n\n"
                        f"Stop code: {result.stopped or 'NONE'}\n\n"
                        f"End type: {result.end_type}\n\n"
                        f"Estimated tokens (shadow, not billing): {result.shadow_tokens}")
        rendered = mask_pii(rendered) + "\n"
        if out is not None:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(rendered, encoding="utf-8")
        print(rendered, end="")
        return 0
    except (OSError, UnicodeError, ValueError, RetrievalUnavailable, EmbeddingError):
        # Never echo document text, query text, local paths or exception messages.
        parser.error("RESEARCH_INPUT_OR_STORE_ERROR")
    finally:
        if library is not None and library.index is not None:
            library.index.close()


if __name__ == "__main__":
    raise SystemExit(main())
