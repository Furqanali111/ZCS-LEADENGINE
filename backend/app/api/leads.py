import uuid
from datetime import datetime, timezone
from typing import Annotated, Literal
from urllib.parse import unquote

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session, joinedload, selectinload

from app.constants import CLOSED_STATUSES
from app.db import get_session
from app.errors import AppError
from app.models import Contact, LeadActivity, Organization, SourceRecord
from app.schemas import ActivityIn, ActivityOut, ActivityPage, LeadFilters, LeadOut, LeadPage, LeadPatch
from app.services.activities import add_activity, change_status
from app.services.leads import lead_query, primary_email, rescore_org, sorted_contacts
from app.services.suppression import suppressed_ids

router = APIRouter(prefix="/api/leads")
owners_router = APIRouter(prefix="/api/owners")
OPEN_STATUSES = ("new", "researching")  # claiming moves only these to in_progress


def salesperson(x_salesperson: Annotated[str | None, Header()] = None) -> str | None:
    """The name the browser sends (percent-encoded). No accounts: this says who did it, it does not prove it."""
    name = "".join(c for c in unquote(x_salesperson or "") if c.isprintable()).strip()[:40]  # no NUL or newlines
    return None if name.lower() == "none" else name or None  # "none" means unclaimed in the owner filter


def claim(session: Session, org: Organization, name: str | None) -> None:
    """Atomic: the UPDATE only matches an unclaimed lead or one already ours, so two people cannot both win."""
    if not name:
        raise AppError(400, "name_required", "Enter your name at the top of the page first")
    if suppressed_ids(session, [org.id]):
        raise AppError(409, "lead_suppressed", "This lead is on the suppression list")
    if org.crm_status in CLOSED_STATUSES:
        raise AppError(409, "lead_closed", "This lead is closed. Change its status first if you want to work it again")
    won = session.execute(update(Organization).where(
        Organization.id == org.id, or_(Organization.owner.is_(None), func.lower(Organization.owner) == name.lower()),
    ).values(owner=func.coalesce(Organization.owner, name)).execution_options(synchronize_session=False)).rowcount
    session.refresh(org, ["owner", "crm_status"])
    if not won:
        raise AppError(409, "already_claimed", f"{org.owner} is already working on this lead")
    if org.crm_status in OPEN_STATUSES:
        change_status(session, org, "in_progress", name)

SORTS = {"score": Organization.fit_score, "name": Organization.name, "updated": Organization.updated_at,
         "follow_up": Organization.next_follow_up_at,
         "website": func.lower(Organization.website),
         # Alphabetical by the lead's first email, leads without one last.
         "email": select(func.min(func.lower(Contact.email))).where(
             Contact.organization_id == Organization.id, Contact.email.is_not(None)).scalar_subquery()}
LOADS = (selectinload(Organization.contacts), selectinload(Organization.locations),
         joinedload(Organization.score), selectinload(Organization.source_records).defer(SourceRecord.raw))
PLAIN = [f for f in LeadOut.model_fields if f not in ("contact", "contacts", "primary_email", "locations", "score", "source", "suppressed")]


def _out(org: Organization, suppressed: bool = False) -> LeadOut:
    by_role = {c.role: c for c in org.contacts}
    src = max(org.source_records, key=lambda s: s.collected_at, default=None)
    return LeadOut.model_validate({
        **{f: getattr(org, f) for f in PLAIN},
        "contact": by_role.get("authorized_official") or by_role.get("provider"),
        "contacts": sorted_contacts(org),
        "primary_email": primary_email(org),
        "locations": org.locations,
        "score": org.score,
        "suppressed": suppressed,
        "source": {"source_key": src.source_key, "collected_at": src.collected_at} if src else None,
    }, from_attributes=True)


@router.get("", response_model=LeadPage)
def list_leads(filters: Annotated[LeadFilters, Query()], session: Session = Depends(get_session),
               page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
               sort: Literal["score", "name", "updated", "follow_up", "email", "website"] = "score", order: Literal["asc", "desc"] = "desc"):
    base = lead_query(filters)
    col = SORTS[sort]
    col = col.asc().nulls_last() if order == "asc" else col.desc().nulls_last()
    # The total rides along as a window count (one round trip fewer); only an empty page needs a separate count.
    stmt = (base.add_columns(func.count().over()).options(*LOADS).order_by(col, Organization.id)
            .limit(page_size).offset((page - 1) * page_size))
    rows = session.execute(stmt).all()
    orgs = [r[0] for r in rows]
    total = rows[0][1] if rows else session.scalar(select(func.count()).select_from(base.subquery()))
    hit = suppressed_ids(session, [o.id for o in orgs])
    return LeadPage(items=[_out(o, o.id in hit) for o in orgs], total=total, page=page, page_size=page_size)


def _load(session: Session, lead_id: str, options=()) -> Organization:
    try:
        org = session.get(Organization, uuid.UUID(lead_id), options=options)
    except ValueError:
        org = None
    if org is None:
        raise AppError(404, "not_found", f"Lead {lead_id} not found")
    return org


@router.get("/{lead_id}", response_model=LeadOut)
def get_lead(lead_id: str, session: Session = Depends(get_session)):
    org = _load(session, lead_id, LOADS)
    return _out(org, bool(suppressed_ids(session, [org.id])))


@router.patch("/{lead_id}", response_model=LeadOut)
def patch_lead(lead_id: str, body: LeadPatch, session: Session = Depends(get_session), name: str | None = Depends(salesperson)):
    org = _load(session, lead_id, LOADS)
    if body.crm_status is not None:
        if body.crm_status != "do_not_contact" and suppressed_ids(session, [org.id]):
            raise AppError(409, "lead_suppressed", "Remove the suppression entry before changing this lead's status")
        if body.crm_status == "in_progress":
            claim(session, org, name)  # picking In progress means "I am working this"
        change_status(session, org, body.crm_status, name)
    if "next_follow_up_at" in body.model_fields_set:
        org.next_follow_up_at = body.next_follow_up_at
    if body.reject_website and not (org.enrichment_status == "rejected_by_user" and org.website is None):
        for c in [c for c in org.contacts if c.source_key == "practice_website"]:
            session.delete(c)
        org.website = org.website_evidence = None
        org.enrichment_status = "rejected_by_user"
        rescore_org(session, org)  # website staff points no longer apply
        add_activity(session, org, type="note", summary="Website rejected", actor=name)
    session.commit()
    session.refresh(org)  # reload server-side updated_at
    return _out(org, bool(suppressed_ids(session, [org.id])))


@router.post("/{lead_id}/claim", response_model=LeadOut)
def claim_lead(lead_id: str, session: Session = Depends(get_session), name: str | None = Depends(salesperson)):
    org = _load(session, lead_id, LOADS)
    claim(session, org, name)
    session.commit()
    session.refresh(org)
    return _out(org, bool(suppressed_ids(session, [org.id])))


@router.post("/{lead_id}/release", response_model=LeadOut)
def release_lead(lead_id: str, session: Session = Depends(get_session), name: str | None = Depends(salesperson)):
    org = _load(session, lead_id, LOADS)
    if not name:
        raise AppError(400, "name_required", "Enter your name at the top of the page first")
    if org.owner and org.owner.lower() != name.lower():
        raise AppError(409, "not_your_lead", f"{org.owner} is working on this lead, only they can release it")
    if org.owner:
        previous, org.owner = org.owner, None
        if org.crm_status == "in_progress":
            change_status(session, org, "new", name)
        add_activity(session, org, type="note", summary=f"Released by {previous}", actor=name)
    session.commit()
    session.refresh(org)
    return _out(org, bool(suppressed_ids(session, [org.id])))


@owners_router.get("", response_model=list[str])
def list_owners(session: Session = Depends(get_session)):
    return list(session.scalars(select(Organization.owner).where(Organization.owner.is_not(None)).distinct().order_by(Organization.owner)))


@router.get("/{lead_id}/activities", response_model=ActivityPage)
def list_activities(lead_id: str, session: Session = Depends(get_session),
                    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)):
    org = _load(session, lead_id)
    where = LeadActivity.organization_id == org.id
    total = session.scalar(select(func.count()).select_from(LeadActivity).where(where))
    stmt = (select(LeadActivity).where(where).order_by(LeadActivity.occurred_at.desc(), LeadActivity.created_at.desc(), LeadActivity.id)
            .limit(page_size).offset((page - 1) * page_size))
    return ActivityPage(items=session.scalars(stmt).all(), total=total, page=page, page_size=page_size)


@router.post("/{lead_id}/activities", response_model=ActivityOut, status_code=201)
def create_activity(lead_id: str, body: ActivityIn, session: Session = Depends(get_session), name: str | None = Depends(salesperson)):
    org = _load(session, lead_id)
    act = add_activity(session, org, type=body.type, occurred_at=body.occurred_at, summary=body.summary, outcome=body.outcome, actor=name)
    if "next_follow_up_at" in body.model_fields_set:
        org.next_follow_up_at = body.next_follow_up_at
    session.commit()
    return act
