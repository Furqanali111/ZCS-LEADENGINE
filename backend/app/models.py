import uuid
from datetime import date, datetime

from sqlalchemy import (
    ARRAY, DDL, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Text, UniqueConstraint, event, func, text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import (
    ACTIVITY_TYPES, CRM_STATUSES, JOB_STATUSES, ORG_TYPES, OUTCOMES, PRIORITIES, SUPPRESSION_KINDS, US_STATES,
)
from app.db import Base

SOURCE_STATUSES = ("available", "approved_not_built", "not_reviewed", "rejected")
LOCATION_PURPOSES = ("location", "mailing", "practice")
CONTACT_ROLES = ("authorized_official", "provider")


def in_list(column: str, values) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in sorted(values))})"


class IdMixin:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"), default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SourceConfig(IdMixin, Base):
    __tablename__ = "source_configs"
    __table_args__ = (CheckConstraint(in_list("status", SOURCE_STATUSES), name="ck_source_configs_status"),)

    key: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    access_method: Mapped[str | None] = mapped_column(Text)
    rate_limit_per_sec: Mapped[float | None]
    policy_reviewed_on: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)


class SearchJob(IdMixin, Base):
    __tablename__ = "search_jobs"
    __table_args__ = (
        CheckConstraint(in_list("state", US_STATES), name="ck_search_jobs_state"),
        CheckConstraint(in_list("status", JOB_STATUSES), name="ck_search_jobs_status"),
        CheckConstraint("target_count BETWEEN 1 AND 1200", name="ck_search_jobs_target_count"),
    )

    specialty: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text)
    target_count: Mapped[int] = mapped_column(Integer)
    include_practices: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    include_solo: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    include_subparts: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    include_hospitals: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    sources: Mapped[list[str]] = mapped_column(ARRAY(Text))
    status: Mapped[str] = mapped_column(Text, default="queued", server_default="queued")
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    checkpoint: Mapped[dict] = mapped_column(
        JSONB, default=lambda: {"phase": None, "skip": 0}, server_default=text('\'{"phase": null, "skip": 0}\'::jsonb')
    )
    counters: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Organization(IdMixin, Base):
    __tablename__ = "organizations"
    __table_args__ = (
        CheckConstraint(in_list("state", US_STATES), name="ck_organizations_state"),
        CheckConstraint(in_list("organization_type", ORG_TYPES), name="ck_organizations_organization_type"),
        CheckConstraint(in_list("priority", PRIORITIES), name="ck_organizations_priority"),
        CheckConstraint(in_list("crm_status", CRM_STATUSES), name="ck_organizations_crm_status"),
        Index("ix_organizations_state", "state"),
        Index("ix_organizations_primary_taxonomy_desc", "primary_taxonomy_desc"),
        Index("ix_organizations_priority", "priority"),
        Index("ix_organizations_fit_score", "fit_score"),
        Index("ix_organizations_crm_status", "crm_status"),
        Index("ix_organizations_next_follow_up_at", "next_follow_up_at"),
    )

    # The unique constraint on npi already creates the npi index the spec lists.
    npi: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    dba_name: Mapped[str | None] = mapped_column(Text)
    organization_type: Mapped[str] = mapped_column(Text)
    parent_organization_name: Mapped[str | None] = mapped_column(Text)
    primary_taxonomy_code: Mapped[str | None] = mapped_column(Text)
    primary_taxonomy_desc: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    fax: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text)
    fit_score: Mapped[int | None] = mapped_column(Integer)
    priority: Mapped[str | None] = mapped_column(Text)
    crm_status: Mapped[str] = mapped_column(Text, default="new", server_default="new")
    status_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_contacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_follow_up_at: Mapped[date | None] = mapped_column(Date)

    locations: Mapped[list["Location"]] = relationship(back_populates="organization", cascade="all, delete-orphan", passive_deletes=True)
    contacts: Mapped[list["Contact"]] = relationship(back_populates="organization", cascade="all, delete-orphan", passive_deletes=True)
    source_records: Mapped[list["SourceRecord"]] = relationship(back_populates="organization", cascade="all, delete-orphan", passive_deletes=True)
    score: Mapped["LeadScore | None"] = relationship(back_populates="organization", cascade="all, delete-orphan", passive_deletes=True, uselist=False)


def org_fk(**kw) -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), **kw)


class Location(IdMixin, Base):
    __tablename__ = "locations"
    __table_args__ = (
        UniqueConstraint("organization_id", "purpose", "address_1", "zip", name="uq_locations_org_purpose_address"),
        CheckConstraint(in_list("purpose", LOCATION_PURPOSES), name="ck_locations_purpose"),
    )

    organization_id: Mapped[uuid.UUID] = org_fk(index=True)
    purpose: Mapped[str] = mapped_column(Text)
    address_1: Mapped[str] = mapped_column(Text, default="", server_default="")
    address_2: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str | None] = mapped_column(Text)
    zip: Mapped[str] = mapped_column(Text, default="", server_default="")
    phone: Mapped[str | None] = mapped_column(Text)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))

    organization: Mapped[Organization] = relationship(back_populates="locations")


class Contact(IdMixin, Base):
    __tablename__ = "contacts"
    __table_args__ = (
        UniqueConstraint("organization_id", "role", "first_name", "last_name", name="uq_contacts_org_role_name"),
        CheckConstraint(in_list("role", CONTACT_ROLES), name="ck_contacts_role"),
    )

    organization_id: Mapped[uuid.UUID] = org_fk(index=True)
    first_name: Mapped[str] = mapped_column(Text, default="", server_default="")
    last_name: Mapped[str] = mapped_column(Text, default="", server_default="")
    title: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text)
    source_key: Mapped[str] = mapped_column(Text)

    organization: Mapped[Organization] = relationship(back_populates="contacts")


class SourceRecord(IdMixin, Base):
    __tablename__ = "source_records"
    __table_args__ = (UniqueConstraint("source_key", "external_id", name="uq_source_records_source_external"),)

    organization_id: Mapped[uuid.UUID] = org_fk(index=True)
    source_key: Mapped[str] = mapped_column(Text)
    external_id: Mapped[str] = mapped_column(Text)
    raw: Mapped[dict] = mapped_column(JSONB)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    organization: Mapped[Organization] = relationship(back_populates="source_records")


class SearchJobLead(IdMixin, Base):
    __tablename__ = "search_job_leads"
    __table_args__ = (UniqueConstraint("search_job_id", "organization_id", name="uq_search_job_leads_pair"),)

    search_job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("search_jobs.id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[uuid.UUID] = org_fk(index=True)
    was_new: Mapped[bool] = mapped_column(Boolean)


class LeadScore(IdMixin, Base):
    __tablename__ = "lead_scores"
    __table_args__ = (CheckConstraint(in_list("priority", PRIORITIES), name="ck_lead_scores_priority"),)

    organization_id: Mapped[uuid.UUID] = org_fk(unique=True)
    components: Mapped[dict] = mapped_column(JSONB)
    total: Mapped[int] = mapped_column(Integer)
    priority: Mapped[str] = mapped_column(Text)
    config_version: Mapped[str] = mapped_column(Text)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    organization: Mapped[Organization] = relationship(back_populates="score")


class LeadActivity(Base):
    """Insert-only: a database trigger rejects UPDATE and DELETE."""

    __tablename__ = "lead_activities"
    __table_args__ = (
        CheckConstraint(in_list("type", ACTIVITY_TYPES), name="ck_lead_activities_type"),
        CheckConstraint(f"outcome IS NULL OR {in_list('outcome', OUTCOMES)}", name="ck_lead_activities_outcome"),
        CheckConstraint("char_length(summary) <= 2000", name="ck_lead_activities_summary_length"),
        CheckConstraint("type = 'status_change' OR summary IS NOT NULL", name="ck_lead_activities_summary_required"),
        Index("ix_lead_activities_org_occurred", "organization_id", text("occurred_at DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"), default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"))
    type: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    summary: Mapped[str | None] = mapped_column(Text)
    outcome: Mapped[str | None] = mapped_column(Text)
    from_status: Mapped[str | None] = mapped_column(Text)
    to_status: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# Mirrors migration 0004 so create_all (used by the test fixtures) gets the same trigger.
event.listen(LeadActivity.__table__, "after_create", DDL(
    "CREATE FUNCTION lead_activities_append_only() RETURNS trigger LANGUAGE plpgsql AS "
    "$$ BEGIN RAISE EXCEPTION 'lead_activities is append-only'; END $$"
))
event.listen(LeadActivity.__table__, "after_create", DDL(
    "CREATE TRIGGER lead_activities_append_only BEFORE UPDATE OR DELETE ON lead_activities "
    "FOR EACH ROW EXECUTE FUNCTION lead_activities_append_only()"
))
event.listen(LeadActivity.__table__, "after_drop", DDL("DROP FUNCTION IF EXISTS lead_activities_append_only()"))


class SuppressionEntry(Base):
    """No foreign key to organizations on purpose: opt-outs outlive leads."""

    __tablename__ = "suppression_list"
    __table_args__ = (
        UniqueConstraint("kind", "value", name="uq_suppression_list_kind_value"),
        CheckConstraint(in_list("kind", SUPPRESSION_KINDS), name="ck_suppression_list_kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"), default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(Text)
    value: Mapped[str] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
