from dataclasses import asdict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas.pronunciation import EntryIn, EntryOut, EntryUpdate, PreviewIn, PreviewOut
from app.services import pronunciation as svc

router = APIRouter(prefix="/pronunciations", tags=["pronunciation"])


@router.get("", response_model=list[EntryOut])
def list_entries(session: Session = Depends(get_session)):
    return svc.list_entries(session)


@router.post("", response_model=EntryOut, status_code=201)
def create(body: EntryIn, session: Session = Depends(get_session)):
    return svc.create_entry(
        session, body.term, body.replacement, body.language, body.case_sensitive
    )


@router.patch("/{entry_id}", response_model=EntryOut)
def update(entry_id: str, body: EntryUpdate, session: Session = Depends(get_session)):
    return svc.update_entry(session, entry_id, **body.model_dump(exclude_unset=True))


@router.delete("/{entry_id}", status_code=204)
def delete(entry_id: str, session: Session = Depends(get_session)):
    svc.delete_entry(session, entry_id)


@router.post("/preview", response_model=PreviewOut)
def preview(body: PreviewIn, session: Session = Depends(get_session)):
    """How a text will be spoken with the current dictionary (no audio)."""
    text, applied = svc.apply_for(session, body.text, body.language)
    return PreviewOut(text=text, applied=[asdict(a) for a in applied])
