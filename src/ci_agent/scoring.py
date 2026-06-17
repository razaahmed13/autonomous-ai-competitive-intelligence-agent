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
    "ai_developer_relevance": 25,
    "market_impact": 18,
    "neodym_relevance": 13,
    "strategic_business_signal": 12,
    "agent_automation_relevance": 10,
    "technical_novelty": 7,
    "client_roi_potential": 5,
    "urgency": 5,
    "source_credibility": 5,
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
            "- very_weak: Only a bare, indirect, or speculative signal supports this criterion.",
            "- weak: Some source-grounded relevance, but the evidence or expected impact is limited.",
            "- partial: Clear source-grounded relevance, but the signal is incomplete, narrow, early, or not yet decisive.",
            "- good: Solid source-grounded relevance with plausible practical or strategic impact.",
            "- strong: Clear, important, well-supported relevance with meaningful impact for this criterion.",
            "- excellent: Exceptional, source-grounded relevance with immediate, strategic, or unusually high impact for this criterion.",
            "",
            "Status assignment rules:",
            "- Use only the provided source context as evidence.",
            "- Do not assign strong or excellent unless the source context directly supports the criterion.",
            "- Prefer lower statuses when evidence is thin, indirect, or speculative.",
            "- Evidence must explain what source detail supports the selected status.",
            "",
            "AI-development priority calibration:",
            "- Prioritize high-value AI developments that directly affect builders and technical decision-makers: foundation models, agent frameworks, coding tools, AI infrastructure, evaluation systems, and AI developer tooling.",
            "- Assign strong or excellent for ai_developer_relevance when the source directly shows new or materially changed model capabilities, agent/coding workflows, AI infrastructure, eval/benchmark systems, SDKs, orchestration frameworks, deployment tooling, or other developer-facing AI capabilities.",
            "- Generic funding, acquisition, valuation, or business news should not receive strong or excellent for ai_developer_relevance unless the source shows unusually high impact on the AI developer ecosystem, foundation-model landscape, AI infrastructure stack, platform control, or developer distribution.",
            "",
            "Market-impact calibration:",
            "- For vendor tutorials, how-to posts, benchmark writeups, product walkthroughs, and technical explainers: Do not assign strong or excellent for market_impact, strategic_business_signal, urgency, or client_roi_potential unless the source directly shows major adoption, revenue impact, enterprise rollout, large customer demand, pricing shift, or strategic market movement.",
            "- Such technical/vendor items may receive good or strong for ai_developer_relevance, technical_novelty, or agent_automation_relevance when directly supported, but business-impact criteria should usually stay partial or good at most.",
            "- For generic funding, acquisition, valuation, or business news, avoid strong or excellent market_impact or strategic_business_signal unless the story has unusually high impact: a major market shift, very large deal, strategic platform control, major enterprise adoption, or direct effect on the AI developer ecosystem.",
            "- For a large acquisition, funding round, IPO, valuation change, pricing war, market-share shift, or large enterprise/customer adoption event, assign strong or excellent for market_impact when the source shows clear market movement.",
            "- Assign strong or excellent for strategic_business_signal when an event changes competitive positioning, platform economics, pricing, distribution, or AI adoption behavior.",
            "- Assign strong urgency when competitors, customers, or implementation teams are likely to react soon.",
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
