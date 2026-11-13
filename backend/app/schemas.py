import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.constants import ACTIVITY_TYPES, CRM_STATUSES, ORG_TYPES, OUTCOMES, PRIORITIES, US_STATES


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    name: str
    status: str
    notes: str | None
    key_missing: bool = False


class SearchCreate(BaseModel):
    specialty: str = Field(min_length=1, max_length=100)
    state: str
    city: str | None = Field(default=None, max_length=100)
    target_count: int = Field(default=500, ge=1, le=50000)
    include_practices: bool = True
    include_solo: bool = True
    include_subparts: bool = True
    include_hospitals: bool = False
    sources: list[str] = Field(min_length=1)
    enrich: bool = False

    @field_validator("specialty", mode="before")
    @classmethod
    def strip_specialty(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("state", mode="before")
    @classmethod
    def upper_state(cls, v):
        if not isinstance(v, str):
            raise ValueError("must be a string")
        v = v.strip().upper()
        if v not in US_STATES:
            raise ValueError("must be a US state or DC code")
        return v

    @field_validator("city", mode="before")
    @classmethod
    def blank_city(cls, v):
        return (v.strip() or None) if isinstance(v, str) else v

    @field_validator("sources")
    @classmethod
    def dedupe_sources(cls, v):
        return list(dict.fromkeys(v))

    @model_validator(mode="after")
    def need_a_lead_type(self):
        if not (self.include_practices or self.include_solo):
            raise ValueError("include_practices and include_solo cannot both be false")
        return self


class SavedSearchIn(SearchCreate):
    name: str = Field(min_length=1, max_length=60)

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v):
        return v.strip() if isinstance(v, str) else v


class SavedSearchOut(SavedSearchIn):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_by: str | None
    created_at: datetime
    last_run_at: datetime | None


class ProgressOut(BaseModel):
    leads_fetched: int
    exhausted: bool  # every phase walked so far has been read to the end


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    specialty: str
    state: str
    city: str | None
    target_count: int
    include_practices: bool
    include_solo: bool
    include_subparts: bool
    include_hospitals: bool
    sources: list[str]
    enrich: bool
    status: str
    counters: dict
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class LeadFilters(BaseModel):
    q: str | None = None
    state: str | None = None
    specialty: str | None = None
    organization_type: str | None = None
    priority: str | None = None
    min_score: int | None = Field(default=None, ge=0, le=100)
    crm_status: str | None = None
    owner: str | None = None  # a name, or "none" for unclaimed
    search_job_id: uuid.UUID | None = None
    follow_up: Literal["due", "overdue", "none"] | None = None
    has_website: bool | None = None
    has_email: bool | None = None
    email_sent: bool | None = None

    @field_validator("state", mode="before")
    @classmethod
    def upper_state(cls, v):
        if v is None:
            return v
        if not isinstance(v, str) or v.strip().upper() not in US_STATES:
            raise ValueError("must be a US state or DC code")
        return v.strip().upper()

    @field_validator("organization_type", "priority", "crm_status")
    @classmethod
    def known_value(cls, v, info):
        allowed = {"organization_type": ORG_TYPES, "priority": PRIORITIES, "crm_status": CRM_STATUSES}[info.field_name]
        if v is not None and v not in allowed:
            raise ValueError(f"must be one of {', '.join(allowed)}")
        return v


class LeadPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    crm_status: str | None = None
    next_follow_up_at: date | None = None  # explicit null clears it; told apart from missing via model_fields_set
    reject_website: bool | None = None
    email_sent: bool | None = None

    @field_validator("email_sent")
    @classmethod
    def not_null(cls, v):
        if v is None:  # an explicit null is not a value
            raise ValueError("must be true or false")
        return v

    @field_validator("crm_status")
    @classmethod
    def known_status(cls, v):
        if v not in CRM_STATUSES:  # also rejects an explicit null
            raise ValueError(f"must be one of {', '.join(CRM_STATUSES)}")
        return v

    @field_validator("reject_website")
    @classmethod
    def only_true(cls, v):
        if v is not True:  # rejecting is one-way here; also rejects an explicit null
            raise ValueError("must be true")
        return v

    @model_validator(mode="after")
    def need_a_field(self):
        if not self.model_fields_set:
            raise ValueError("send crm_status, next_follow_up_at, email_sent and/or reject_website")
        return self


class ActivityIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    occurred_at: datetime | None = None
    summary: str = Field(min_length=1, max_length=2000)
    outcome: str | None = None
    next_follow_up_at: date | None = None

    @field_validator("summary")
    @classmethod
    def strip_summary(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v

    @field_validator("type")
    @classmethod
    def known_type(cls, v):
        # status_change is written only by status updates, never posted directly
        allowed = [t for t in ACTIVITY_TYPES if t != "status_change"]
        if v not in allowed:
            raise ValueError(f"must be one of {', '.join(allowed)}")
        return v

    @field_validator("outcome")
    @classmethod
    def known_outcome(cls, v):
        if v is not None and v not in OUTCOMES:
            raise ValueError(f"must be one of {', '.join(OUTCOMES)}")
        return v

    @field_validator("occurred_at")
    @classmethod
    def assume_utc(cls, v):
        if v is not None and v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        if v is not None and v > datetime.now(timezone.utc) + timedelta(days=1):
            raise ValueError("must not be more than 1 day in the future")
        return v


class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    occurred_at: datetime
    summary: str | None
    outcome: str | None
    from_status: str | None
    to_status: str | None
    actor: str | None = None
    created_at: datetime


class ActivityPage(BaseModel):
    items: list[ActivityOut]
    total: int
    page: int
    page_size: int


class ContactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    first_name: str | None
    last_name: str | None
    title: str | None
    phone: str | None
    role: str | None
    email: str | None = None
    email_status: str | None = None
    source_url: str | None = None
    collected_at: datetime | None = None


class LocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    purpose: str | None
    address_1: str | None
    address_2: str | None
    city: str | None
    state: str | None
    zip: str | None
    phone: str | None
    is_primary: bool


class ScoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    components: dict
    config_version: str
    calculated_at: datetime


class SourceInfoOut(BaseModel):
    source_key: str
    collected_at: datetime


class RelatedOut(BaseModel):
    id: uuid.UUID
    name: str
    city: str | None
    state: str | None
    crm_status: str
    owner: str | None
    fit_score: int | None
    priority: str | None
    reasons: list[str]


class LeadOut(BaseModel):
    id: uuid.UUID
    npi: str
    name: str
    dba_name: str | None
    organization_type: str
    parent_organization_name: str | None
    primary_taxonomy_desc: str | None
    phone: str | None
    fax: str | None
    city: str | None
    state: str | None
    fit_score: int | None
    priority: str | None
    crm_status: str
    owner: str | None = None
    email_sent: bool = False
    email_sent_by: str | None = None
    updated_at: datetime
    last_contacted_at: datetime | None
    next_follow_up_at: date | None
    suppressed: bool = False
    website: str | None
    enrichment_status: str
    website_evidence: dict | None
    primary_email: str | None
    contact: ContactOut | None
    contacts: list[ContactOut]
    locations: list[LocationOut]
    score: ScoreOut | None
    source: SourceInfoOut | None


class LeadPage(BaseModel):
    items: list[LeadOut]
    total: int
    page: int
    page_size: int


class ExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filters: LeadFilters | None = None
    ids: list[uuid.UUID] | None = Field(default=None, max_length=5000)


class PipelineCard(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    city: str | None
    state: str | None
    organization_type: str
    fit_score: int | None
    priority: str | None
    owner: str | None = None
    next_follow_up_at: date | None
    last_contacted_at: datetime | None


class PipelineColumn(BaseModel):
    status: str
    count: int
    leads: list[PipelineCard]


class PipelineBoard(BaseModel):
    columns: list[PipelineColumn]


class DateRange(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: date = Field(alias="from")
    to: date


class CountItem(BaseModel):
    key: str
    count: int


class Conversion(BaseModel):
    """Recorded outcomes only: never a prediction."""

    converted: int
    contacted: int
    rate: float | None


class DashboardStats(BaseModel):
    range: DateRange
    total: int
    new_leads: int
    critical_high: int
    follow_ups_due: int
    status_changes_today: int
    meetings_scheduled: int
    converted: int
    by_state: list[CountItem]
    by_specialty: list[CountItem]
    by_status: list[CountItem]
    recent_jobs: list[JobOut]
    conversion: Conversion


class SuppressionIn(BaseModel):
    kind: Literal["npi", "phone", "email"]
    value: str
    reason: str | None = Field(default=None, max_length=500)


class SuppressionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    value: str
    reason: str | None
    created_at: datetime


class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    kind: Literal["email", "call", "message"]
    subject: str | None = Field(default=None, max_length=200)
    body: str = Field(min_length=1, max_length=5000)

    @model_validator(mode="after")
    def subject_only_for_email(self):
        if self.subject is not None and self.kind != "email":
            raise ValueError("subject is only allowed for email templates")
        return self


class TemplatePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    kind: Literal["email", "call", "message"] | None = None
    subject: str | None = Field(default=None, max_length=200)
    body: str | None = Field(default=None, min_length=1, max_length=5000)


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    kind: str
    subject: str | None
    body: str
    created_at: datetime
    updated_at: datetime
