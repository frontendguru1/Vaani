"""Phase 1 quality spike: run every available engine on the same voice + sentences.

    cd backend
    uv run python scripts/benchmark_engines.py --ref ~/clips/me.wav --ref-text "exact words..."

F5-based engines need a SHORT reference (<=12 s) whose transcript matches exactly. If your
main --ref is longer, also pass --short-ref/--short-ref-text. XTTS uses --ref (any length,
repeatable). Outputs go to data/benchmarks/<timestamp>/ with a results.json.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.engines import registry  # noqa: E402
from app.engines.base import EngineError  # noqa: E402
from app.services import audio  # noqa: E402

SENTENCES: list[tuple[str, str, str]] = [
    # (id, language, text)
    ("en1", "en", "Good morning! I hope you slept well, because today we have a lot to get done."),
    (
        "en2",
        "en",
        "My grandmother used to tell us stories every night, and I still remember "
        "how her voice changed for each character.",
    ),
    ("hi1", "hi", "नमस्ते! आज मौसम बहुत सुहाना है, चलो बाहर टहलने चलते हैं।"),
    ("hi2", "hi", "बचपन की यादें हमेशा दिल के सबसे करीब रहती हैं।"),
    ("mix1", "hi", "आज की meeting में हमने नए project के बारे में discuss किया।"),
]


@dataclass
class Row:
    engine: str
    sentence: str
    language: str
    device: str
    compute_s: float
    audio_s: float
    rtf: float  # seconds of compute per second of audio (<1 = faster than real time)
    file: str
    error: str = ""


def run_engine(
    name, refs, ref_text, short_ref, short_text, out_dir, langs
) -> tuple[dict, list[Row]]:
    eng = registry.get_engine(name)
    meta: dict = {"engine": name, "label": eng.label, "license": eng.license}
    avail = eng.availability()
    if not avail.ok:
        print(f"\n== {eng.label}: SKIPPED — {avail.reason}")
        return {**meta, "skipped": avail.reason}, []

    print(f"\n== {eng.label}")
    t0 = time.perf_counter()
    try:
        eng.load()
    except EngineError as exc:
        print(f"   load failed: {exc}")
        return {**meta, "error": str(exc)}, []
    meta["load_s"] = round(time.perf_counter() - t0, 1)
    meta["device"] = eng.device
    meta["version"] = eng.version
    print(f"   loaded on {eng.device} in {meta['load_s']}s ({eng.version})")

    cache = out_dir / "voices" / name
    t0 = time.perf_counter()
    try:
        if eng.needs_transcript:
            profile = eng.create_voice([short_ref], cache, [short_text])
        else:
            profile = eng.create_voice(refs, cache, [ref_text] if ref_text else None)
    except EngineError as exc:
        print(f"   voice failed: {exc}")
        return {**meta, "error": str(exc)}, []
    meta["voice_s"] = round(time.perf_counter() - t0, 2)
    print(f"   voice conditioning in {meta['voice_s']}s")

    rows: list[Row] = []
    for sid, lang, text in SENTENCES:
        if lang not in eng.supported_languages or (langs and lang not in langs):
            continue
        file = out_dir / f"{name}_{sid}.wav"
        t0 = time.perf_counter()
        try:
            res = eng.synthesize(text, profile, lang)
        except Exception as exc:  # noqa: BLE001 - keep benchmarking other sentences
            rows.append(Row(name, sid, lang, str(eng.device), 0, 0, 0, "", str(exc)))
            print(f"   {sid}: ERROR {exc}")
            continue
        compute = time.perf_counter() - t0
        audio.write_wav(file, res.audio, res.sample_rate)
        dur = len(res.audio) / res.sample_rate
        row = Row(
            name,
            sid,
            lang,
            res.device,
            round(compute, 2),
            round(dur, 2),
            round(compute / dur, 2) if dur else 0,
            file.name,
        )
        rows.append(row)
        print(f"   {sid}: {dur:5.1f}s audio in {compute:5.1f}s  (RTF {row.rtf})")

    # Second run of the first sentence: shows warm-model speed.
    first = next((r for r in rows if not r.error), None)
    if first:
        text = next(t for s, _l, t in SENTENCES if s == first.sentence)
        t0 = time.perf_counter()
        res = eng.synthesize(text, profile, first.language)
        warm = time.perf_counter() - t0
        meta["warm_rtf"] = round(warm / (len(res.audio) / res.sample_rate), 2)
        print(f"   warm re-run of {first.sentence}: RTF {meta['warm_rtf']}")
    eng.unload()
    return meta, rows


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--ref", type=Path, action="append", required=True, help="reference clip(s)")
    p.add_argument("--ref-text", default="", help="transcript of the first --ref")
    p.add_argument(
        "--short-ref", type=Path, help="<=12 s clip for F5 engines (default: first --ref)"
    )
    p.add_argument("--short-ref-text", help="exact transcript of --short-ref")
    p.add_argument("--engines", default=",".join(registry.engine_names()))
    p.add_argument("--langs", default="", help="limit to languages, e.g. en,hi")
    p.add_argument("--tag", default="", help="label appended to the output folder")
    args = p.parse_args()

    settings = get_settings()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S") + (f"-{args.tag}" if args.tag else "")
    out_dir = settings.data_dir / "benchmarks" / stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    # Normalise references once: mono 24 kHz WAV.
    refs = [
        audio.convert_to_wav(r.expanduser(), out_dir / "refs" / f"ref{i}.wav", 24_000)
        for i, r in enumerate(args.ref)
    ]
    short_src = args.short_ref.expanduser() if args.short_ref else args.ref[0].expanduser()
    short_ref = audio.convert_to_wav(short_src, out_dir / "refs" / "short.wav", 24_000)
    short_text = args.short_ref_text or args.ref_text
    print(
        f"References: {[f'{audio.duration_seconds(r):.1f}s' for r in refs]}, "
        f"short {audio.duration_seconds(short_ref):.1f}s"
    )

    langs = {x for x in args.langs.split(",") if x}
    results = {"created": stamp, "engines": [], "rows": []}
    for name in [e.strip() for e in args.engines.split(",") if e.strip()]:
        meta, rows = run_engine(name, refs, args.ref_text, short_ref, short_text, out_dir, langs)
        results["engines"].append(meta)
        results["rows"] += [asdict(r) for r in rows]

    (out_dir / "results.json").write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\n{'engine':10} {'sent':6} {'device':8} {'audio':>6} {'compute':>8} {'RTF':>5}")
    for r in results["rows"]:
        print(
            f"{r['engine']:10} {r['sentence']:6} {r['device']:8} {r['audio_s']:6.1f} "
            f"{r['compute_s']:8.1f} {r['rtf']:5.2f} {r['error'][:40]}"
        )
    print(f"\nOutputs: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
