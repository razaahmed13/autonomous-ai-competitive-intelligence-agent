from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

from .scoring import CriterionAssessment


class SourceType(StrEnum):
    RSS = "rss"
    WEB = "web"
    API = "api"


class IntelligenceCategory(StrEnum):
    MODEL_RELEASE = "Model Release"
    RESEARCH = "Research"
    STARTUP_ACTIVITY = "Startup Activity"
    COMPETITOR_UPDATE = "Competitor Update"
    INFRASTRUCTURE = "Infrastructure"
    REGULATION = "Regulation"
    OTHER = "Other"


def _normalized_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class SourceConfig(BaseModel):
    model_config = ConfigDict(use_enum_values=False)

    name: str
    type: SourceType
    url: str
    category_hint: str | None = None

    @field_validator("name", "url")
    @classmethod
    def non_empty(cls, value: str) -> str:
        value = _normalized_text(value)
        if not value:
            raise ValueError("value must not be empty")
        return value


class RawSourceItem(BaseModel):
    model_config = ConfigDict(use_enum_values=False)

    id: str | None = None
    source_name: str
    source_type: SourceType
    title: str
    url: str
    published_at: datetime | None = None
    author: str | None = None
    raw_summary: str | None = None
    content: str | None = None
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    content_hash: str | None = None

    @field_validator("source_name", "title", "url")
    @classmethod
    def required_text(cls, value: str) -> str:
        value = _normalized_text(value)
        if not value:
            raise ValueError("value must not be empty")
        return value

    @field_validator("raw_summary", "content", "author")
    @classmethod
    def optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = _normalized_text(value)
        return value or None

    @model_validator(mode="after")
    def set_hashes(self) -> "RawSourceItem":
        hash_source = "|".join(
            [
                self.source_name.lower(),
                self.title.lower(),
                self.url,
                self.raw_summary or "",
                self.content or "",
            ]
        )
        self.content_hash = self.content_hash or _hash_text(hash_source)
        self.id = self.id or _hash_text(f"{self.source_name.lower()}|{self.url}")[:24]
        return self


class DedupedEvent(BaseModel):
    id: str
    canonical_title: str
    source_items: list[RawSourceItem]
    source_links: list[str]
    merged_summary: str | None = None
    content_fingerprint: str

    @field_validator("canonical_title", "content_fingerprint")
    @classmethod
    def non_empty_text(cls, value: str) -> str:
        value = _normalized_text(value)
        if not value:
            raise ValueError("value must not be empty")
        return value

    @field_validator("source_items", "source_links")
    @classmethod
    def non_empty_list(cls, value: list) -> list:
        if not value:
            raise ValueError("list must not be empty")
        return value


class IntelligenceItem(BaseModel):
    title: str
    category: IntelligenceCategory
    importance_score: float = Field(ge=1, le=10)
    raw_score: float = Field(ge=0, le=100)
    score_reason: str
    summary: str
    why_it_matters: str
    why_it_matters_to_neodym: str
    recommended_action: str
    scoring_assessments: list[CriterionAssessment]
    source_links: list[str]
    source_names: list[str] = Field(default_factory=list)
    deduped_from_ids: list[str] = Field(default_factory=list)
    content_fingerprint: str

    @field_validator("title", "score_reason", "summary", "why_it_matters", "why_it_matters_to_neodym", "recommended_action", "content_fingerprint")
    @classmethod
    def required_intelligence_text(cls, value: str) -> str:
        value = _normalized_text(value)
        if not value:
            raise ValueError("value must not be empty")
        return value

    @field_validator("source_links")
    @classmethod
    def requires_sources(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("intelligence items require at least one source link")
        return value


class DailyBrief(BaseModel):
    date: str
    generated_at: datetime
    methodology: str
    items: list[IntelligenceItem]
    source_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    selected_count: int = Field(ge=0)
