"""Compare lexical query preprocessing through the same search_lex surface."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rag_research_agent.core.lexical import lex_terms
from rag_research_agent.lab.kiwi_terms import kiwi_terms, KiwiUnavailable
from rag_research_agent.observe import golden
from rag_research_agent.observe.evaluate import hit_at_k, first_hit_rank
from rag_research_agent.rag.library import Library


def compare(items, index, term_functions=None):
    functions = term_functions or {"lex": lex_terms, "kiwi": kiwi_terms}
    results = {}
    for name, terms in functions.items():
        def rank(question):
            hits = index.search_lex(" ".join(terms(question)), k=100)
            best = {}
            for chunk, score, _ in hits:
                best[chunk.document_id] = max(best.get(chunk.document_id, float("-inf")), score)
            return sorted(best.items(), key=lambda v: (-v[1], v[0]))
        rows = golden.to_rows(items, rank, name, k=3)
        evidence = [r for r in rows if r["expected"]]
        ranks = [first_hit_rank(r, name) for r in evidence]
        results[name] = {"hit_at_1": hit_at_k(rows, name, 1), "hit_at_3": hit_at_k(rows, name, 3),
                         "mrr": sum(1/r if r else 0 for r in ranks) / len(ranks) if ranks else None,
                         "rows": rows}
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--set", default=str(ROOT / "data/golden_set.json"))
    ap.add_argument("--corpus", default=str(ROOT / "data/articles.json"))
    args = ap.parse_args(argv)
    try:
        kiwi_terms("설치 점검")
        articles = json.loads(Path(args.corpus).read_text(encoding="utf-8"))
        items = golden.load([args.set], [a["id"] for a in articles])
        from tempfile import TemporaryDirectory
        with TemporaryDirectory(prefix="rra-lex-") as temp:
            lib = Library(temp, embedder="fake").build([(a["id"], a["title"], a["text"]) for a in articles])
            try:
                result = compare(items, lib.index)
            finally:
                lib.index.close()
        print("| 방식 | Hit@1 | Hit@3 | MRR |\n| --- | --- | --- | --- |")
        for name, value in result.items():
            print(f"| {name} | {value['hit_at_1']} | {value['hit_at_3']} | {value['mrr']} |")
        print("\n| 질의 | lex 상위 문서 | kiwi 상위 문서 | 차이 |\n| --- | --- | --- | --- |")
        for item, a, b in zip(items, result["lex"]["rows"], result["kiwi"]["rows"]):
            left, right = a["lex"]["topk"], b["kiwi"]["topk"]
            print(f"| {item['question'].replace('|', '/')} | {left} | {right} | {left != right} |")
        return 0
    except (KiwiUnavailable, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
