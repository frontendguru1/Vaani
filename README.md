# Vaani · वाणी

A personal voice-cloning studio that runs **entirely on your Mac**. Give it a few clean clips of someone's voice (with their permission). Then type a script in English, Hindi or a mix of both, and Vaani reads it back in that voice. No cloud services, no accounts, and it works offline once the models are downloaded.

> **Status:** Phase 0 (scaffolding) is done. The app starts, the database is set up, and the hello page shows system health. Voice cloning arrives in the next phases.

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
- About **10 GB** of free disk space once the voice models are installed

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

### Tests

```bash
cd backend  && uv run pytest
cd frontend && pnpm test
```

### Maintenance

```bash
cd backend
uv run vaani check              # is the database schema up to date?
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

## Roadmap

0. ✅ Scaffolding
1. Quality spike: compare the voice engines by ear
2. Backend core: voices, cleanup, quality checks, generation, history
3. Frontend: voice library, recording, generation studio, history
4. Polish and extras
5. Notes on fine-tuning (documentation only)
