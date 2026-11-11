import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.constants import US_STATES


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    name: str
    status: str
    notes: str | None


class SearchCreate(BaseModel):
    specialty: str = Field(min_length=1, max_length=100)
    state: str
    city: str | None = Field(default=None, max_length=100)
    target_count: int = Field(default=500, ge=1, le=1200)
    include_practices: bool = True
    include_solo: bool = True
    include_subparts: bool = True
    include_hospitals: bool = False
    sources: list[str] = Field(min_length=1)

    @field_validator("specialty", mode="before")
    @classmethod
    def strip_specialty(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("state", mode="before")
    @classmethod
    def upper_state(cls, v):
        v = v.strip().upper() if isinstance(v, str) else v
        if v not in US_STATES:
            raise ValueError("must be a US state or DC code")
        return v

    @field_validator("city", mode="before")
    @classmethod
    def blank_city(cls, v):
        return (v.strip() or None) if isinstance(v, str) else v

    @model_validator(mode="after")
    def need_a_lead_type(self):
        if not (self.include_practices or self.include_solo):
            raise ValueError("include_practices and include_solo cannot both be false")
        return self


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
    status: str
    counters: dict
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
