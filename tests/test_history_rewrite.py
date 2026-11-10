import pytest

from rag_research_agent.rag.history_rewrite import rewrite_with_history


@pytest.mark.parametrize("word", ["그거", "그건", "그것은", "그게", "이것", "이거", "이건", "해당", "위의"])
def test_demonstratives_expand_even_long_queries(word):
    query = f"{word} 제도가 언제부터 적용되는지 자세하게 설명해 주세요?"
    rewritten, reasons = rewrite_with_history(query, ["육아휴직 급여"])
    assert rewritten == query + " 육아휴직 급여"
    assert reasons == ["demonstrative"]


def test_short_query_without_demonstrative_uses_previous_keywords():
    assert rewrite_with_history("언제부터야?", ["육아휴직 급여"]) == (
        "언제부터야? 육아휴직 급여", ["short_query"]
    )


def test_both_rule_reasons_and_exact_original_preserved():
    query = "  그건\t언제부터야?  "
    rewritten, reasons = rewrite_with_history(query, ["육아휴직 급여"])
    assert rewritten == query + " 육아휴직 급여"
    assert reasons == ["demonstrative", "short_query"]


def test_no_history_returns_original_without_reasons():
    assert rewrite_with_history("그건 언제부터야?", []) == ("그건 언제부터야?", [])


@pytest.mark.parametrize("query", ["육아휴직 급여 지급 조건과 신청 방법을 알려 주세요", "해당화 재배 방법과 계절별 관리 요령을 자세히 설명해 주세요"])
def test_long_independent_query_is_unchanged(query):
    assert rewrite_with_history(query, ["실업급여 신청"]) == (query, [])


@pytest.mark.parametrize("limit", [1, 2, 3])
def test_max_turns_never_adds_older_topics_or_mutates_history(limit):
    history = ["주택임대차 계약", "실업급여 신청", "육아휴직 급여"]
    before = history.copy()
    assert rewrite_with_history("언제부터?", history, max_turns=limit) == (
        "언제부터? 육아휴직 급여", ["short_query"]
    )
    assert history == before


def test_zero_turn_limit_disables_expansion():
    assert rewrite_with_history("그건 언제?", ["육아휴직 급여"], max_turns=0) == ("그건 언제?", [])


def test_negative_turn_limit_is_rejected():
    with pytest.raises(ValueError, match="max_turns"):
        rewrite_with_history("언제?", [], max_turns=-1)


@pytest.mark.parametrize("previous", ["", "  ", "CIVIL [MASK] OR A !"])
def test_no_previous_keywords_means_no_applied_reasons_or_older_fallback(previous):
    assert rewrite_with_history("그건 언제?", ["육아휴직 급여", previous]) == ("그건 언제?", [])


def test_uses_real_lex_terms_and_deduplicates_current_and_previous_terms():
    assert rewrite_with_history("급여?", ["CIVIL [MASK] OR 육아휴직, 급여 급여"]) == (
        "급여? 육아휴직", ["short_query"]
    )
    assert rewrite_with_history("급여?", ["급여 급여"]) == ("급여?", [])


@pytest.mark.parametrize("query", ["", " \t\n"])
def test_blank_current_query_is_preserved(query):
    assert rewrite_with_history(query, ["육아휴직 급여"]) == (query, [])


def test_short_query_character_threshold():
    assert rewrite_with_history("가나다라마 바사아자차", ["육아휴직"])[0] == "가나다라마 바사아자차 육아휴직"
    assert rewrite_with_history("가나다라마 바사아자차카", ["육아휴직"]) == ("가나다라마 바사아자차카", [])
