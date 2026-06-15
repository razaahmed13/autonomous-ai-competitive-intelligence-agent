from __future__ import annotations

from pydantic import BaseModel, Field, ValidationError

from .llm.client import LLMClient
from .llm.prompts import (
    build_analysis_prompt,
    build_analysis_system_prompt,
    build_categorization_prompt,
    build_categorization_system_prompt,
)
from .models import DedupedEvent, IntelligenceCategory, IntelligenceItem
from .ranking import rank_intelligence_items


class CategoryResponse(BaseModel):
    category: IntelligenceCategory
    confidence: float = Field(ge=0, le=1)
    reason: str


class AnalysisResponse(BaseModel):
    title: str
    importance_score: int = Field(ge=1, le=10)
    score_reason: str
    summary: str
    why_it_matters: str
    why_it_matters_to_neodym: str
    recommended_action: str


def generate_intelligence_items(
    events: list[DedupedEvent],
    *,
    llm_client: LLMClient,
    max_items: int = 8,
) -> list[IntelligenceItem]:
    items: list[IntelligenceItem] = []
    for event in events:
        category = classify_event(event, llm_client)
        analysis = analyze_event(event, category.category, llm_client)
        item = IntelligenceItem(
            title=analysis.title,
            category=category.category,
            importance_score=analysis.importance_score,
            score_reason=analysis.score_reason,
            summary=analysis.summary,
            why_it_matters=analysis.why_it_matters,
            why_it_matters_to_neodym=analysis.why_it_matters_to_neodym,
            recommended_action=analysis.recommended_action,
            source_links=event.source_links,
            source_names=list(dict.fromkeys(source_item.source_name for source_item in event.source_items)),
            deduped_from_ids=[source_item.id or "" for source_item in event.source_items],
        )
        items.append(item)
    return rank_intelligence_items(items)[:max_items]


def classify_event(event: DedupedEvent, llm_client: LLMClient) -> CategoryResponse:
    data = llm_client.complete_json(
        system_prompt=build_categorization_system_prompt(),
        user_prompt=build_categorization_prompt(event),
    )
    try:
        return CategoryResponse.model_validate(data)
    except ValidationError:
        # The plan allows invalid category fallback to Other after validation failure.
        return CategoryResponse(category=IntelligenceCategory.OTHER, confidence=0, reason="Invalid LLM category response; fell back to Other.")


def analyze_event(event: DedupedEvent, category: IntelligenceCategory, llm_client: LLMClient) -> AnalysisResponse:
    data = llm_client.complete_json(
        system_prompt=build_analysis_system_prompt(),
        user_prompt=build_analysis_prompt(event, category),
    )
    return AnalysisResponse.model_validate(data)
