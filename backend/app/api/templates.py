import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_session
from app.errors import AppError
from app.models import OutreachTemplate
from app.schemas import TemplateIn, TemplateOut, TemplatePatch

router = APIRouter(prefix="/api/templates")


def _get(session: Session, template_id: uuid.UUID) -> OutreachTemplate:
    t = session.get(OutreachTemplate, template_id)
    if t is None:
        raise AppError(404, "not_found", f"Template {template_id} not found")
    return t


def _save(session: Session, t: OutreachTemplate) -> OutreachTemplate:
    try:
        session.commit()
    except IntegrityError:  # unique name
        session.rollback()
        raise AppError(409, "duplicate_name", "A template with this name already exists")
    session.refresh(t)
    return t


@router.get("", response_model=list[TemplateOut])
def list_templates(session: Session = Depends(get_session)):
    return session.scalars(select(OutreachTemplate).order_by(OutreachTemplate.kind, OutreachTemplate.name)).all()


@router.post("", response_model=TemplateOut, status_code=201)
def create_template(body: TemplateIn, session: Session = Depends(get_session)):
    t = OutreachTemplate(**body.model_dump())
    session.add(t)
    return _save(session, t)


@router.patch("/{template_id}", response_model=TemplateOut)
def update_template(template_id: uuid.UUID, body: TemplatePatch, session: Session = Depends(get_session)):
    t = _get(session, template_id)
    changes = body.model_dump(exclude_unset=True)
    for field in ("name", "kind", "body"):
        if field in changes and changes[field] is None:
            raise AppError(422, "validation_error", f"{field} cannot be null")
    if changes.get("kind", t.kind) != "email":
        if changes.get("subject") is not None:
            raise AppError(422, "validation_error", "subject is only allowed for email templates")
        changes["subject"] = None
    for field, value in changes.items():
        setattr(t, field, value)
    return _save(session, t)


@router.delete("/{template_id}", status_code=204)
def delete_template(template_id: uuid.UUID, session: Session = Depends(get_session)):
    session.delete(_get(session, template_id))
    session.commit()
    return Response(status_code=204)
