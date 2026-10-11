from types import SimpleNamespace as NS

import pytest

from app.services.subtitles import Span, build_cues, chunk_spans, to_srt, to_vtt


def ch(text, offset, pause=0, voice=None):
    return NS(text=text, offset_seconds=offset, pause_after_ms=pause, voice_id=voice)


def test_cue_ends_where_its_pause_begins():
    chunks = [ch("Hello there.", 0.5, 350), ch("How are you?", 2.35, 0)]
    spans = chunk_spans(chunks, total_seconds=4.0)
    assert [(s.start, s.end) for s in spans] == [(0.5, 2.0), (2.35, 4.0)]


def test_srt_format_and_timestamps():
    cues = build_cues([Span(0.5, 2.0, "Hello there."), Span(3661.25, 3662.5, "Late line.")])
    assert to_srt(cues) == (
        "1\n00:00:00,500 --> 00:00:02,000\nHello there.\n\n"
        "2\n01:01:01,250 --> 01:01:02,500\nLate line.\n"
    )


def test_vtt_format():
    out = to_vtt(build_cues([Span(0, 1.5, "Hi.")]))
    assert out.startswith("WEBVTT\n\n00:00:00.000 --> 00:00:01.500\nHi.")


def test_long_sentence_wraps_and_splits_into_timed_cues():
    text = (
        "My grandmother used to tell us stories every single night, and I still remember "
        "how her voice changed for each character in every one of them."
    )
    cues = build_cues([Span(10.0, 20.0, text)])
    assert len(cues) >= 2
    for c in cues:
        lines = c.text.split("\n")
        assert len(lines) <= 2 and all(len(line) <= 42 for line in lines)
    assert cues[0].start == 10.0 and cues[-1].end == pytest.approx(20.0)
    assert all(a.end == pytest.approx(b.start) for a, b in zip(cues, cues[1:], strict=False))
    assert " ".join(" ".join(c.text.split("\n")) for c in cues) == text


def test_dialogue_lines_get_speaker_names():
    chunks = [ch("Beta, what are you reading?", 0, 500, None), ch("A story!", 2.5, 0, "v2")]
    spans = chunk_spans(chunks, 4.0, {"v1": "Papa", "v2": "Meera"}, default_voice="v1")
    assert [c.text for c in build_cues(spans)] == [
        "Papa: Beta, what are you reading?",
        "Meera: A story!",
    ]


def test_hindi_text_and_whitespace_normalised():
    cues = build_cues(chunk_spans([ch("आज मौसम\nबहुत सुहाना है।", 0)], 2.0))
    assert cues[0].text == "आज मौसम बहुत सुहाना है।"


def test_tiny_cue_is_stretched_into_the_gap_but_never_overlaps():
    cues = build_cues([Span(0.0, 0.3, "Hi."), Span(0.6, 2.0, "Next.")])
    assert cues[0].end == pytest.approx(0.6)  # stretched to the next cue, not past it
    cues = build_cues([Span(0.0, 0.3, "Hi."), Span(5.0, 6.0, "Next.")])
    assert cues[0].end == pytest.approx(0.8)


def test_missing_timing_is_an_error():
    with pytest.raises(ValueError):
        chunk_spans([ch("x", None)], 1.0)


# --- end to end ------------------------------------------------------------


def test_subtitles_for_a_real_generation_line_up_with_the_audio(db):
    from fastapi.testclient import TestClient

    from app.main import app
    from app.services import audio, generation, storage
    from tests.test_voices_service import make_voice

    s, runner = db
    voice, _ = make_voice(s, runner)
    script = "First sentence is right here. [pause 2s] Second sentence follows now."
    gen, job = generation.create_generation(s, voice_id=voice.id, script=script, language="en")
    runner.run_one(job.id)
    s.expire_all()
    g = generation.get_generation(s, gen.id)
    wav, sr = audio.read_mono(storage.resolve(g.audio_path))
    total = len(wav) / sr

    with TestClient(app) as client:
        r = client.get(f"/api/v1/generations/{gen.id}/subtitles?format=srt&download=true")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/x-subrip")
        assert r.headers["content-disposition"].endswith('.srt"')
        srt = r.text
        vtt = client.get(f"/api/v1/generations/{gen.id}/subtitles?format=vtt").text
    assert "First sentence is right here." in srt and "[pause" not in srt
    assert vtt.startswith("WEBVTT")
    blocks = srt.strip().split("\n\n")
    assert len(blocks) == 2

    def secs(ts):
        h, m, rest = ts.split(":")
        s_, ms = rest.split(",")
        return int(h) * 3600 + int(m) * 60 + int(s_) + int(ms) / 1000

    (a_start, a_end), (b_start, b_end) = [
        tuple(secs(t) for t in b.split("\n")[1].split(" --> ")) for b in blocks
    ]
    assert a_start == pytest.approx(0, abs=0.01)
    assert b_start - a_end == pytest.approx(2.0, abs=0.02)  # the [pause 2s] gap is cue-free
    assert b_end == pytest.approx(total, abs=0.02)


def test_subtitles_need_a_finished_generation(db):
    from app.services import generation
    from app.services.errors import Invalid
    from tests.test_voices_service import make_voice

    s, runner = db
    voice, _ = make_voice(s, runner)
    gen, _job = generation.create_generation(
        s, voice_id=voice.id, script="Not run yet.", language="en"
    )
    with pytest.raises(Invalid, match="once the audio is ready"):
        generation.subtitles(s, gen.id)


def test_two_line_cues_are_balanced():
    cue = build_cues([Span(0, 3, "Welcome to Vaani. My friend studied at IIT.")])[0]
    assert cue.text == "Welcome to Vaani.\nMy friend studied at IIT."  # breaks at the sentence
    plain = build_cues([Span(0, 3, "a quick brown fox jumps over the lazy sleeping dog today")])[0]
    a, b = plain.text.split("\n")
    assert abs(len(a) - len(b)) <= 8, plain.text  # no punctuation: balanced by length
    hi = build_cues([Span(0, 3, "आज मौसम बहुत सुहाना है। चलो बाहर टहलने चलते हैं।")])[0]
    assert hi.text == "आज मौसम बहुत सुहाना है।\nचलो बाहर टहलने चलते हैं।"
