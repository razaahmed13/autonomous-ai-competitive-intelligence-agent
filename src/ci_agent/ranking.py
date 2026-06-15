from __future__ import annotations

from .models import IntelligenceItem


def rank_intelligence_items(items: list[IntelligenceItem]) -> list[IntelligenceItem]:
    return sorted(
        items,
        key=lambda item: (
            item.importance_score,
            len(item.source_links),
            item.title.lower(),
        ),
        reverse=True,
    )
