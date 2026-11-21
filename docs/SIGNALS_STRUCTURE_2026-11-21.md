# Three-signal structure (2026-11-21)

Status: structure only. Implemented and tested with synthetic values; no real embedding or language model was run (unverified for quality).

## What was added

- `src/rag_research_agent/edge/signals.py` (incubating): `SurprisalScorer` protocol, `FakeSurprisalScorer`, `SegmentSignals`, `rank01`, `collect`, `combine`.
- `tests/test_signals.py`: 6 tests.
- README / README.ko: a short section describing the structure and that further engine development is private.

## What was not added

No tuned weights, gates, thresholds or combination formula. `combine()` is a plain weighted sum and requires explicit weights. Existing modules, data/, profiles/ and existing tests are unchanged.

## Test run (this environment, Python 3.13, optional extras not installed)

| Run | passed | failed | errors | skipped |
| --- | --- | --- | --- | --- |
| Before (without the new files) | 228 | 6 | 15 | 4 |
| After | 234 | 6 | 15 | 4 |

The 6 failures and 15 errors are the same before and after: missing optional packages (`langchain_core`, `langgraph`, `langsmith`, `memvid_sdk`). `test_structure.py::test_removing_any_one_module_leaves_the_others_importable` fails before and after for the same reason (`langsmith` not installed).
