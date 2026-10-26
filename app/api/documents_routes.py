"""Admins keep the information documents and the booking and queue rules (phase 7D)."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import Auth, get_auth, get_db, run_and_commit
from app.tools import documents
from app.tools.permissions import require_role
from app.tools.policy_settings import policy_view, update_policy

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


class DocumentChange(BaseModel):
    title: str = Field(max_length=200)
    body: str = Field(max_length=documents.MAX_BODY + 1000)
    checked_today: bool = True


class NewDocument(BaseModel):
    title: str = Field(max_length=200)
    body: str = Field(max_length=documents.MAX_BODY + 1000)
    collection: str | None = Field(None, max_length=40)
    language: str = Field(max_length=2)
    translation_of: int | None = None


class PolicyChange(BaseModel):
    values: dict[str, int]


@router.get("/documents")
def list_documents(
    language: str | None = Query(None, max_length=2),
    collection: str | None = Query(None, max_length=40),
    q: str | None = Query(None, max_length=100),
    auth: Auth = Depends(get_auth),
    db: Session = Depends(get_db),
) -> dict:
    return documents.list_documents(db, auth.actor, language, collection, q)


@router.get("/documents/{document_id}")
def get_document(document_id: int, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    return documents.get_document(db, auth.actor, document_id)


@router.put("/documents/{document_id}")
def save_document(
    document_id: int, body: DocumentChange, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)
) -> dict:
    return run_and_commit(
        db,
        lambda: documents.save_document(
            db, auth.actor, document_id, body.title, body.body, checked_today=body.checked_today
        ),
    )


@router.post("/documents", status_code=201)
def add_document(body: NewDocument, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    return run_and_commit(
        db,
        lambda: documents.save_document(
            db, auth.actor, None, body.title, body.body, body.collection, body.language, body.translation_of
        ),
    )


@router.post("/documents/{document_id}/hide")
def hide(document_id: int, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    return run_and_commit(db, lambda: documents.hide_document(db, auth.actor, document_id))


@router.post("/documents/{document_id}/restore")
def restore(document_id: int, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    return run_and_commit(db, lambda: documents.restore_document(db, auth.actor, document_id))


@router.post("/documents/{document_id}/revert")
def revert(document_id: int, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    return run_and_commit(db, lambda: documents.revert_document(db, auth.actor, document_id))


@router.get("/policy")
def get_policy(auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    require_role(auth.actor, "admin")
    return policy_view(db)


@router.put("/policy")
def put_policy(body: PolicyChange, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    return run_and_commit(db, lambda: update_policy(db, auth.actor, body.values))
