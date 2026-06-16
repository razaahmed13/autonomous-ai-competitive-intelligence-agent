from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, field_validator


class CriterionStatus(StrEnum):
    MISSING = "missing"
    VERY_WEAK = "very_weak"
    WEAK = "weak"
    PARTIAL = "partial"
    GOOD = "good"
    STRONG = "strong"
    EXCELLENT = "excellent"


class CriterionAssessment(BaseModel):
    id: str
    status: CriterionStatus
    evidence: str
    reason: str

    @field_validator("id", "evidence", "reason")
    @classmethod
    def non_empty_text(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("value must not be empty")
        return value


SCORING_CRITERIA: dict[str, float] = {
    "neodym_relevance": 25,
    "market_impact": 18,
    "technical_novelty": 15,
    "agent_automation_relevance": 12,
    "client_roi_potential": 10,
    "urgency": 8,
    "source_credibility": 6,
    "actionability": 6,
}

STATUS_MULTIPLIERS: dict[CriterionStatus, float] = {
    CriterionStatus.MISSING: 0,
    CriterionStatus.VERY_WEAK: 0.15,
    CriterionStatus.WEAK: 0.3,
    CriterionStatus.PARTIAL: 0.5,
    CriterionStatus.GOOD: 0.7,
    CriterionStatus.STRONG: 0.85,
    CriterionStatus.EXCELLENT: 1,
}


def validate_assessments(assessments: list[CriterionAssessment]) -> list[CriterionAssessment]:
    expected_ids = set(SCORING_CRITERIA)
    actual_ids = [assessment.id for assessment in assessments]
    actual_id_set = set(actual_ids)

    duplicates = sorted({criterion_id for criterion_id in actual_ids if actual_ids.count(criterion_id) > 1})
    unknown = sorted(actual_id_set - expected_ids)
    missing = sorted(expected_ids - actual_id_set)
    if duplicates or unknown or missing:
        details = []
        if missing:
            details.append(f"missing criteria: {', '.join(missing)}")
        if duplicates:
            details.append(f"duplicate criteria: {', '.join(duplicates)}")
        if unknown:
            details.append(f"unknown criteria: {', '.join(unknown)}")
        raise ValueError("; ".join(details))
    return assessments


def calculate_raw_score(assessments: list[CriterionAssessment]) -> float:
    validate_assessments(assessments)
    total = sum(
        SCORING_CRITERIA[assessment.id] * STATUS_MULTIPLIERS[assessment.status]
        for assessment in assessments
    )
    return round(total, 1)


def calculate_importance_score(raw_score: float) -> float:
    return max(1.0, round(raw_score / 10, 1))


def build_score_reason(assessments: list[CriterionAssessment], raw_score: float, importance_score: float) -> str:
    validate_assessments(assessments)
    strongest = _format_statuses(
        assessments,
        {CriterionStatus.GOOD, CriterionStatus.STRONG, CriterionStatus.EXCELLENT},
        reverse=True,
    )
    weakest = _format_statuses(
        assessments,
        {CriterionStatus.MISSING, CriterionStatus.VERY_WEAK, CriterionStatus.WEAK, CriterionStatus.PARTIAL},
        reverse=False,
    )
    reason = f"Scored {importance_score:.1f}/10 ({raw_score:.1f}/100) using deterministic weighted criteria."
    if strongest:
        reason += f" Strongest signals: {strongest}."
    if weakest:
        reason += f" Limiting factors: {weakest}."
    return reason


def criteria_prompt_text() -> str:
    lines = ["Scoring criteria. Return exactly one assessment for each id:"]
    for criterion_id in SCORING_CRITERIA:
        lines.append(f"- {criterion_id}")
    lines.extend(
        [
            "",
            "Allowed statuses:",
            "- missing: No source-grounded evidence supports this criterion.",
            "- very_weak: Barely relevant; evidence is indirect, speculative, or extremely thin.",
            "- weak: Some relevance, but evidence is limited or expected impact is low.",
            "- partial: Clear but incomplete relevance; useful signal, not decisive.",
            "- good: Solid source-grounded relevance with plausible practical impact.",
            "- strong: Clear, important, and well-supported relevance to Neodym or the AI market.",
            "- excellent: Exceptional relevance; immediate, strategic, highly actionable, and strongly evidenced.",
            "",
            "Status assignment rules:",
            "- Use only the provided source context as evidence.",
            "- Do not assign strong or excellent unless the source context directly supports the criterion.",
            "- Prefer lower statuses when evidence is thin, indirect, or speculative.",
            "- Evidence must explain what source detail supports the selected status.",
        ]
    )
    return "\n".join(lines)


def _format_statuses(
    assessments: list[CriterionAssessment],
    statuses: set[CriterionStatus],
    *,
    reverse: bool,
) -> str:
    matching = [assessment for assessment in assessments if assessment.status in statuses]
    matching.sort(
        key=lambda assessment: STATUS_MULTIPLIERS[assessment.status],
        reverse=reverse,
    )
    return ", ".join(f"{assessment.id}={assessment.status.value}" for assessment in matching[:3])
