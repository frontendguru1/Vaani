# Vaani · वाणी

A personal voice-cloning studio that runs **entirely on your Mac**. Give it a few clean clips of someone's voice (with their permission). Then type a script in English, Hindi or a mix of both, and Vaani reads it back in that voice. No cloud services, no accounts, and it works offline once the models are downloaded.

> **Status:** the backend works end to end. You can create a voice, generate speech in it with live progress, browse history and delete everything. The web interface for these is being built next (Phase 3); until then the backend can be used through its API at http://127.0.0.1:8000/docs.

![Screenshot placeholder](docs/screenshot.png)

## Features

**Planned for the core app**
- Create a Voice from uploaded clips (wav/mp3/m4a/ogg) or a microphone recording
- Automatic cleanup: mono conversion, silence trimming, loudness normalising, optional denoise
- A quality check with a Good / Okay / Poor rating and the reasons for it
- A voice library: preview, rename, delete (deletion removes every file and record)
- A required consent note per voice
- Generate speech from long scripts, with natural pauses and live progress
- Generation history with replay, regenerate and download (WAV/MP3)
- A dark, animated interface that respects reduced-motion settings

**Later:** speaking-style variants, auto-transcription, a pronunciation dictionary, pause markers, multi-voice dialogue, batch generation, subtitle export, and side-by-side engine comparison.

## Requirements

- macOS on Apple Silicon (built and tested on an M1 Pro, 16 GB)
- [Homebrew](https://brew.sh)
- About **10 GB** of free disk space once the voice models are installed (XTTS-v2 alone is 2.1 GB and downloads automatically the first time a voice is created)

```bash
brew install ffmpeg uv node@22
```

Node 22 is installed alongside any existing Node. Either put it on your PATH for this project or prefix the commands:

```bash
export PATH=/opt/homebrew/opt/node@22/bin:$PATH
```

## Setup and run

```bash
git clone git@github.com:frontendguru1/Vaani.git && cd Vaani
cp .env.example .env            # optional; defaults work

# Backend — terminal 1
cd backend
uv sync
uv run vaani-dev                # http://127.0.0.1:8000  (creates/migrates the database)

# Frontend — terminal 2
cd frontend
pnpm install
pnpm dev                        # open http://localhost:5173
```

### Optional extra voice engines

XTTS-v2 is built in. Two more engines can be added for comparison. Each lives in its own Python environment, because their libraries clash with XTTS's:

```bash
# F5-TTS MLX — fast-ish English on Apple Silicon (~1.4 GB model on first use)
uv venv --python 3.11 .venvs/f5mlx && VIRTUAL_ENV=.venvs/f5mlx uv pip install f5-tts-mlx soundfile

# IndicF5 — Hindi specialist (~1.4 GB). Gated: accept the terms at
# https://huggingface.co/ai4bharat/IndicF5, create a Read token, then:
backend/.venv/bin/hf auth login
uv venv --python 3.10 .venvs/indicf5 && VIRTUAL_ENV=.venvs/indicf5 uv pip install "git+https://github.com/ai4bharat/IndicF5.git" soundfile
```

Both of these need a short reference clip (≤ 12–15 s) **and the exact words spoken in it**.

### Comparing engines (benchmark)

```bash
cd backend
uv run python scripts/benchmark_engines.py --ref ~/clips/me.wav --ref-text "the exact words in the clip"
```

It speaks a few English, Hindi and Hinglish sentences with every installed engine. It saves the audio to `data/benchmarks/<date-time>/` so you can listen, and prints how long each engine took.

| Measured on the M1 Pro (synthetic reference voice) | Speed |
|---|---|
| XTTS-v2 on the Apple GPU (default) | about 2× faster than real time |
| XTTS-v2 on CPU | about 1.5× slower than real time |
| F5-TTS MLX | 2.5–5× slower than real time |

### Tests

```bash
cd backend  && uv run pytest
cd frontend && pnpm test
```

### Maintenance

```bash
cd backend
uv run vaani check              # schema up to date? any orphaned files or missing files?
uv run vaani check --fix-orphans  # delete folders that no longer belong to any voice
uv run vaani migrate            # apply database migrations
uv run vaani reset-dev-data     # wipe all voices, generations and the database (keeps models)
```

## Configuration

All settings go in `.env` at the repo root. See `.env.example` for the full list.

| Setting | Default | Meaning |
|---|---|---|
| `VAANI_DATA_DIR` | `data` | Where voices, generations, the database and models are stored |
| `DATABASE_URL` | SQLite in the data dir | Point this at Postgres later if wanted |
| `VAANI_DEVICE` | `auto` | `auto` tries the Apple GPU (MPS) and falls back to CPU |
| `VAANI_DEFAULT_ENGINE` | `xtts` | Voice engine used when none is chosen |
| `VAANI_PAUSE_SENTENCE_MS` / `_PARAGRAPH_MS` | 350 / 800 | Pauses between generated sentences and paragraphs |
| `VAANI_FEATURES` | empty | Comma-separated experimental features |

## Project structure

```
backend/    Python API (FastAPI), database models and migrations, voice engines
frontend/   Web interface (React, TypeScript, Tailwind, Motion)
data/       Your private data — voices, audio, database, models (never committed)
```

## API

Everything is under `/api/v1`. Interactive docs are at http://127.0.0.1:8000/docs.

| Call | What it does |
|---|---|
| `POST /voices` | Upload clips (multipart: `name`, `language`, `consent_note`, `files[]`). Returns the voice and a job id |
| `POST /voices/quality-check` | Rate a single clip without saving it |
| `GET /voices`, `GET/PATCH/DELETE /voices/{id}` | Voice library. DELETE removes every file and record |
| `GET /voices/{id}/preview` | Play the reference clip |
| `POST /generations` | `{voice_id, language, script, engine?, settings?}`. Returns a job id |
| `GET /generations`, `GET /generations/{id}` | History |
| `GET /generations/{id}/audio?format=wav\|mp3&download=true` | The result |
| `POST /generations/{id}/regenerate`, `DELETE /generations/{id}` | |
| `GET /jobs/{id}`, `GET /jobs/{id}/events` | Job status, and live progress as Server-Sent Events |
| `GET /engines`, `GET /health` | Installed engines, and system status |

## Voice models and licenses

| Engine | Good for | Download | License |
|---|---|---|---|
| [XTTS-v2](https://huggingface.co/coqui/XTTS-v2) via [coqui-tts](https://github.com/idiap/coqui-ai-TTS) | English + Hindi, baseline | 2.1 GB | Code MPL-2.0; weights **Coqui Public Model License (non-commercial)** |
| [IndicF5](https://huggingface.co/ai4bharat/IndicF5) (AI4Bharat) | Hindi quality | 1.4 GB | MIT; access requires accepting the terms on Hugging Face |
| [F5-TTS MLX](https://github.com/lucasnewman/f5-tts-mlx) | Fast English on Apple Silicon | 0.2–1.4 GB | Code MIT; weights license not stated (upstream F5-TTS weights are CC-BY-NC) |

Which engines Vaani ships with depends on a listening test in Phase 1. **Vaani is for personal and family use only.** Do not use it commercially.

## Privacy and consent

- Everything stays on this computer. Vaani makes no network calls except the one-time model downloads.
- All recordings, voices and generated audio live in `data/`, which is excluded from git.
- Only clone a voice when that person has agreed, or when it's your own. Vaani asks for a consent note for each voice and refuses to generate without one.
- Deleting a voice permanently removes its recordings, cached voice data, generated audio and database records.

## Troubleshooting

- **The page says "Can't reach the backend":** start it with `cd backend && uv run vaani-dev`.
- **`pnpm dev` fails with a Node version error:** you're on an older Node. Use the Node 22 PATH line above.
- **System card shows ffmpeg missing:** run `brew install ffmpeg`.
- **The first voice takes a minute:** XTTS-v2 is loading, or downloading on the very first run. Later voices and generations reuse the loaded model.
- **XTTS sounds wrong on the GPU:** force CPU with `VAANI_XTTS_DEVICE=cpu` in `.env` and compare.
- **IndicF5 shows "gated model":** accept its terms on Hugging Face, then run `backend/.venv/bin/hf auth login`.

## Roadmap

0. ✅ Scaffolding
1. 🎧 Quality spike: the benchmark is built; the listening test on a real voice is still to do
2. ✅ Backend core: voices, cleanup, quality checks, generation, history
3. Frontend: voice library, recording, generation studio, history
4. Polish and extras
5. Notes on fine-tuning (documentation only)
