import pytest

from app.services.chunking import chunk_text


def texts(chunks):
    return [c.text for c in chunks]


def test_english_sentences_split_on_terminal_punctuation():
    s = "Hello there, my friend. How are you today? I am doing really well!"
    assert texts(chunk_text(s, min_chars=5)) == [
        "Hello there, my friend.",
        "How are you today?",
        "I am doing really well!",
    ]
    # With the default min (20) the 18-char question merges into the next sentence.
    assert texts(chunk_text(s))[1] == "How are you today? I am doing really well!"


def test_hindi_danda_is_a_sentence_boundary():
    s = "आज मौसम बहुत सुहाना है। चलो बाहर टहलने चलते हैं। शाम को चाय पिएंगे॥"
    out = texts(chunk_text(s, min_chars=5))
    assert out == ["आज मौसम बहुत सुहाना है।", "चलो बाहर टहलने चलते हैं।", "शाम को चाय पिएंगे॥"]


def test_mixed_hindi_english():
    s = "आज की meeting बहुत अच्छी रही। Next week हम launch करेंगे!"
    assert len(chunk_text(s, min_chars=5)) == 2


def test_spans_point_back_into_original_text():
    s = "  First sentence here.\n\nSecond paragraph sentence. Third one is here too.  "
    for c in chunk_text(s):
        assert s[c.start : c.end] == c.text


def test_paragraph_pause_is_longer_than_sentence_pause():
    s = (
        "One sentence that is long enough. Another sentence that is long enough.\n\n"
        "New paragraph starts right here."
    )
    chunks = chunk_text(s, sentence_pause_ms=300, paragraph_pause_ms=900)
    assert [c.pause_after_ms for c in chunks] == [300, 900, 0]
    assert [c.paragraph for c in chunks] == [0, 0, 1]


def test_short_sentences_merge_forward():
    s = "Hi. Okay. This one is the real long sentence here."
    out = texts(chunk_text(s))
    assert out == ["Hi. Okay. This one is the real long sentence here."]


def test_trailing_short_sentence_merges_back():
    s = "This is a perfectly normal sentence. Yes."
    assert texts(chunk_text(s)) == ["This is a perfectly normal sentence. Yes."]


def test_long_sentence_split_at_clauses_within_limit():
    s = (
        "When the rain finally stopped, the children ran outside, splashing through every "
        "puddle they could find, laughing loudly, while their parents watched from the porch."
    )
    chunks = chunk_text(s, max_chars=60)
    assert all(len(c.text) <= 60 for c in chunks)
    assert " ".join(texts(chunks)).replace("  ", " ") == s


def test_spaceless_text_gets_hard_cut():
    s = "a" * 130
    chunks = chunk_text(s, max_chars=50)
    assert [len(c.text) for c in chunks] == [50, 50, 30]


def test_empty_script_yields_nothing():
    assert chunk_text("   \n\n  ") == []


def test_indices_are_sequential():
    s = "Sentence number one is here. Sentence number two is here. Sentence three is here."
    assert [c.index for c in chunk_text(s)] == [0, 1, 2]


def test_ellipsis_and_quotes():
    s = 'She whispered, "Are you sure?" Then she left... without another word.'
    out = texts(chunk_text(s, min_chars=5))
    assert out[0] == 'She whispered, "Are you sure?"'


def test_rejects_tiny_max_chars():
    with pytest.raises(ValueError):
        chunk_text("abc", max_chars=5)
