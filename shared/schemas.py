"""Shared Pydantic schemas — wire format consumed by all microservices."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class PlaceSearchResult(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    id: str
    name: str
    address: str
    lat: float
    lng: float
    category: str
    rating: float
    review_count: int


class PlaceDetails(PlaceSearchResult):
    model_config = ConfigDict(strict=True, extra="forbid")

    website: str | None = None
    phone: str | None = None
    hours: list[str] = []
    photos: list[str] = []


class QualifierVerdict(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    is_qualified: bool
    score: float = Field(ge=0.0, le=1.0)
    reasoning: str
    icp_fit: dict[str, bool]


class GeneratedEmail(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    subject: Annotated[str, StringConstraints(max_length=100)]
    body: Annotated[str, StringConstraints(max_length=1500)]
    personalization_hooks: list[str]
    model_used: str


class Lead(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    place: PlaceDetails
    verdict: QualifierVerdict | None = None
    email: GeneratedEmail | None = None
    decision: Literal["pending", "approved", "rejected"] = "pending"


class Run(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    id: UUID
    prompt: str
    target_query: str
    limit: int
    leads: list[Lead]
    created_at: datetime
    status: Literal["scraping", "qualifying", "generating", "completed", "failed"]
