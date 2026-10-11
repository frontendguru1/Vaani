"""Engines whose dependencies conflict with the main venv run as long-lived worker
processes in their own venv (repo-root .venvs/<name>). Protocol: one JSON object per line
on stdin/stdout. Audio is exchanged as WAV files. See backend/workers/README.md."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Any, ClassVar

from app.config import REPO_ROOT, get_settings
from app.engines.base import Availability, EngineError, SynthesisResult, TTSEngine, VoiceProfile
from app.services import audio

log = logging.getLogger("vaani.engines.worker")

WORKERS_DIR = REPO_ROOT / "backend" / "workers"
REF_FILE = "ref.wav"


def hf_token_path() -> Path | None:
    """`huggingface-cli login` writes here by default (we redirect HF_HOME for models)."""
    for p in (Path.home() / ".cache" / "huggingface" / "token",):
        if p.is_file():
            return p
    return None


class SubprocessEngine(TTSEngine):
    venv: ClassVar[str]
    worker_script: ClassVar[str]
    max_ref_seconds: ClassVar[float] = 12.0
    needs_transcript = True

    def __init__(self) -> None:
        super().__init__()
        self._proc: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()
        self._version = "unknown"

    # -- process plumbing -------------------------------------------------
    @property
    def python(self) -> Path:
        return REPO_ROOT / ".venvs" / self.venv / "bin" / "python"

    @property
    def worker_path(self) -> Path:
        return WORKERS_DIR / self.worker_script

    @property
    def log_path(self) -> Path:
        return get_settings().data_dir / "logs" / f"{self.name}.log"

    def availability(self) -> Availability:
        if not self.python.is_file():
            return Availability(False, f"venv missing: .venvs/{self.venv} (see README)")
        return Availability(True)

    @property
    def version(self) -> str:
        return self._version

    @property
    def is_loaded(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def worker_env(self) -> dict[str, str]:
        settings = get_settings()
        env = {
            **os.environ,
            "HF_HOME": str(settings.models_dir / "hf"),
            "HF_HUB_DISABLE_TELEMETRY": "1",
            "PYTORCH_ENABLE_MPS_FALLBACK": "1",
            "PYTHONUNBUFFERED": "1",
            "PYTHONPATH": str(WORKERS_DIR),  # so any worker script can import _protocol
            "VAANI_DEVICE": settings.device,
        }
        token = hf_token_path()
        if token:
            env["HF_TOKEN_PATH"] = str(token)
        return env

    def _call(self, req: dict[str, Any]) -> dict[str, Any]:
        assert self._proc and self._proc.stdin and self._proc.stdout
        self._proc.stdin.write(json.dumps(req) + "\n")
        self._proc.stdin.flush()
        while True:
            line = self._proc.stdout.readline()
            if not line:
                raise EngineError(
                    f"{self.label} worker exited. Last log lines:\n{self._log_tail()}"
                )
            try:
                resp = json.loads(line)
            except json.JSONDecodeError:
                resp = None
            if isinstance(resp, dict) and "ok" in resp:
                break
            # Stray output printed before the worker redirected stdout (e.g. on import).
            log.debug("%s worker stdout: %s", self.name, line.rstrip())
        if not resp.get("ok"):
            raise EngineError(f"{self.label}: {resp.get('error', 'unknown error')}")
        return resp

    def _log_tail(self, n: int = 15) -> str:
        try:
            return "\n".join(self.log_path.read_text(errors="replace").splitlines()[-n:])
        except OSError:
            return "(no log)"

    def load(self) -> None:
        with self._lock:
            if self.is_loaded:
                return
            avail = self.availability()
            if not avail.ok:
                raise EngineError(f"{self.label} unavailable: {avail.reason}")
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            logf = self.log_path.open("a")
            self._proc = subprocess.Popen(
                [str(self.python), str(self.worker_path)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=logf,
                text=True,
                env=self.worker_env(),
                cwd=str(WORKERS_DIR),
            )
            try:
                resp = self._call({"cmd": "load", "options": self.load_options()})
            except Exception:
                self._kill()
                raise
            self.device = resp.get("device", "unknown")
            self._version = resp.get("version", "unknown")
            log.info("%s worker loaded on %s", self.label, str(self.device).upper())

    def load_options(self) -> dict[str, Any]:
        return {}

    def _kill(self) -> None:
        if self._proc:
            self._proc.kill()
            self._proc.wait(timeout=5)
        self._proc = None

    def unload(self) -> None:
        with self._lock:
            if self.is_loaded:
                try:
                    self._call({"cmd": "shutdown"})
                    self._proc.wait(timeout=10)  # type: ignore[union-attr]
                except Exception:  # noqa: BLE001
                    pass
            self._kill()
            self.device = None

    # -- engine API ---------------------------------------------------------
    def create_voice(
        self,
        reference_files: list[Path],
        cache_dir: Path,
        transcripts: list[str] | None = None,
    ) -> VoiceProfile:
        if not reference_files:
            raise EngineError(f"{self.label} needs a reference clip")
        if not transcripts or not transcripts[0].strip():
            raise EngineError(f"{self.label} needs the exact transcript of the reference clip")
        src = reference_files[0]
        dur = audio.duration_seconds(src)
        if dur > self.max_ref_seconds + 0.5:
            raise EngineError(
                f"{self.label} works best with a reference of at most {self.max_ref_seconds:.0f}s "
                f"(got {dur:.1f}s). Use a shorter clip whose transcript matches exactly."
            )
        cache_dir.mkdir(parents=True, exist_ok=True)
        audio.convert_to_wav(src, cache_dir / REF_FILE, self.sample_rate)
        return VoiceProfile(
            self.name,
            self.version,
            cache_dir,
            {"ref_audio": REF_FILE, "ref_text": transcripts[0].strip()},
        )

    def synthesize(
        self, text: str, profile: VoiceProfile, language: str, **options: Any
    ) -> SynthesisResult:
        if language not in self.supported_languages:
            raise EngineError(f"{self.label} does not support language '{language}'")
        self.load()
        with tempfile.TemporaryDirectory(dir=get_settings().data_dir) as tmp:
            out = Path(tmp) / "out.wav"
            with self._lock:
                self._call(
                    {
                        "cmd": "synthesize",
                        "text": text,
                        "language": language,
                        "ref_audio": str(profile.path("ref_audio")),
                        "ref_text": profile.data["ref_text"],
                        "out": str(out),
                        "options": {
                            k: v for k, v in options.items() if k in ("speed", "steps", "seed")
                        },
                    }
                )
            wav, sr = audio.read_mono(out)
        return SynthesisResult(wav, sr, self.device or "unknown")
