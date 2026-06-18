from __future__ import annotations

from pydantic import BaseModel, Field, ValidationError

from .llm.client import LLMClient
from .llm.prompts import (
    build_analysis_prompt,
    build_analysis_system_prompt,
    build_brief_deduplication_prompt,
    build_brief_deduplication_system_prompt,
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
    scoring_assessments: list[CriterionAssessment]


class BriefDedupeGroup(BaseModel):
    item_ids: list[str] = Field(min_length=1)
    title: str | None = None
    summary: str | None = None
    reason: str | None = None


class BriefDedupeResponse(BaseModel):
    groups: list[BriefDedupeGroup] = Field(min_length=1)


def generate_intelligence_items(
    events: list[DedupedEvent],
    *,
    llm_client: LLMClient,
    max_items: int | None = 5,
    neodym_profile: str | None = None,
) -> list[IntelligenceItem]:
    items: list[IntelligenceItem] = []
    for event in events:
        try:
            category = classify_event(event, llm_client)
            analysis = analyze_event(event, category.category, llm_client, neodym_profile=neodym_profile)
        except Exception:
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
            scoring_assessments=analysis.scoring_assessments,
            source_links=event.source_links,
            source_names=list(dict.fromkeys(source_item.source_name for source_item in event.source_items)),
            deduped_from_ids=[source_item.id or "" for source_item in event.source_items],
            content_fingerprint=event.content_fingerprint,
        )
        items.append(item)
        print(f"[{item.title}] from [{', '.join(item.source_names)}] got scored.", flush=True)
    ranked_items = rank_intelligence_items(items)
    if max_items is None:
        return ranked_items
    return ranked_items[:max_items]


def deduplicate_brief_items_with_llm(
    items: list[IntelligenceItem],
    llm_client: LLMClient,
) -> list[IntelligenceItem]:
    """Presentation-only LLM dedupe for selected daily brief items.

    The returned list is intended only for JSON/Markdown/Slack rendering. Callers should
    persist/report the original analyzed items before using this presentation transform.
    """
    if len(items) <= 1:
        return items

    try:
        data = llm_client.complete_json(
            system_prompt=build_brief_deduplication_system_prompt(),
            user_prompt=build_brief_deduplication_prompt(items),
        )
        response = BriefDedupeResponse.model_validate(data)
        return _apply_brief_dedupe_groups(items, response.groups)
    except Exception:
        return items


def _apply_brief_dedupe_groups(
    items: list[IntelligenceItem],
    groups: list[BriefDedupeGroup],
) -> list[IntelligenceItem]:
    by_id = {item.content_fingerprint: item for item in items}
    seen: set[str] = set()
    deduped: list[IntelligenceItem] = []

    for group in groups:
        group_ids = group.item_ids
        if any(item_id not in by_id or item_id in seen for item_id in group_ids):
            raise ValueError("brief dedupe groups must reference each input id exactly once")
        seen.update(group_ids)
        group_items = [by_id[item_id] for item_id in group_ids]
        if len(group_items) == 1:
            # Explicitly preserve unrelated/singleton items exactly as analyzed, even if
            # the LLM supplied rewritten title/summary fields.
            deduped.append(group_items[0])
            continue
        deduped.append(_merge_brief_items(group_items, title=group.title, summary=group.summary))

    if seen != set(by_id):
        raise ValueError("brief dedupe response omitted one or more input ids")
    return deduped


def _merge_brief_items(
    items: list[IntelligenceItem],
    *,
    title: str | None,
    summary: str | None,
) -> IntelligenceItem:
    strongest = max(items, key=lambda item: (item.importance_score, item.raw_score))
    source_links = list(dict.fromkeys(link for item in items for link in item.source_links))
    source_names = list(dict.fromkeys(name for item in items for name in item.source_names))
    deduped_from_ids = list(dict.fromkeys(raw_id for item in items for raw_id in item.deduped_from_ids if raw_id))
    return strongest.model_copy(
        update={
            "title": title or strongest.title,
            "summary": summary or strongest.summary,
            "source_links": source_links,
            "source_names": source_names,
            "deduped_from_ids": deduped_from_ids,
        }
    )


def _complete_json_with_retry(llm_client: LLMClient, *, system_prompt: str, user_prompt: str) -> dict:
    try:
        return llm_client.complete_json(system_prompt=system_prompt, user_prompt=user_prompt)
    except Exception:
        return llm_client.complete_json(system_prompt=system_prompt, user_prompt=user_prompt)


def classify_event(event: DedupedEvent, llm_client: LLMClient) -> CategoryResponse:
    system_prompt = build_categorization_system_prompt()
    user_prompt = build_categorization_prompt(event)
    data = _complete_json_with_retry(llm_client, system_prompt=system_prompt, user_prompt=user_prompt)
    try:
        return CategoryResponse.model_validate(data)
    except ValidationError as exc:
        retry_data = _complete_json_with_retry(
            llm_client,
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
    data = _complete_json_with_retry(llm_client, system_prompt=system_prompt, user_prompt=user_prompt)
    try:
        return _validate_analysis_response(data)
    except (ValidationError, ValueError) as exc:
        retry_data = _complete_json_with_retry(
            llm_client,
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
