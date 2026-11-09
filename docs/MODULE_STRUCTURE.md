# Module structure (M0)

Source of truth: [DESIGN.ko.md](DESIGN.ko.md) section 3. This page only records what exists after M0; it makes no new decisions.

Package: `src/rag_research_agent/` (renamed from `memvid_guardrail`). Distribution name: `langchain-rag-research-agent`.

| Module | Interface file | Interfaces | Fakes | State after M0 |
| --- | --- | --- | --- | --- |
| `core` | `types.py`, `contracts.py` | `Segment`, `Knobs`, `Candidate`, `EdgeScore`, `CausalLink`, `Brief`, `Status` (+ existing `Chunk`, `IndexManifest`, ...) | n/a | types only, no behaviour |
| `guard` | `protocols.py` | `Masker`, `InputPolicy` | yes | protocols new; `masking.py` unchanged (frozen) |
| `embed` | `providers.py` | `Embedder` | `FakeEmbedder` | unchanged |
| `ingest` | `protocols.py` | `Chunker` | yes | protocol new |
| `ontology` | `protocols.py` | `OntologyLabeler`, `LinkBuilder` | yes | new, interfaces only |
| `store` | `protocols.py` | `VectorStore` | yes | protocol new; memvid adapter unchanged |
| `retrieve` | `protocols.py` | `Retriever`, `Reranker` | yes | protocol new |
| `edge` | `protocols.py` | `EdgeScorer`, `ProtectedPicker` | yes | new, no scoring logic or weights |
| `knobs` | `protocols.py` | `KnobMapper`, `Preset` | yes | new, placeholder mapping only |
| `diet` | `protocols.py` | `TokenBudget`, `Dieter` | yes | new, no reduction logic |
| `compose` | `protocols.py` | `Composer`, `OutputChecker` | yes | new, extractive fake only |
| `rag` | `graph.py`, `chain.py` | `build_graph`, adapters | n/a | unchanged (assembler) |
| `observe` | `protocols.py` | `Tracer`, `Evaluator` | yes | protocol new |
| `lab` | | | | unchanged |

Fakes are test stand-ins, not implementations. Nothing in M0 implements Equalizer logic.

## Enforced by `tests/test_structure.py`

1. Every module declares a maturity tier; stable/incubating code never imports `lab`.
2. Modules other than `core`, `rag` (assembler) and `lab` do not import each other.
3. `langchain`/`langgraph` appear only in `rag` and `ontology/*adapter*` files.
4. `core`, `edge`, `diet`, `knobs`, `compose` import with all optional dependencies blocked.
5. Removing any one module (import blocked) leaves the others importable.

## Known debt (recorded, not hidden)

Two cross-module imports predate M0 and are listed in `KNOWN_DEBT` in the structure test. The test requires the list to match reality, so it can only shrink:

- `ingest` -> `guard` (`chunking.py` uses `guard.masking`; should receive a `Masker`)
- `store` -> `retrieve` (`memvid_store.py` uses `retrieve.keyword.lex_terms`; move to `core` or inject)

## Test baseline (this environment, `memvid-sdk` not installed)

Before rename (main 051dc47): 44 passed, 4 failed, 4 errors. After M0: 57 passed, same 4 failed, same 4 errors. All 8 are in `test_memvid_store.py` / `test_index_lifecycle.py` and fail with `ModuleNotFoundError: memvid_sdk`; they need the `memvid` extra and were not run against the real SDK here.

## After Equalizer v0 (2026-11-09)

Working parts (uncalibrated): `edge/rules.py`, `edge/scorer.py`, `edge/focus.py`, `knobs/mapper.py`, `diet/dieter.py`,
`compose/extractive.py`, `ingest/sentences.py`, assembled by `rag/brief.py` (`build_brief`, parts injected via `Parts`).
Data: `data/golden_rules/research_v1.json`, `data/equalizer/presets_v0.json`, `data/golden_sets/*.json`.
See [EQUALIZER_V0.ko.md](EQUALIZER_V0.ko.md).

## Vector store choice (2026-11-09)

Owner decision: develop with **Chroma** first (`store/chroma_store.py`, extra `chroma`, telemetry off, local files),
keep **memvid** (`store/memvid_store.py`) as a swappable alternative. Both expose `search_vector`, `search_lex`,
`vector_count`, `close` and return `(Chunk, score, rank)`. Reason: memvid writes were intermittently refused on
Windows (`os error 5` / index IO), while reads and results were fine; Chroma is what the owner uses in class.
