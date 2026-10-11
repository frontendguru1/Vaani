# CLAUDE.md — Vaani (वाणी)

Vaani is a personal, **fully local** voice-cloning app: upload/record clips of a person → clean + quality-check → save a named Voice → type an English/Hindi (or Hinglish) script → get audio in that voice. Runs **only on the local machine**: a Mac with Apple Silicon (M1 or newer, macOS 13+, 16 GB RAM recommended), with nothing deployed anywhere. Prerequisites are listed in README → "Prerequisites". **No cloud APIs, no telemetry, works offline after the models are downloaded once.** Audio of real people (including a child) lives in `data/`, which is gitignored. Every Voice needs a **consent note**; generation is blocked without one. Personal/family use only — several model weights are non-commercial. The full original brief is `vaani-claude-code-prompt.md` (local only, gitignored — not in the repo).

## Current status

- **Phase 0 — Scaffolding: DONE (2026-10-11).**
- **Phase 1 — Quality spike: BUILT, listening decision PENDING.** `backend/scripts/benchmark_engines.py` works for all three engines. Only a *synthetic* reference (macOS "Rishi" voice) has been benchmarked so far — it proves the pipeline, not cloning quality. The owner still needs to (a) supply a real 15–60 s clip + transcript and listen, (b) finish the IndicF5 Hugging Face token login. XTTS-v2 is the working default until then.
- **Phase 2 — Backend core: DONE (2026-10-11).** Voices (upload → clean → quality → voiceprint as a job), library CRUD + hard delete, engine registry + 3 engines, generation with chunking + SSE progress + stitching + MP3, history/regenerate/delete, consistency check. 69 tests.
- **Phase 3 — Frontend: DONE (2026-10-11).** Voices (bento library, create dialog with drop zone, mic recorder, per-file quality cards, SSE-driven processing stepper + voiceprint + flourish, rename, two-step delete), Generate (voice/engine/language/speed, script editor with live sentence highlight, progress orb, result player with playback-synced highlight, WAV/MP3), History (play, regenerate, delete). Verified with Playwright (desktop, 390px, reduced motion). 15 frontend tests.
- **Phase 4 — in progress.** Done: **auto-transcription** (mlx-whisper large-v3-turbo; Transcribing step on voice creation, Clips dialog to play / read / correct phrases, one-click transcribe from Generate when F5/IndicF5 is picked). Done: **pronunciation dictionary** (Pronunciation page with Try-it, chips on Generate); **pause markers** (`[pause 1s]` etc., chips in the editor, insert buttons); **multi-voice dialogue** (`[Name]: …` lines); **subtitle export** (SRT/VTT); **12 built-in voices** (6 female, 6 male XTTS studio speakers). The owner picks the next nice-to-have. Pending: real-voice listening test.
- Known issues: F5-MLX and IndicF5 outputs come out shorter than XTTS's for the same sentence (possible clipping), and IndicF5 is ~20× slower than real time on CPU. Whisper's Hindi has small spelling slips (e.g. परिक्षन for परीक्षण), so check transcripts in the Clips dialog before relying on F5/IndicF5.
- **Security review done 2026-10-11** (see "Security model" below); all confirmed findings fixed with tests.

## Stack (versions actually installed)

| Layer | Choice |
|---|---|
| Backend | Python 3.11.5 (Homebrew), uv 0.13, FastAPI 0.143, Uvicorn 0.54, SQLAlchemy 2, Alembic, pydantic-settings, python-ulid |
| ML (main venv) | torch 2.14.1 (MPS ok), torchaudio 2.11, coqui-tts 0.27.5, transformers 4.57.6 (pinned <5), librosa, mlx-whisper 0.4.3 (model `mlx-community/whisper-large-v3-turbo`, 1.6 GB, MIT, in `data/models/whisper/`) |
| Engine venvs | `.venvs/f5mlx` (Py 3.11, f5-tts-mlx 0.2.6, mlx 0.32.3), `.venvs/indicf5` (Py 3.10, IndicF5 from git) — see `backend/workers/README.md` |
| DB | SQLite `data/vaani.db`, WAL + foreign keys on; `DATABASE_URL` overrides it |
| Frontend | Node 22.23 (Homebrew `node@22`, keg-only), pnpm 10, Vite 8, React 19, TypeScript 7, Tailwind 4 (`@tailwindcss/vite`), `motion` 14, React Router 7, TanStack Query 5, Radix Dialog + Slider, lucide-react, Vitest 5 |
| Fonts | Bundled via @fontsource (Inter Variable, JetBrains Mono Variable, Noto Sans Devanagari) — no CDN, works offline |
| Audio | ffmpeg 9.0.2 (Homebrew) |

## Commands

```bash
# Node 22 is keg-only — prefix frontend commands or put it on PATH:
export PATH=/opt/homebrew/opt/node@22/bin:$PATH

# Setup
cd backend && uv sync                       # creates backend/.venv (Python 3.11)
cd frontend && pnpm install

# Run (one command each)
cd backend && uv run vaani-dev              # migrates, then uvicorn --reload on 127.0.0.1:8000
cd frontend && pnpm dev                     # http://localhost:5173, proxies /api -> :8000

# Test / lint
cd backend && uv run pytest && uv run ruff check . && uv run ruff format --check .
cd frontend && pnpm test && pnpm lint       # pnpm build = typecheck + bundle

# DB maintenance
cd backend && uv run vaani init-db | migrate | check
uv run vaani make-migration "add voices"    # autogenerate — ALWAYS review the file
uv run vaani reset-dev-data [--yes]         # deletes voices/generations/benchmarks + DB; keeps models

# Benchmark (outputs + results.json in data/benchmarks/<stamp>/)
cd backend && uv run python scripts/benchmark_engines.py --ref ~/me.wav --ref-text "exact words" \
    [--short-ref ~/me_10s.wav --short-ref-text "..."] [--engines xtts,f5_mlx,indicf5] [--tag name]
VAANI_XTTS_DEVICE=cpu uv run python scripts/benchmark_engines.py ...   # force CPU for comparison
```

## Directory map

```
backend/app/
  main.py          FastAPI app; sets PYTORCH_ENABLE_MPS_FALLBACK before any torch import
  config.py        Settings (env prefix VAANI_, reads repo-root .env); data_dir resolves from repo root
  db.py            make_engine() (SQLite pragmas), SessionLocal, get_session dependency
  cli.py / dev.py  `vaani` maintenance CLI / `vaani-dev` server launcher
  api/v1/          one router per feature; registered ONLY in api/v1/__init__.py
  services/        business logic, no HTTP:
                     voices.py (create/list/update/delete, ensure_profile = voiceprint cache)
                     generation.py (create, job handler, regenerate, delete, mp3)
                     jobs.py (single worker thread + SSE pub/sub) · preprocessing.py · quality.py
                     analysis.py (numpy VAD/segments) · chunking.py · stitching.py · audio.py (ffmpeg)
                     transcription.py (mlx-whisper; best_window picks a transcribed ≤N s phrase run)
                     storage.py (data/ layout, rel paths) · maintenance.py (consistency) · errors.py
  models/          ORM; base.py has Base (naming convention), IdMixin (ULID), TimestampMixin
  schemas/         pydantic request/response models
  engines/         base.py (TTSEngine ABC), registry.py, xtts.py (in-process),
                     subprocess_engine.py + f5_mlx.py + indicf5.py (worker processes)
backend/workers/     engine workers run inside .venvs/<name>; JSON-lines protocol (_protocol.py)
backend/scripts/     benchmark_engines.py
backend/migrations/  Alembic; files named YYYYMMDD_<rev>_<slug>.py
backend/tests/       conftest points VAANI_DATA_DIR at /tmp/vaani-test-data (never real data/)
frontend/src/
  styles/tokens.css  ALL colours/radii/shadows/blurs (CSS vars); index.css maps them into Tailwind @theme
  motion/tokens.ts   ALL durations/easings/springs/variants
  components/        shared UI: AppShell (sidebar / mobile tab bar, PageHeader), Button, Modal (Radix),
                     Toasts, Waveform (+ peaks.ts, width-based bars, draw-in), AudioPlayer, Orb,
                     ScoreRing/RatingPill, ProgressRing, EmptyState, Aurora, Logo
  features/voices/   VoicesPage, VoiceCard, CreateVoiceDialog, FileCard, Dropzone, Recorder, Voiceprint
  features/generate/ GeneratePage, ScriptEditor (textarea + mirrored backdrop for highlighting)
  features/history/  HistoryPage
  features/pronunciation/ PronunciationPage (+ AppliedChips, reused on Generate)
  features/health/   api.ts (health probe used by the sidebar status line)
  lib/               api.ts (types + endpoints; XHR `upload()` for real upload progress),
                     useJobEvents.ts (SSE hook), voiceColor.ts (per-voice hue), format.ts
data/                gitignored: vaani.db, voices/, generations/, benchmarks/, models/
```

## Architecture notes

- **API:** everything under `/api/v1`. Routes stay thin; services take a `Session` and are testable without HTTP.
- **Config:** `app.config.get_settings()` (cached). Feature flags: `VAANI_FEATURES=a,b` → `settings.feature_enabled("a")`.
- **DB:** ULID string PKs (`IdMixin`), `created_at`/`updated_at` on every table (`TimestampMixin`), JSON columns for per-engine settings. Large artefacts are files under `data/`; rows store relative paths. Deletion is a hard delete of rows + files. Avoid SQLite-only SQL. Alembic runs in `render_as_batch` mode so SQLite ALTERs work.
- **Engines:** `TTSEngine` ABC (`load/unload/create_voice/synthesize`, `supported_languages`, `max_chunk_chars(lang)`, `availability()`), `@register` + `ENGINE_MODULES` in registry.py; instances are singletons so models stay loaded. XTTS runs in-process. F5-MLX and IndicF5 run as long-lived worker processes in their own venvs (dependency conflicts); `SubprocessEngine` speaks JSON lines over stdin/stdout, audio via WAV files, worker stderr → `data/logs/<engine>.log`.
- **Voiceprints:** `voices.ensure_profile(voice, engine)` returns the cached conditioning (XTTS latents `.pt`, or a 24 kHz ref clip + transcript for F5 engines), recomputing only if missing or the engine version changed. Row in `voice_engine_profiles`, files in `data/voices/<id>/engines/<engine>/`. XTTS uses the cleanest segments up to 60 s.
- **Jobs:** `JobRunner` = one daemon thread + FIFO → only one job touches a model at a time. Kinds: `create_voice`, `generate`. Handlers report via `ctx.progress(fraction, step, message, event=..., **data)` → row update (throttled) + SSE publish. `/jobs/{id}/events` sends a `snapshot` first, then events until `succeeded`/`failed`, with 15 s keep-alives. Jobs left running at startup are marked failed ("Interrupted").
- **Generation flow:** chunk (`.?!।॥`, merges <20-char sentences, splits >`max_chunk_chars` at clauses; XTTS en 230 / hi 140) → per-chunk synth (events `chunk_started` carry char `start/end` for highlighting) → `stitch()` trims chunk silence, 8 ms fades, inserts sentence/paragraph pauses → `output.wav`; MP3 made on first request.
- **Transcription:** `voice_samples.transcript_segments` = Whisper phrases `[{start,end,text}]` in the processed clip; `transcript_source` = `user` (typed or corrected, never overwritten) | `whisper`. Runs as a step of `create_voice` (setting `VAANI_TRANSCRIBE_ON_CREATE`, never fails the voice) or as job `transcribe_voice` (`POST /voices/{id}/transcribe`). `PUT /voices/{id}/samples/{sid}/transcript {texts}` corrects phrase by phrase. Transcript engines get their reference from `_transcript_reference`: a typed transcript for a short clip, else `best_window` (longest run of phrases ≤ engine `max_ref_seconds`), cut to `engines/<eng>/ref_src.wav`. Changing transcripts drops transcript-engine voiceprints (`invalidate_transcript_profiles`).
- **Voice accuracy (2026-10-11, measured on the owner's real 13-clip English voice):** speaker similarity (SpeechBrain ECAPA cosine vs the voice's own clips; same-person clips score 0.81–0.92). XTTS with the old call settings: 0.579 and 6.2 % WER (dropped words). XTTS with the model's tuned settings: 0.634, 0 % WER, 0.63× real time. **F5-TTS: 0.806, 0 % WER, ~2.9× real time (Euler/16).** Hindi (synthetic ref): IndicF5 0.857 / 3.8 % CER but ~10× slower than XTTS 0.755 / 12 %. On the owner's English-recorded voice, IndicF5 Hindi scored 0.81 but **added babble not in the script and garbled words** (English reference clip + English transcript into an Indic-only model), and took 8 min for 42 s of audio; XTTS Hindi was intelligible with an English accent (0.68). So IndicF5 is only suggested as "most accurate" for voices whose language is Hindi; otherwise the hint says it needs a Hindi recording first. Hence `generation.recommend_engine` (`VAANI_DEFAULT_ENGINE=auto`): English + a transcribed clip → F5; Hindi → XTTS with IndicF5 offered; built-ins → XTTS.
- **Similarity / speaker check:** `services/similarity.py` (ECAPA, CPU, model in `data/models/speechbrain/`, real files via `LocalStrategy.COPY_SKIP_CACHE`). `voices.voice_embedding()` builds a **medoid-based** robust centroid (a plain mean let one intruder of three survive), stores `voices.embedding_path` (.npy), and writes each segment's `match`. Segments with match < 0.45 are left out of the voiceprint (`_reference_segments`); `_transcript_reference` prefers the best-matching clip. During voice creation `quality.apply_speaker_check` replaces the pitch-spread "multiple speakers" guess (false alarm on 5 of 13 real child clips, all matching at ≥0.81) with `different_speaker` only where the model disagrees. Every single-speaker generation stores `generations.similarity`; the UI shows "Sounds very close… 86%" and "Compare with the original". Separate load and run locks: one shared lock deadlocked the first real voice creation.
- **XTTS settings:** `create_voice` passes the model config's `gpt_cond_len=30`, `gpt_cond_chunk_len=4`, `max_ref_len`, `sound_norm_refs` (the method defaults used only the first 6 s), and `synthesize` starts from the config's temperature/top_k/top_p/length & repetition penalties (inference() defaults to repetition_penalty 10 vs the config's 5). `XTTSEngine.PROFILE_REV` is in the version string, so bumping it rebuilds cached voiceprints. Built-ins rebuild from studio latents.
- **F5 worker:** output length = reference frames + reference speaking rate × text length (upstream heuristic; the bundled duration predictor cut 4–5 s sentences to ~2 s). Default solver Euler with 16 steps (same similarity as RK4/8, ~20 % faster; Euler/8 garbled 35 % of words).
- **Built-in voices:** `services/builtin_voices.py`. `CATALOG` = 12 XTTS studio speakers from `speakers_xtts.pth` (part of the model download, CPML). Gender was chosen by **measured median pitch** (female 197–237 Hz, male 93–116 Hz); speakers whose pitch didn't match their name's apparent gender were excluded, not guessed. `voices.source` = user|builtin, plus `builtin_key` and `gender`. Seeding runs once at first start (`app_settings.builtin_voices_seeded`, set only after the job is queued; disable with `VAANI_SEED_BUILTIN_VOICES=false`), or via `POST /voices/builtin/restore`. Each voice gets the speaker's latents as its XTTS voiceprint (`TTSEngine.create_builtin_voice`) and an ~8 s sample spoken from `SAMPLE_TEXT` (`kind=builtin`, `transcript_source=builtin`, exact), which serves as the preview and as the F5/IndicF5 reference. No upload-quality rating (it would wrongly call a short sample "Poor"). Deleting one works; Restore brings it back.
- **Subtitles:** `services/subtitles.py` (pure) + `generation.subtitles()` + `GET /generations/{id}/subtitles?format=srt|vtt&download=`. Cue i runs from `offset_seconds` to the next chunk's offset minus this chunk's pause (last cue: file end), so pauses stay cue-free. Text is the original chunk text, never `spoken_text`. Lines wrap at 42 characters, 2 lines per cue, preferring a break after sentence/clause punctuation (incl. `।`) and otherwise balancing by length. Longer sentences become several cues timed by character share; cues under 0.8 s stretch into the following gap without overlapping. Dialogue cues are prefixed "Name: ".
- **Dialogue:** `services/dialogue.py`. A `[Name]:` tag at a line start (not `[pause…]`) hands the following text to the voice with that name (case and spacing ignored). Untagged text goes to the selected voice. Unknown or duplicate names → 422 `unknown_speaker`/`ambiguous_speaker`. `generation._plan()` chunks each turn with `chunk_script` (spans shifted into script coordinates); a marker at a turn's start replaces the turn pause (`VAANI_PAUSE_TURN_MS`, 500). `generation_chunks.voice_id` = speaker (NULL = the generation's voice); `generation.settings["speakers"]` lists every speaker. The job ensures one voiceprint per speaker, and `chunk_started` events carry `voice_id` (the UI tints the orb and highlight). **`delete_voice` also deletes any generation the voice spoke in**, even if another voice owns it. Every speaker must be ready, have consent, and meet transcript-engine needs.
- **Pause markers:** `chunking.chunk_script()` (used by `create_generation`) finds `[pause …]` (`PAUSE_RE`, case-insensitive): blank = 1 s; `1s`, `1.5 sec`, `2` (seconds), `500ms`; max 10 s per marker. Text between markers is chunked with `chunk_text`, so a marker mid-sentence splits it. Each marker run (they add up) **replaces** the pause after the previous chunk. A leading marker becomes `generation.settings["lead_pause_ms"]`, which `stitch(lead_ms=)` puts before chunk 0; trailing markers are dropped. Unreadable markers raise `PauseMarkerError` → 422 `bad_pause`, so they're never spoken. Spans still index the original script, so highlighting skips markers. The frontend mirrors the parser in `lib/pauses.ts` (keep the two in sync).
- **Pronunciation:** `services/pronunciation.py`. `apply(text, language, entries)` is pure: whole-word matches (word chars include all of Devanagari, because `\w` misses matras), longest term first, single pass (no cascades), optional per-language scope and case sensitivity, multi-word terms tolerate any whitespace. It's applied per chunk in `create_generation`; the result goes in `generation_chunks.spoken_text` (NULL when nothing changed), the script and chunk `text` stay untouched so highlighting still lines up, and the job synthesizes `spoken_text or text`. Regenerate re-applies the current dictionary. API: `/pronunciations` CRUD + `POST /pronunciations/preview`.
- **Delete:** `delete_voice` removes rows (FK cascade: samples, profiles, generations, chunks; jobs by id) and folders, and returns `leftover_paths` (must be empty). `vaani check` finds orphans both ways.
- **Frontend motion:** `<MotionConfig reducedMotion="user">` wraps the app, so transforms are dropped under prefers-reduced-motion and opacity fades remain. Use `fadeOnly()` for hand-rolled motion. Progress visuals must be driven by backend events, never faked.
- **Frontend data:** TanStack Query keys `["voices"]`, `["generations"]`, `["engines"]`, `["health"]`; lists poll every 2 s only while something is processing. Jobs: `useJobEvents(jobId, onEvent)` opens an EventSource on `/jobs/{id}/events`, so add new event types to its list. Route transitions live in `App.tsx` (`AnimatedRoutes` passes the frozen `location` to `<Routes>`).
- **Design identity:** the one bold element is the per-voice colour (`voiceColors(id)`, oklch hue from the id) used on the card, waveform, orb and history stripe. No all-caps eyebrows and no "A · B" meta strings; monospace only for numbers and timers.

## Security model

Single local user, no login. The threat is *other websites in the same browser* reaching 127.0.0.1. `app/security.py`:
- `TrustedHostMiddleware` (`VAANI_ALLOWED_HOSTS`, default localhost/127.0.0.1/[::1]) blocks DNS rebinding.
- `OriginGuard` refuses non-GET requests whose `Origin` isn't in `VAANI_ALLOWED_ORIGINS` (the Vite and API origins) or whose `Sec-Fetch-Site` is `cross-site`. This blocks cross-site multipart/bodiless POSTs, which skip CORS preflight. Requests without an Origin (curl, scripts) are allowed.
- It also enforces a request `Content-Length` cap (`VAANI_MAX_UPLOAD_MB`, 1 GB) and requires a length on multipart; `voices.copy_limited` caps each file at 200 MB while streaming.
- ffmpeg/ffprobe: `audio.check_format` allowlists container formats (ffmpeg sniffs content, so a ".mp3" could be an HLS/concat playlist), `-protocol_whitelist file,pipe`, and 180 s timeouts.
- Workers: reader thread + timeouts (load 20 min, call 5 min); a hung worker is killed and the job fails instead of freezing the queue.
- `trust_remote_code` (IndicF5) is pinned to reviewed commit `fb652a9`. Re-review `model.py` before bumping it.
- `storage.resolve` refuses paths outside `data/`; upload names go through `safe_filename`; `torch.load` uses the safe default `weights_only=True`.

## Decision log

- **2026-10-11** uv instead of pip/venv: coqui-tts now recommends it, and it is fast. Python pinned to 3.11 (`backend/.python-version`).
- **2026-10-11** Node 22 installed keg-only beside the global Node 18 (Vite 8 needs ≥20.19). `.nvmrc` = 22.
- **2026-10-11** ULIDs for ids (sortable, URL-safe), stored as `String(26)`.
- **2026-10-11** Fonts self-hosted via @fontsource for the offline requirement.
- **2026-10-11** Radix and WaveSurfer deferred to Phase 3 (added when a component needs them; no speculative deps).
- **2026-10-11** This repo uses a repo-local git identity (`git config user.name/user.email`), separate from the machine's global one.
- **2026-10-11** Project brief removed from the public repo at the owner's request (rewrote the single commit, force-pushed). It stays local + gitignored.
- **2026-10-11** One venv per conflicting engine + worker processes, rather than one venv with pinned compromises (IndicF5 needs transformers<4.50, coqui needs >=4.57).
- **2026-10-11** **XTTS defaults to MPS.** Benchmark (synthetic ref): CPU RTF ≈ 1.45, MPS RTF ≈ 0.5 warm (first sentence ~1.4 = warm-up). No hang with coqui-tts 0.27.5 + torch 2.14; MPS output matched CPU on pitch (≈115 Hz = reference) and spectral flatness. `VAANI_XTTS_DEVICE=cpu` forces CPU.
- **2026-10-11** F5-MLX: works after a compat shim (see Gotchas) but RTF 2.5–5.5 on an M1-class Mac (slower than XTTS on MPS) and outputs look short. Not chosen as default.
- **2026-10-11** Quality checker is pure numpy + librosa.yin (no ML VAD): energy VAD with 3rd-percentile noise floor; SNR reported as `null` when there are no pauses to measure against; pitch-spread IQR > 6.5 semitones → "maybe multiple speakers" (heuristic, says so).
- **2026-10-11** Preprocessing uses only ffmpeg filters (highpass, optional `afftdn` denoise, silenceremove ×2 with areverse, `loudnorm` −20 LUFS) — no DeepFilterNet/Demucs download needed.
- **2026-10-11** **Engine choice still awaiting the owner's listening test on a real clip.**
- **2026-10-11** IndicF5 benchmark (Hindi synthetic ref, CPU): RTF ≈ 16–23 (a 3–4 s clip takes 64–91 s), and outputs are shorter than XTTS's (3.9 s vs 7.8 s for the same sentence). XTTS on MPS for the same Hindi lines: RTF ≈ 0.6. **XTTS stays default**; IndicF5 kept as an optional engine for a listening comparison.
- **2026-10-11** Custom SVG waveform instead of WaveSurfer: themeable, draw-in animation, ~100 lines, no dependency. Native `<select>` for engines (accessible); Radix only for Dialog + Slider.
- **2026-10-11** Datetimes: `UTCDateTime` TypeDecorator, since SQLite returned naive datetimes and the UI showed "5 h ago" in IST. Same column type underneath, so no migration.
- **2026-10-11** Voice-level quality summary carries clip reasons up ("1 of 2 clips: …") so every rating has a reason (an "Okay" with no reason was showing).
- **2026-10-11** Auto-transcription with **mlx-whisper large-v3-turbo** (1.6 GB) over small (0.48 GB, weaker Hindi) and faster-whisper (CPU-only on Mac). Runs in the main venv, loaded once. Measured: English clip transcribed perfectly in 4 s including first load; Hindi in 1.1 s with minor spelling slips → per-phrase correction UI.
- **2026-10-11** Orb redesigned at the owner's request ("feel like AI is happening"): rotating conic halo, drifting blobs inside the sphere, orbiting particles, travelling ray ring; voiceprint gets a ripple + slow rotation through every step. Both are still under reduced motion.
- **2026-10-11** Worker engines set `HF_HUB_OFFLINE=1` once their weights are cached (offline requirement); XTTS skips its downloader when `model.pth` exists.

## Conventions

- **Never commit secrets or private data.** No tokens, keys, `.env`, `data/` or the local brief. `.githooks/pre-commit` blocks token/key patterns and those paths (enable per clone: `git config core.hooksPath .githooks`). The HF token lives only in `~/.cache/huggingface/token`. Before every push, scan the staged diff.
- **Commits:** `type(scope): summary` + `Problem:` / `Solution:` body. Types: feat, fix, refactor, docs, test, chore. Scopes: backend, frontend, db, engines, docs. One commit per phase minimum; update this file in the same commit.
- **Python:** ruff (line 100, rules E,F,I,B,UP; B008 ignored for FastAPI `Depends`). Type hints everywhere.
- **Add a migration:** change the model → `uv run vaani make-migration "msg"` → read and fix the generated file → `uv run pytest` (`test_models_match_migrations` fails if a model drifted from migrations).
- **Add an API route:** `app/api/v1/<feature>.py` with `router = APIRouter(...)` → append the module to the tuple in `api/v1/__init__.py` → logic goes in `services/`.
- **Add an engine:** subclass `TTSEngine` (or `SubprocessEngine` + a `workers/<name>_worker.py` and a `.venvs/<name>`), decorate with `@register`, add the module to `ENGINE_MODULES`. API/UI pick it up from `/api/v1/engines`.
- **Add a background job:** `@job_handler("kind")` in a service, `get_runner().submit(session, "kind", payload, ...)`, optional `@on_job_failure("kind")` to mark your rows failed.
- **Testing services:** use the `db` fixture → `(session, runner)`; call `runner.run_one(job.id)` to run a job synchronously, then `session.expire_all()`. `tests/fakes.py` registers a `fake` engine (the default in tests).
- **Add a frontend feature:** `src/features/<name>/{api.ts, Component.tsx, Component.test.tsx}`.
- **Add an animation:** import from `src/motion/tokens.ts` (`variants`, `transition`, `spring`, `press`). Never inline durations or easings. Animate transform/opacity only.
- **Colours etc.:** only through tokens (`var(--…)` or the Tailwind names mapped in `index.css`).

## Gotchas

- **Node 18 is still the global default.** Use `/opt/homebrew/opt/node@22/bin` or `pnpm` fails on Vite 8.
- **XTTS-v2 on MPS** was reported to hang (coqui issue #3649) — it does NOT with coqui-tts 0.27.5 + torch 2.14 here. First load downloads 2.1 GB into `data/models/tts/` (accepts CPML via `COQUI_TOS_AGREED=1`); later loads take ~30 s.
- **transformers must stay <5**: coqui-tts 0.27.5 imports `isin_mps_friendly`, which 5.x removed (ImportError on `import TTS`).
- **f5-tts-mlx 0.2.6 vs mlx 0.32**: `mx.random.normal((ch, dur))` fails because `dur` is an mx scalar. `workers/f5mlx_worker.py` wraps `mx.random.normal` to cast shapes to int. Also don't import `f5_tts_mlx.generate` (needs PortAudio) — the worker re-implements its loop with one loaded model.
- **Worker stdout is the protocol.** `_protocol.serve()` redirects fd 1 to stderr, but imports can print earlier, so the parent skips non-JSON lines.
- **IndicF5 venv pins** (setup.py doesn't pin, requirements.txt does): `transformers<4.50` (5.x builds models on the meta device and IndicF5's model.py loads its vocoder with real tensors → "Tensor on device cpu is not on the expected device meta"), `numpy<=1.26.4`, `datasets<4` (5.x needs a newer huggingface_hub than transformers 4.49 allows), plus `torchcodec` (newer torchaudio needs it to load audio). See `backend/workers/README.md`.
- **Offline switch**: worker engines get `HF_HUB_OFFLINE=1` only after one successful load (marker `data/models/.<engine>-loaded-once`). Checking the main repo cache isn't enough, because IndicF5 downloads its vocoder separately on first load.
- **Dev server reloads on every backend edit** — if someone is using the app at the time, a running job is interrupted (marked "Interrupted").
- **HF token location**: `hf auth login` writes `~/.cache/huggingface/token`; workers get `HF_HOME=data/models/hf` for weights, so we pass `HF_TOKEN_PATH` explicitly.
- **Uploads**: allowed extensions in `voices.ALLOWED_EXTENSIONS` (incl. aiff/aif — macOS's native format). FastAPI `Form(...)` rejects empty strings before our validators, so required text fields use `Form("")` and the service validates (gives a proper `code`).
- **Test sessions go stale** after `runner.run_one()` (the job used other sessions) → `session.expire_all()`.
- **uvicorn --reload unloads the models** on every backend edit, so the next job reloads XTTS (~30 s). The generation job reports a `loading_model` step for this; don't mistake it for slowness.
- **Playwright**: the system has no project-local Playwright; scripts borrow `~/Projects/career-ops/node_modules/playwright` via `createRequire`. Full-page phone screenshots draw the fixed tab bar mid-page (capture artefact).
- **Motion + SVG rotate:** motion applies `transform-box: fill-box`, so `rotate` on an SVG child spins it around its own box. For radial layouts wrap each element in `<g transform="rotate(deg cx cy)">` (the orb's rays all stacked at the top before this).
- **Migrations and the dev server:** `vaani-dev` migrates only at start; hot reloads don't. After adding a migration run `uv run vaani migrate`, or the running app hits missing columns.
- **Tests must not run real Whisper:** conftest sets `VAANI_TRANSCRIBE_ON_CREATE=false`; tests monkeypatch `transcription.transcribe_file`. (Forgetting this made the suite take 4 min.)
- **React Query caches previews by text**: after changing the dictionary, invalidate `["pron-preview"]` as well as `["pronunciations"]` (`useRefreshDictionary`), or the Try-it box and Generate's chips show stale results. There's a regression test.
- **Never run `vaani make-migration` as a probe:** it writes a revision even with no changes, and the dev server auto-applies it on reload. Deleting it then leaves the DB on an unknown revision; fix with `alembic stamp <head> --purge`.
- **Tests stub the speaker model** (autouse fixture in conftest); one test exercises the real locking with a stand-in encoder. `VAANI_DEFAULT_ENGINE=fake` in tests forces the engine, or the recommender would pick real F5.
- **Migrations run on every server start** (`main.lifespan` → `upgrade_to_head`), including hot reloads. Before this, new code briefly ran against an old schema and the owner's delete/playback requests 500'd with "no such column".
- **VoiceProfile.file_keys()** decides which data values are cache files (by extension). The old "every string is a file" check made a profile holding a text value (a speaker name) look broken, so it was rebuilt every time.
- **Editor caret after inserts** must be restored synchronously (`pendingCaret` + `useLayoutEffect` in ScriptEditor). A `requestAnimationFrame` let fast typing land mid-text; there's a regression test.
- **zsh: `GID` and `UID` are read-only integer variables.** Don't use them as shell variable names in Bash tool commands ("bad math expression").
- **Vite build** warns that the bundle is over 500 kB (React + motion + Query). Harmless for a local app.
- **IndicF5** pins `transformers<4.50`, `numpy<=1.26.4` and installs a module named `f5_tts`; coqui-tts 0.27.5 needs `transformers>=4.57`. **Separate venv** (`.venvs/indicf5`, Python 3.10). The model is gated on Hugging Face: the user must accept the terms and log in.
- **F5-TTS MLX** needs a mono 24 kHz reference of about 5–10 s plus its transcript. Likely English-only.
- **Tests** must never point at `data/`. conftest overrides `VAANI_DATA_DIR`/`DATABASE_URL` before app import.
- `motion/react` re-exports framer-motion 14. `MotionConfig`, `useReducedMotion` and `AnimatePresence` all live there.
- Vitest needs `globals: true` (set in `vite.config.ts`) for the `test`/`expect` globals.

## Model downloads (ask before each)

| Model | Size | License |
|---|---|---|
| XTTS-v2 (`tts_models/multilingual/multi-dataset/xtts_v2`) | 2.1 GB | Coqui Public Model License (non-commercial) |
| IndicF5 (`ai4bharat/IndicF5`, gated) | 1.4 GB + vocoder | MIT |
| F5-TTS MLX (`lucasnewman/f5-tts-mlx`) | 1.35 GB full / 0.23 GB 4-bit | code MIT; weights unstated (upstream F5 is CC-BY-NC) |

## Backlog

Nice-to-haves from the brief (style variants, Whisper transcription, pronunciation dictionary, pause markers, dialogue, batch, SRT, engine comparison). Candidates to evaluate: Indic-Speak and SPRING_F5. Phase 5: fine-tuning notes only.

## Working rules for Claude

Plan before code. Stop at the end of each phase and summarise. Ask before large downloads and give the size. Verify third-party APIs from installed packages or docs, never from memory. Be honest about audio quality. Keep this file and README.md current in each phase's commit. Kill dev servers when done.
