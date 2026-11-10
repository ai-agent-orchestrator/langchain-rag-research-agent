"""Boundary behavior of the real shared keyword tokenizer; no optional dependencies."""
import pytest

from rag_research_agent.core.lexical import lex_terms


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        pytest.param("", [], id="empty"),
        pytest.param(" \t\r\n\v\f", [], id="ascii-whitespace"),
        pytest.param("\u00a0\u2003\u3000", [], id="unicode-whitespace"),
        pytest.param("한글 english 123 한글abc123", ["한글", "english", "123", "한글abc123"], id="mixed-scripts"),
        pytest.param("한 a 1 한글 ab 12", ["한글", "ab", "12"], id="one-character-fragments"),
        pytest.param("ＡＢＣ ａｂｃ １２３ 한글１２", ["ａｂｃ", "１２３", "한글１２"], id="fullwidth-preserved"),
        pytest.param("ａｂｃ abc １２ 12", ["ａｂｃ", "abc", "１２", "12"], id="no-width-folding"),
        pytest.param("한글\u3000english\u00a0123", ["한글", "english", "123"], id="unicode-word-separators"),
        pytest.param("😀 🚀 👩\u200d💻", [], id="emoji-only"),
        pytest.param("😀한글🚀 english🙂 123🎉", ["한글", "english", "123"], id="emoji-around-terms"),
        pytest.param("ab😀cd 한😀글", ["abcd", "한글"], id="emoji-removal-joins-fragments"),
        pytest.param("한글! 한글 english, english 123 123", ["한글", "english", "123"], id="deduplicate-after-cleaning"),
        pytest.param("English english ENGLISH", ["English", "english"], id="case-preserved-uppercase-dropped"),
        pytest.param("CIVIL CRIMINAL FAMILY OTHER OR and Not ｏｒ", ["ｏｒ"], id="labels-and-ascii-operators"),
        pytest.param("!!! --- [PHONE] [EMAIL]", [], id="punctuation-and-uppercase-masks"),
    ],
)
def test_lex_terms_boundary_outputs(query, expected):
    assert lex_terms(query) == expected


@pytest.mark.parametrize("word", ["a" * 100_000, "한" * 100_000], ids=["latin", "hangul"])
def test_very_long_word_is_preserved_and_deduplicated(word):
    assert lex_terms(f"{word}! {word} tail") == [word, "tail"]


def test_repeated_calls_preserve_values_and_order():
    query = "한글 english 123 ａｂｃ 😀 ab😀cd 한글 English OR"
    expected = ["한글", "english", "123", "ａｂｃ", "abcd", "English"]
    for _ in range(30):
        assert lex_terms(query) == expected


def test_mutating_one_result_does_not_affect_subsequent_calls():
    query = "한글 english 123 한글"
    first = lex_terms(query)
    assert first == ["한글", "english", "123"]
    first.clear()
    assert lex_terms(query) == ["한글", "english", "123"]
