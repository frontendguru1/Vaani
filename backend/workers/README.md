# Engine workers

Engines whose dependencies clash with the main backend venv run here, each in its own
venv under the repo-root `.venvs/`, as a long-lived process that keeps its model loaded.

| Worker | venv | Create with |
|---|---|---|
| `f5mlx_worker.py` | `.venvs/f5mlx` (Py 3.11) | `uv venv --python 3.11 .venvs/f5mlx && VIRTUAL_ENV=.venvs/f5mlx uv pip install f5-tts-mlx soundfile` |
| `indicf5_worker.py` | `.venvs/indicf5` (Py 3.10) | `uv venv --python 3.10 .venvs/indicf5 && VIRTUAL_ENV=.venvs/indicf5 uv pip install "git+https://github.com/ai4bharat/IndicF5.git" soundfile torchcodec "transformers<4.50" "numpy<=1.26.4" "datasets<4"` |

Why separate: IndicF5 pins `transformers<4.50` and `numpy<=1.26.4` and installs a module
named `f5_tts`; coqui-tts needs `transformers>=4.57`.

Protocol (`_protocol.py`): one JSON object per line.
`{"cmd":"load","options":{}}` → `{"ok":true,"device":..,"version":..}`;
`{"cmd":"synthesize","text","language","ref_audio","ref_text","out","options"}` → writes
WAV to `out`; `{"cmd":"shutdown"}`. Errors return `{"ok":false,"error":".."}`.
Workers must not import `app` (different venv). stderr goes to `data/logs/<engine>.log`.
