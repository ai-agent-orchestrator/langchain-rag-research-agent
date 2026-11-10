"""Hand-calculated edge cases against the real golden v2 scorer."""
import math

import pytest

from rag_research_agent.observe.golden_v2 import bootstrap_ci, score_item


def question(relevant):
    return {"id": "edge", "question": "alpha beta", "type": "multi_hop",
            "split": "compare", "answerable": bool(relevant), "relevant": relevant}


def evidence(quote, grade=2):
    return {"source": "doc", "quote": quote, "grade": grade}


def hit(text):
    return {"source": "doc", "text": text}


def test_k_larger_than_results_keeps_missing_ideal_units():
    row = score_item(question([evidence("alpha"), evidence("beta", 1)]),
                     [hit("alpha")], accepted=True, k=10)
    # One of two units: Hit=1, Recall=1/2, MRR=1/1; no refusal.
    # DCG=3/log2(2)=3; IDCG=3+1/log2(3), even with only one result.
    assert row["hit"] == 1.0
    assert row["recall"] == 0.5
    assert row["mrr"] == 1.0
    assert row["ndcg"] == pytest.approx(3 / (3 + 1 / math.log2(3)))
    assert row["false_refusal"] == 0.0
    assert row["false_accept"] is None  # Answerable: outside this denominator.


@pytest.mark.parametrize("accepted", [False, True])
def test_zero_results_for_answerable_question(accepted):
    row = score_item(question([evidence("alpha")]), [], accepted=accepted,
                     k=5, kept_texts=[])
    # Zero found / one relevant; DCG/IDCG=0/3, no first rank, retained=0/1.
    for metric in ("hit", "recall", "mrr", "ndcg", "e2e_recall"):
        assert row[metric] == 0.0
    # Refusing an answerable item counts once, irrespective of retrieval.
    assert row["false_refusal"] == (0.0 if accepted else 1.0)
    assert row["false_accept"] is None  # Answerable items are excluded.


@pytest.mark.parametrize("hits", [[], [hit("unrelated")]])
@pytest.mark.parametrize("accepted", [False, True])
def test_no_evidence_question_has_no_retrieval_denominator(hits, accepted):
    row = score_item(question([]), hits, accepted=accepted, k=5, kept_texts=[])
    # There are zero relevance units: Recall and nDCG would divide by zero.
    # Hit/MRR/e2e and refusal are also excluded, rather than scored zero.
    for metric in ("hit", "recall", "mrr", "ndcg", "e2e_recall", "false_refusal"):
        assert row[metric] is None
    # False acceptance is 1/1 if accepted, 0/1 otherwise, even with no hits.
    assert row["false_accept"] == (1.0 if accepted else 0.0)


def test_distinct_quotes_found_in_separate_chunks():
    row = score_item(question([evidence("alpha"), evidence("beta", 1)]),
                     [hit("alpha"), hit("beta")], k=2, kept_texts=["beta"])
    # Two distinct units found: Hit=1, Recall=2/2, MRR=1/1.
    # DCG=IDCG=3+1/log2(3); only beta survives, so e2e=1/2.
    assert row["hit"] == row["recall"] == row["mrr"] == row["ndcg"] == 1.0
    assert row["e2e_recall"] == 0.5


def test_one_quote_split_across_chunks_is_not_reassembled():
    row = score_item(question([evidence("alpha beta")]),
                     [hit("alpha "), hit("beta")], k=2, kept_texts=["alpha beta"])
    # Neither chunk contains the full quote: found=0/1, DCG/IDCG=0/3.
    # Even a full retained quote cannot repair the missing retrieval match.
    for metric in ("hit", "recall", "mrr", "ndcg", "e2e_recall"):
        assert row[metric] == 0.0


@pytest.mark.parametrize("texts", [("alpha", "beta"), ("beta", "alpha")])
def test_ndcg_equal_grade_ties_have_the_same_ideal_score(texts):
    row = score_item(question([evidence("alpha"), evidence("beta")]),
                     [hit(text) for text in texts], k=2)
    # Both gains are 2**2-1=3. Either order gives DCG=IDCG=3+3/log2(3).
    assert row["ndcg"] == 1.0
    assert row["recall"] == 1.0  # Two distinct quotes found / two units.


def test_ndcg_multiple_quotes_in_one_chunk_use_highest_fresh_grade_once():
    relevant = [evidence("alpha", 1), evidence("beta"), evidence("gamma", 1)]
    row = score_item(question(relevant),
                     [hit("alpha beta"), hit("beta"), hit("alpha gamma")], k=3)
    # Rank 1 finds alpha,beta: max(1,3)=3; both units become used.
    # Rank 2 repeats beta: 0. Rank 3 repeats alpha but adds gamma: 1.
    # DCG=3+0/log2(3)+1/log2(4)=3.5; ideal separate gains are [3,1,1].
    assert row["ndcg"] == pytest.approx(3.5 / (3 + 1 / math.log2(3) + 0.5))
    assert row["recall"] == 1.0  # All three units found / three, despite nDCG<1.


def test_mrr_uses_first_match_in_entire_ranking_beyond_k():
    row = score_item(question([evidence("alpha")]),
                     [hit("noise"), hit("noise"), hit("alpha")], k=2)
    # Top two contain zero units: Hit=Recall=0 and DCG/IDCG=0/3.
    # MRR scans all supplied ranks: first match is rank 3, hence 1/3.
    assert row["hit"] == row["recall"] == row["ndcg"] == 0.0
    assert row["mrr"] == pytest.approx(1 / 3)


def test_bootstrap_same_seed_repeats_hand_calculated_interval():
    # Seed 0, pairs drawn from [0,1]: [1,1], [0,0], [1,0], [1,0].
    # Sorted means=[0,.5,.5,1]. Existing floor-index percentiles use
    # int(3*.025)=0 and int(3*.975)=2, so the interval is [0,.5].
    first = bootstrap_ci([0.0, 1.0], seed=0, samples=4)
    second = bootstrap_ci([0.0, 1.0], seed=0, samples=4)
    assert first == second == [0.0, 0.5]


@pytest.mark.parametrize("seed,samples", [(0, 1), (7, 25)])
def test_bootstrap_one_observation_collapses_to_that_value(seed, samples):
    # Every size-one resample is [.25], mean=.25; both endpoints equal .25.
    assert bootstrap_ci([0.25], seed=seed, samples=samples) == [0.25, 0.25]
