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
from .scoring import (
    CriterionAssessment,
    build_score_reason,
    calculate_importance_score,
    calculate_raw_score,
    validate_assessments,
)


class CategoryResponse(BaseModel):
    category: IntelligenceCategory
    confidence: float = Field(ge=0, le=1)
    reason: str


class AnalysisResponse(BaseModel):
    title: str
    summary: str
    why_it_matters: str
    why_it_matters_to_neodym: str
    recommended_action: str
    scoring_assessments: list[CriterionAssessment]


def generate_intelligence_items(
    events: list[DedupedEvent],
    *,
    llm_client: LLMClient,
    max_items: int = 8,
    neodym_profile: str | None = None,
) -> list[IntelligenceItem]:
    items: list[IntelligenceItem] = []
    for event in events:
        category = classify_event(event, llm_client)
        try:
            analysis = analyze_event(event, category.category, llm_client, neodym_profile=neodym_profile)
        except (ValidationError, ValueError):
            continue
        raw_score = calculate_raw_score(analysis.scoring_assessments)
        importance_score = calculate_importance_score(raw_score)
        item = IntelligenceItem(
            title=analysis.title,
            category=category.category,
            importance_score=importance_score,
            raw_score=raw_score,
            score_reason=build_score_reason(analysis.scoring_assessments, raw_score, importance_score),
            summary=analysis.summary,
            why_it_matters=analysis.why_it_matters,
            why_it_matters_to_neodym=analysis.why_it_matters_to_neodym,
            recommended_action=analysis.recommended_action,
            scoring_assessments=analysis.scoring_assessments,
            source_links=event.source_links,
            source_names=list(dict.fromkeys(source_item.source_name for source_item in event.source_items)),
            deduped_from_ids=[source_item.id or "" for source_item in event.source_items],
        )
        items.append(item)
    return rank_intelligence_items(items)[:max_items]


def classify_event(event: DedupedEvent, llm_client: LLMClient) -> CategoryResponse:
    system_prompt = build_categorization_system_prompt()
    user_prompt = build_categorization_prompt(event)
    data = llm_client.complete_json(system_prompt=system_prompt, user_prompt=user_prompt)
    try:
        return CategoryResponse.model_validate(data)
    except ValidationError as exc:
        retry_data = llm_client.complete_json(
            system_prompt=system_prompt,
            user_prompt=_retry_prompt(user_prompt, exc),
        )
        try:
            return CategoryResponse.model_validate(retry_data)
        except ValidationError:
            # The plan allows invalid category fallback to Other after validation failure.
            return CategoryResponse(
                category=IntelligenceCategory.OTHER,
                confidence=0,
                reason="Invalid LLM category response after retry; fell back to Other.",
            )


def analyze_event(
    event: DedupedEvent,
    category: IntelligenceCategory,
    llm_client: LLMClient,
    *,
    neodym_profile: str | None = None,
) -> AnalysisResponse:
    system_prompt = build_analysis_system_prompt()
    user_prompt = build_analysis_prompt(event, category, neodym_profile=neodym_profile)
    data = llm_client.complete_json(system_prompt=system_prompt, user_prompt=user_prompt)
    try:
        return _validate_analysis_response(data)
    except (ValidationError, ValueError) as exc:
        retry_data = llm_client.complete_json(
            system_prompt=system_prompt,
            user_prompt=_retry_prompt(user_prompt, exc),
        )
        return _validate_analysis_response(retry_data)


def _retry_prompt(original_prompt: str, error: Exception) -> str:
    return f"""
{original_prompt}

The previous JSON response failed validation:
{error}

Return corrected JSON only. Respect every schema constraint exactly. For analysis, include exactly all required scoring_assessments with allowed criterion ids and statuses.
""".strip()


def _validate_analysis_response(data: dict) -> AnalysisResponse:
    response = AnalysisResponse.model_validate(data)
    response.scoring_assessments = validate_assessments(response.scoring_assessments)
    return response
