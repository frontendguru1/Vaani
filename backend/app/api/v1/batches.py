from fastapi import APIRouter, BackgroundTasks, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Voice
from app.schemas.batches import BatchCreate, BatchOut
from app.schemas.generations import GenerationOut
from app.services import batches as svc

router = APIRouter(prefix="/batches", tags=["batches"])


def _out(session: Session, b) -> BatchOut:  # noqa: ANN001
    names = dict(session.execute(select(Voice.id, Voice.name)).all())
    s = svc.summary(session, b)
    items = [
        GenerationOut.model_validate(g).model_copy(update={"voice_name": names.get(g.voice_id)})
        for g in b.generations
    ]
    return BatchOut(
        id=b.id,
        title=b.title,
        voice_id=b.voice_id,
        voice_name=names.get(b.voice_id),
        language=b.language,
        engine=b.engine,
        created_at=b.created_at,
        progress=s["progress"],
        finished=s["finished"],
        counts=s["counts"],
        items=items,
        done_chunks=s["done_chunks"],
    )


@router.post("", response_model=BatchOut, status_code=202)
def create(body: BatchCreate, session: Session = Depends(get_session)):
    b = svc.create_batch(
        session,
        voice_id=body.voice_id,
        language=body.language,
        title=body.title,
        engine=body.engine,
        settings=body.settings.model_dump(exclude_none=True),
        items=[i.model_dump() for i in body.items],
    )
    return _out(session, svc.get_batch(session, b.id))


@router.get("", response_model=list[BatchOut])
def list_all(session: Session = Depends(get_session)):
    return [_out(session, b) for b in svc.list_batches(session)]


@router.get("/{batch_id}", response_model=BatchOut)
def get(batch_id: str, session: Session = Depends(get_session)):
    return _out(session, svc.get_batch(session, batch_id))


@router.post("/{batch_id}/cancel")
def cancel(batch_id: str, session: Session = Depends(get_session)):
    return {"cancelled": svc.cancel_batch(session, batch_id)}


@router.delete("/{batch_id}")
def delete(batch_id: str, session: Session = Depends(get_session)):
    return {"files_removed": svc.delete_batch(session, batch_id)}


@router.get("/{batch_id}/download")
def download(
    batch_id: str,
    background: BackgroundTasks,
    format: str = Query("wav", pattern="^(wav|mp3)$"),
    subtitles: str = Query("srt", pattern="^(srt|vtt|none)$"),
    session: Session = Depends(get_session),
):
    path, name = svc.build_zip(
        session, batch_id, format, None if subtitles == "none" else subtitles
    )
    background.add_task(path.unlink, missing_ok=True)  # the ZIP is temporary
    return FileResponse(path, media_type="application/zip", filename=name)
