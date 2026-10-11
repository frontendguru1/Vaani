# CLAUDE.md — Vaani (वाणी)

Vaani is a personal, **fully local** voice-cloning app: upload/record clips of a person → clean + quality-check → save a named Voice → type an English/Hindi (or Hinglish) script → get audio in that voice. Runs only on Rahul's MacBook Pro (M1 Pro, 16 GB, macOS 26). **No cloud APIs, no telemetry, works offline after models are downloaded.** Audio of real people (including a child) lives in `data/`, which is gitignored. Every Voice needs a **consent note**; generation is blocked without one. Personal/family use only — several model weights are non-commercial. The full original brief is `vaani-claude-code-prompt.md` (local only, gitignored — not in the repo).

## Current status

- **Phase 0 — Scaffolding: DONE (2026-10-11).**
- **Phase 1 — Quality spike: BUILT, listening decision PENDING.** `backend/scripts/benchmark_engines.py` works for all three engines. Only a *synthetic* reference (macOS "Rishi" voice) has been benchmarked so far — it proves the pipeline, not cloning quality. Rahul still needs to (a) supply a real 15–60 s clip + transcript and listen, (b) finish the IndicF5 Hugging Face token login. XTTS-v2 is the working default until then.
- **Phase 2 — Backend core: DONE (2026-10-11).** Voices (upload → clean → quality → voiceprint as a job), library CRUD + hard delete, engine registry + 3 engines, generation with chunking + SSE progress + stitching + MP3, history/regenerate/delete, consistency check. 69 tests.
- **Next: Phase 3 — Frontend** (Voices, Generate, History pages with all section-5 animations).
- Known issues: F5-MLX outputs look short (4.5 s where XTTS says 7 s) — possibly clipped by its duration predictor; needs listening. IndicF5 untested (gated).

## Stack (versions actually installed)

| Layer | Choice |
|---|---|
| Backend | Python 3.11.5 (Homebrew), uv 0.13, FastAPI 0.143, Uvicorn 0.54, SQLAlchemy 2, Alembic, pydantic-settings, python-ulid |
| ML (main venv) | torch 2.14.1 (MPS ok), torchaudio 2.11, coqui-tts 0.27.5, transformers 4.57.6 (pinned <5), librosa |
| Engine venvs | `.venvs/f5mlx` (Py 3.11, f5-tts-mlx 0.2.6, mlx 0.32.3), `.venvs/indicf5` (Py 3.10, IndicF5 from git) — see `backend/workers/README.md` |
| DB | SQLite `data/vaani.db`, WAL + foreign keys on; `DATABASE_URL` overrides it |
| Frontend | Node 22.23 (Homebrew `node@22`, keg-only), pnpm 10, Vite 8, React 19, TypeScript 7, Tailwind 4 (`@tailwindcss/vite`), `motion` 14, Vitest 5 |
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
  components/        shared UI (Aurora, Logo)
  features/<name>/   feature modules (api.ts + components + tests)
  lib/api.ts         fetch wrapper for /api/v1
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
- **Delete:** `delete_voice` removes rows (FK cascade: samples, profiles, generations, chunks; jobs by id) and folders, and returns `leftover_paths` (must be empty). `vaani check` finds orphans both ways.
- **Frontend motion:** `<MotionConfig reducedMotion="user">` wraps the app, so transforms are dropped under prefers-reduced-motion and opacity fades remain. Use `fadeOnly()` for hand-rolled motion. Progress visuals must be driven by backend events, never faked.

## Decision log

- **2026-10-11** uv instead of pip/venv: coqui-tts now recommends it, and it is fast. Python pinned to 3.11 (`backend/.python-version`).
- **2026-10-11** Node 22 installed keg-only beside the global Node 18 (Vite 8 needs ≥20.19). `.nvmrc` = 22.
- **2026-10-11** ULIDs for ids (sortable, URL-safe), stored as `String(26)`.
- **2026-10-11** Fonts self-hosted via @fontsource for the offline requirement.
- **2026-10-11** Radix and WaveSurfer deferred to Phase 3 (added when a component needs them; no speculative deps).
- **2026-10-11** Git identity for this repo set locally to Rahul / rahul.dsg@gmail.com (the global identity is a work email).
- **2026-10-11** Project brief removed from the public repo at Rahul's request (rewrote the single commit, force-pushed). It stays local + gitignored.
- **2026-10-11** One venv per conflicting engine + worker processes, rather than one venv with pinned compromises (IndicF5 needs transformers<4.50, coqui needs >=4.57).
- **2026-10-11** **XTTS defaults to MPS.** Benchmark (synthetic ref): CPU RTF ≈ 1.45, MPS RTF ≈ 0.5 warm (first sentence ~1.4 = warm-up). No hang with coqui-tts 0.27.5 + torch 2.14; MPS output matched CPU on pitch (≈115 Hz = reference) and spectral flatness. `VAANI_XTTS_DEVICE=cpu` forces CPU.
- **2026-10-11** F5-MLX: works after a compat shim (see Gotchas) but RTF 2.5–5.5 on M1 Pro (slower than XTTS on MPS) and outputs look short. Not chosen as default.
- **2026-10-11** Quality checker is pure numpy + librosa.yin (no ML VAD): energy VAD with 3rd-percentile noise floor; SNR reported as `null` when there are no pauses to measure against; pitch-spread IQR > 6.5 semitones → "maybe multiple speakers" (heuristic, says so).
- **2026-10-11** Preprocessing uses only ffmpeg filters (highpass, optional `afftdn` denoise, silenceremove ×2 with areverse, `loudnorm` −20 LUFS) — no DeepFilterNet/Demucs download needed.
- **2026-10-11** **Engine choice still awaiting Rahul's listening test on a real clip.**

## Conventions

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
- **HF token location**: `hf auth login` writes `~/.cache/huggingface/token`; workers get `HF_HOME=data/models/hf` for weights, so we pass `HF_TOKEN_PATH` explicitly.
- **Uploads**: allowed extensions in `voices.ALLOWED_EXTENSIONS` (incl. aiff/aif — macOS's native format). FastAPI `Form(...)` rejects empty strings before our validators, so required text fields use `Form("")` and the service validates (gives a proper `code`).
- **Test sessions go stale** after `runner.run_one()` (the job used other sessions) → `session.expire_all()`.
- **IndicF5** pins `transformers<4.50`, `numpy<=1.26.4` and installs a module named `f5_tts`; coqui-tts 0.27.5 needs `transformers>=4.57`. **Separate venv** (`.venvs/indicf5`, Python 3.10). The model is gated on Hugging Face: Rahul must accept the terms and log in.
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
