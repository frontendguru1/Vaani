from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Voice
from app.schemas.generations import (
    ChunkOut,
    GenerationCreate,
    GenerationCreated,
    GenerationDetail,
    GenerationOut,
)
from app.services import generation as svc

router = APIRouter(prefix="/generations", tags=["generations"])


def _names(session: Session) -> dict[str, str]:
    return dict(session.execute(select(Voice.id, Voice.name)).all())


def _out(gen, names: dict[str, str]) -> GenerationOut:
    return GenerationOut.model_validate(gen).model_copy(
        update={"voice_name": names.get(gen.voice_id)}
    )


def _detail(session: Session, gen) -> GenerationDetail:
    base = _out(gen, _names(session))
    return GenerationDetail(
        **base.model_dump(), chunks=[ChunkOut.model_validate(c) for c in gen.chunks]
    )


@router.post("", response_model=GenerationCreated, status_code=202)
def create(body: GenerationCreate, session: Session = Depends(get_session)):
    gen, job = svc.create_generation(
        session,
        voice_id=body.voice_id,
        script=body.script,
        language=body.language,
        engine=body.engine,
        settings=body.settings.model_dump(exclude_none=True),
    )
    return GenerationCreated(
        generation=_detail(session, svc.get_generation(session, gen.id)), job_id=job.id
    )


@router.get("", response_model=list[GenerationOut])
def history(
    voice_id: str | None = None,
    limit: int = Query(100, le=500),
    session: Session = Depends(get_session),
):
    names = _names(session)
    return [_out(g, names) for g in svc.list_generations(session, voice_id, limit)]


@router.get("/{generation_id}", response_model=GenerationDetail)
def get(generation_id: str, session: Session = Depends(get_session)):
    return _detail(session, svc.get_generation(session, generation_id))


@router.get("/{generation_id}/audio")
def audio(
    generation_id: str,
    format: str = Query("wav", pattern="^(wav|mp3)$"),
    download: bool = False,
    session: Session = Depends(get_session),
):
    path = svc.audio_file(session, generation_id, format)
    media = "audio/mpeg" if format == "mp3" else "audio/wav"
    filename = f"vaani-{generation_id[-8:].lower()}.{format}" if download else None
    return FileResponse(path, media_type=media, filename=filename)


@router.post("/{generation_id}/regenerate", response_model=GenerationCreated, status_code=202)
def regenerate(generation_id: str, session: Session = Depends(get_session)):
    gen, job = svc.regenerate(session, generation_id)
    return GenerationCreated(
        generation=_detail(session, svc.get_generation(session, gen.id)), job_id=job.id
    )


@router.delete("/{generation_id}")
def delete(generation_id: str, session: Session = Depends(get_session)):
    return {
        "generation_id": generation_id,
        "files_removed": svc.delete_generation(session, generation_id),
    }
