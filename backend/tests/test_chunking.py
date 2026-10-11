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


# --- pause markers ---------------------------------------------------------

from app.services.chunking import PauseMarkerError, chunk_script, parse_pause  # noqa: E402


@pytest.mark.parametrize(
    "arg,ms",
    [
        ("", 1000),
        ("1s", 1000),
        (" 1.5 s ", 1500),
        ("2", 2000),
        ("500ms", 500),
        ("2 sec", 2000),
        ("3 seconds", 3000),
        ("250 milliseconds", 250),
        ("60s", 10_000),
    ],
)
def test_parse_pause(arg, ms):
    assert parse_pause(arg) == ms


@pytest.mark.parametrize("arg", ["abc", "1 minute", "-1s", "1s 2s"])
def test_parse_pause_rejects_nonsense(arg):
    with pytest.raises(PauseMarkerError):
        parse_pause(arg)


def test_marker_between_sentences_sets_the_pause():
    s = "First sentence is right here. [pause 2s] Second sentence is right here."
    plan = chunk_script(s, sentence_pause_ms=300)
    assert [c.text for c in plan.chunks] == [
        "First sentence is right here.",
        "Second sentence is right here.",
    ]
    assert [c.pause_after_ms for c in plan.chunks] == [2000, 0]
    assert plan.pause_count == 1 and plan.pause_total_ms == 2000
    for c in plan.chunks:
        assert s[c.start : c.end] == c.text  # spans still point into the script


def test_marker_inside_a_sentence_splits_it():
    s = "And the winner is [pause 1.5s] my grandmother!"
    plan = chunk_script(s, min_chars=5)
    assert [c.text for c in plan.chunks] == ["And the winner is", "my grandmother!"]
    assert plan.chunks[0].pause_after_ms == 1500


def test_consecutive_markers_add_up_and_case_is_ignored():
    s = "Ready to begin now. [PAUSE 1s][pause 500ms] [Pause] Here we go, everybody."
    plan = chunk_script(s)
    assert plan.chunks[0].pause_after_ms == 2500


def test_leading_marker_becomes_lead_in_and_trailing_is_dropped():
    s = "[pause 2s] Hello there, how are you doing? [pause 3s]"
    plan = chunk_script(s)
    assert plan.lead_ms == 2000
    assert len(plan.chunks) == 1 and plan.chunks[0].pause_after_ms == 0


def test_hindi_with_markers():
    s = "आज मौसम बहुत सुहाना है। [pause 1s] चलो बाहर टहलने चलते हैं।"
    plan = chunk_script(s, min_chars=5)
    assert [c.text for c in plan.chunks] == ["आज मौसम बहुत सुहाना है।", "चलो बाहर टहलने चलते हैं।"]
    assert plan.chunks[0].pause_after_ms == 1000


def test_bad_markers_are_reported_not_spoken():
    with pytest.raises(PauseMarkerError, match=r"\[pause abc\]"):
        chunk_script("Hello there friend. [pause abc] Bye now, my friend.")


def test_no_markers_matches_chunk_text():
    s = "One sentence that is long enough. Another sentence that is long enough."
    assert chunk_script(s).chunks == chunk_text(s)
    assert chunk_script(s).lead_ms == 0


def test_only_markers_gives_no_chunks():
    assert chunk_script("[pause 1s] [pause 2s]").chunks == []
