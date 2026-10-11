# CLAUDE.md — Vaani (वाणी)

Vaani is a personal, **fully local** voice-cloning app: upload/record clips of a person → clean + quality-check → save a named Voice → type an English/Hindi (or Hinglish) script → get audio in that voice. Runs only on Rahul's MacBook Pro (M1 Pro, 16 GB, macOS 26). **No cloud APIs, no telemetry, works offline after models are downloaded.** Audio of real people (including a child) lives in `data/`, which is gitignored. Every Voice needs a **consent note**; generation is blocked without one. Personal/family use only — several model weights are non-commercial. The full original brief is `vaani-claude-code-prompt.md` (local only, gitignored — not in the repo).

## Current status

- **Phase 0 — Scaffolding: DONE (2026-10-11).** Backend hello-world with `/api/v1/health`, SQLite + Alembic initial migration, maintenance CLI, frontend hello page with design + motion tokens.
- **Next: Phase 1 — quality spike.** Install torch, write `backend/scripts/benchmark_engines.py`, run XTTS-v2 / IndicF5 / F5-MLX, **stop for Rahul's listening decision.** Ask before every large download (sizes are below).
- Known issues: none yet. The `Compute` row on the hello page shows "torch not installed yet" until Phase 1.

## Stack (versions actually installed)

| Layer | Choice |
|---|---|
| Backend | Python 3.11.5 (Homebrew), uv 0.13, FastAPI 0.143, Uvicorn 0.54, SQLAlchemy 2, Alembic, pydantic-settings, python-ulid |
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

# Benchmark (Phase 1, not yet written)
cd backend && uv run python scripts/benchmark_engines.py
```

## Directory map

```
backend/app/
  main.py          FastAPI app; sets PYTORCH_ENABLE_MPS_FALLBACK before any torch import
  config.py        Settings (env prefix VAANI_, reads repo-root .env); data_dir resolves from repo root
  db.py            make_engine() (SQLite pragmas), SessionLocal, get_session dependency
  cli.py / dev.py  `vaani` maintenance CLI / `vaani-dev` server launcher
  api/v1/          one router per feature; registered ONLY in api/v1/__init__.py
  services/        business logic, no HTTP (system.py = ffmpeg/device probes)
  models/          ORM; base.py has Base (naming convention), IdMixin (ULID), TimestampMixin
  schemas/         pydantic request/response models
  engines/         (Phase 1/2) base.py, registry.py, one module per TTS engine
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
- **Planned engine layer (Phase 2):** `TTSEngine` ABC (`name`, `supported_languages`, `load`, `create_voice`, `synthesize`, `unload`) + registry. **IndicF5 can't share a venv with coqui-tts** (see Gotchas), so non-main-venv engines will run as subprocess workers behind the same interface.
- **Planned jobs:** in-process queue, one generation on the model at a time, SSE progress at `/jobs/{id}/events`.
- **Frontend motion:** `<MotionConfig reducedMotion="user">` wraps the app, so transforms are dropped under prefers-reduced-motion and opacity fades remain. Use `fadeOnly()` for hand-rolled motion. Progress visuals must be driven by backend events, never faked.

## Decision log

- **2026-10-11** uv instead of pip/venv: coqui-tts now recommends it, and it is fast. Python pinned to 3.11 (`backend/.python-version`).
- **2026-10-11** Node 22 installed keg-only beside the global Node 18 (Vite 8 needs ≥20.19). `.nvmrc` = 22.
- **2026-10-11** ULIDs for ids (sortable, URL-safe), stored as `String(26)`.
- **2026-10-11** Fonts self-hosted via @fontsource for the offline requirement.
- **2026-10-11** Radix and WaveSurfer deferred to Phase 3 (added when a component needs them; no speculative deps).
- **2026-10-11** Git identity for this repo set locally to Rahul / rahul.dsg@gmail.com (the global identity is a work email).

## Conventions

- **Commits:** `type(scope): summary` + `Problem:` / `Solution:` body. Types: feat, fix, refactor, docs, test, chore. Scopes: backend, frontend, db, engines, docs. One commit per phase minimum; update this file in the same commit.
- **Python:** ruff (line 100, rules E,F,I,B,UP; B008 ignored for FastAPI `Depends`). Type hints everywhere.
- **Add a migration:** change the model → `uv run vaani make-migration "msg"` → read and fix the generated file → `uv run pytest` (`test_models_match_migrations` fails if a model drifted from migrations).
- **Add an API route:** `app/api/v1/<feature>.py` with `router = APIRouter(...)` → append the module to the tuple in `api/v1/__init__.py` → logic goes in `services/`.
- **Add an engine (Phase 2):** subclass `TTSEngine` in `engines/<name>.py`, register it in the registry; nothing else changes.
- **Add a frontend feature:** `src/features/<name>/{api.ts, Component.tsx, Component.test.tsx}`.
- **Add an animation:** import from `src/motion/tokens.ts` (`variants`, `transition`, `spring`, `press`). Never inline durations or easings. Animate transform/opacity only.
- **Colours etc.:** only through tokens (`var(--…)` or the Tailwind names mapped in `index.css`).

## Gotchas

- **Node 18 is still the global default.** Use `/opt/homebrew/opt/node@22/bin` or `pnpm` fails on Vite 8.
- **XTTS-v2 on MPS** reportedly hangs (coqui issue #3649). Expect CPU, and test in Phase 1.
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
