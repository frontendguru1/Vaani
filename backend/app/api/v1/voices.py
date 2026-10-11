import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import VoiceEngineProfile
from app.schemas.voices import (
    DeleteResult,
    QualityCheck,
    SampleOut,
    VoiceCreated,
    VoiceDetail,
    VoiceOut,
    VoiceUpdate,
)
from app.services import audio, storage, voices
from app.services.errors import Invalid, NotFound
from app.services.quality import analyze

router = APIRouter(prefix="/voices", tags=["voices"])


def _out(voice, counts: dict[str, int] | None = None) -> VoiceOut:
    return VoiceOut.model_validate(voice).model_copy(
        update={
            "has_preview": bool(voice.preview_path),
            "generation_count": (counts or {}).get(voice.id, 0),
        }
    )


def _detail(session: Session, voice) -> VoiceDetail:
    base = _out(voice, voices.generation_counts(session))
    samples = [
        SampleOut.model_validate(s).model_copy(update={"has_audio": bool(s.processed_path)})
        for s in voice.samples
    ]
    engines = list(
        session.scalars(
            select(VoiceEngineProfile.engine).where(VoiceEngineProfile.voice_id == voice.id)
        )
    )
    return VoiceDetail(**base.model_dump(), samples=samples, engines_ready=engines)


@router.get("", response_model=list[VoiceOut])
def list_voices(session: Session = Depends(get_session)):
    counts = voices.generation_counts(session)
    return [_out(v, counts) for v in voices.list_voices(session)]


@router.post("", response_model=VoiceCreated, status_code=202)
def create_voice(
    name: str = Form(""),
    language: str = Form("en"),
    consent_note: str = Form(""),
    description: str = Form(""),
    denoise: bool = Form(False),
    files: list[UploadFile] = File(...),
    kinds: list[str] = Form(default=[]),
    transcripts: list[str] = Form(default=[]),
    session: Session = Depends(get_session),
):
    uploads = [
        voices.Upload(
            filename=f.filename or f"recording-{i}.webm",
            file=f.file,
            kind=kinds[i] if i < len(kinds) and kinds[i] in ("upload", "recording") else "upload",
            transcript=transcripts[i] if i < len(transcripts) else None,
        )
        for i, f in enumerate(files)
    ]
    voice, job = voices.create_voice(
        session,
        name=name,
        language=language,
        consent_note=consent_note,
        description=description,
        uploads=uploads,
        denoise=denoise,
    )
    return VoiceCreated(voice=_out(voice), job_id=job.id)


@router.post("/quality-check", response_model=QualityCheck)
def quality_check(file: UploadFile = File(...)):
    """Analyse one clip without storing anything (for live feedback while picking files)."""
    ext = Path(file.filename or "").suffix.lower().lstrip(".")
    if ext not in voices.ALLOWED_EXTENSIONS:
        raise Invalid(f"Unsupported file type .{ext or '?'}", code="file_type")
    with tempfile.TemporaryDirectory(dir=storage.data_dir()) as tmp:
        src = Path(tmp) / f"in.{ext}"
        src.write_bytes(file.file.read())
        wav = audio.convert_to_wav(src, Path(tmp) / "a.wav", 24_000)
        data, sr = audio.read_mono(wav)
        report = analyze(data, sr)
    return QualityCheck(
        filename=file.filename or "", duration=report.duration, report=report.to_dict()
    )


@router.get("/{voice_id}", response_model=VoiceDetail)
def get_voice(voice_id: str, session: Session = Depends(get_session)):
    return _detail(session, voices.get_voice(session, voice_id))


@router.patch("/{voice_id}", response_model=VoiceDetail)
def update_voice(voice_id: str, body: VoiceUpdate, session: Session = Depends(get_session)):
    voice = voices.update_voice(session, voice_id, **body.model_dump(exclude_unset=True))
    return _detail(session, voice)


@router.delete("/{voice_id}", response_model=DeleteResult)
def delete_voice(voice_id: str, session: Session = Depends(get_session)):
    report = voices.delete_voice(session, voice_id)
    return DeleteResult(**report.__dict__)


@router.get("/{voice_id}/preview")
def preview(voice_id: str, session: Session = Depends(get_session)):
    voice = voices.get_voice(session, voice_id)
    if not voice.preview_path:
        raise NotFound("No preview yet", code="no_preview")
    return FileResponse(storage.resolve(voice.preview_path), media_type="audio/wav")


@router.get("/{voice_id}/samples/{sample_id}/audio")
def sample_audio(voice_id: str, sample_id: str, session: Session = Depends(get_session)):
    voice = voices.get_voice(session, voice_id)
    sample = next((s for s in voice.samples if s.id == sample_id), None)
    if sample is None or not sample.processed_path:
        raise NotFound("Sample audio not found", code="sample_not_found")
    return FileResponse(storage.resolve(sample.processed_path), media_type="audio/wav")
