from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from ..models import DailyBrief, IntelligenceItem

METHODOLOGY = (
    "Items are ranked by LLM-assigned importance score using a rubric based on strategic relevance to Neodym, "
    "market impact, technical novelty, urgency, and source credibility. Ties are broken by source support."
)


def build_daily_brief(
    items: list[IntelligenceItem],
    *,
    source_count: int,
    candidate_count: int,
    generated_at: datetime | None = None,
) -> DailyBrief:
    generated_at = generated_at or datetime.now(UTC)
    return DailyBrief(
        date=generated_at.date().isoformat(),
        generated_at=generated_at,
        methodology=METHODOLOGY,
        items=items,
        source_count=source_count,
        candidate_count=candidate_count,
        selected_count=len(items),
    )


def write_json_report(
    items: list[IntelligenceItem],
    path: str | Path,
    *,
    source_count: int,
    candidate_count: int,
) -> DailyBrief:
    brief = build_daily_brief(items, source_count=source_count, candidate_count=candidate_count)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(brief.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return brief
