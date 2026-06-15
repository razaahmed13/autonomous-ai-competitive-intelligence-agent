from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Callable

from .config import Settings, load_neodym_profile
from .database import Database
from .deduplication import deduplicate_raw_items
from .fetchers.rss import fetch_rss_source
from .intelligence import generate_intelligence_items
from .llm.client import LLMClient, build_llm_client
from .models import IntelligenceItem, RawSourceItem, SourceConfig, SourceType
from .report.json_report import write_json_report
from .report.slack_markdown import write_slack_markdown
from .sources import DEFAULT_SOURCES

Fetcher = Callable[[SourceConfig, Settings], list[RawSourceItem]]


@dataclass(frozen=True)
class SourceFailure:
    source_name: str
    error: str


@dataclass(frozen=True)
class CollectionResult:
    source_count: int
    raw_item_count: int
    inserted_count: int
    skipped_stale_count: int = 0
    failed_sources: list[SourceFailure] = field(default_factory=list)


@dataclass(frozen=True)
class BriefResult:
    source_count: int
    raw_item_count: int
    candidate_count: int
    selected_count: int
    skipped_reported_count: int
    reported_count: int
    json_path: Path
    markdown_path: Path


def default_fetcher(source: SourceConfig, settings: Settings) -> list[RawSourceItem]:
    if source.type is SourceType.RSS:
        return fetch_rss_source(source, settings)
    raise ValueError(f"Unsupported source type: {source.type}")


def filter_collectable_items_by_published_at(
    items: list[RawSourceItem],
    *,
    now: datetime | None = None,
    max_age_hours: int = 24,
) -> list[RawSourceItem]:
    """Keep only fresh published items while preserving missing-date items."""
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    cutoff = now.astimezone(UTC) - timedelta(hours=max_age_hours)

    collectable: list[RawSourceItem] = []
    for item in items:
        if item.published_at is None:
            collectable.append(item)
            continue
        published_at = item.published_at
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=UTC)
        if published_at.astimezone(UTC) >= cutoff:
            collectable.append(item)
    return collectable


def collect_sources(
    sources: list[SourceConfig] | None = None,
    settings: Settings | None = None,
    database: Database | None = None,
    fetcher: Fetcher = default_fetcher,
) -> CollectionResult:
    settings = settings or Settings.from_env()
    sources = sources or DEFAULT_SOURCES
    database = database or Database(settings.database_path)
    database.initialize()

    fetched_items: list[RawSourceItem] = []
    failures: list[SourceFailure] = []
    for source in sources:
        try:
            fetched_items.extend(fetcher(source, settings))
        except Exception as exc:
            failures.append(SourceFailure(source_name=source.name, error=str(exc)))

    collectable_items = filter_collectable_items_by_published_at(fetched_items)
    inserted = database.upsert_raw_items(collectable_items)
    return CollectionResult(
        source_count=len(sources),
        raw_item_count=len(collectable_items),
        inserted_count=inserted,
        skipped_stale_count=len(fetched_items) - len(collectable_items),
        failed_sources=failures,
    )


def generate_brief(
    *,
    raw_items: list[RawSourceItem] | None = None,
    settings: Settings | None = None,
    database: Database | None = None,
    llm_client: LLMClient | None = None,
    json_path: str | Path = "daily_brief.json",
    markdown_path: str | Path = "daily_brief.md",
    max_items: int = 5,
    force: bool = False,
) -> BriefResult:
    settings = settings or Settings.from_env()
    database = database or Database(settings.database_path)
    database.initialize()
    raw_items = raw_items if raw_items is not None else database.list_recent_raw_items(
        hours=settings.brief_lookback_hours,
        limit=200,
    )
    llm_client = llm_client or build_llm_client(settings)
    neodym_profile = load_neodym_profile(settings.neodym_profile_path)

    events = deduplicate_raw_items(raw_items)
    reported_fingerprints = set() if force else database.reported_fingerprints(
        event.content_fingerprint for event in events
    )
    eligible_events = [
        event for event in events if force or event.content_fingerprint not in reported_fingerprints
    ]
    intelligence_items = generate_intelligence_items(
        eligible_events,
        llm_client=llm_client,
        max_items=max_items,
        neodym_profile=neodym_profile,
    )
    reported_count = 0 if force else database.store_reported_intelligence_items(
        _reported_item_records(intelligence_items)
    )
    source_count = len({item.source_name for item in raw_items})
    brief = write_json_report(
        intelligence_items,
        json_path,
        source_count=source_count,
        candidate_count=len(events),
    )
    write_slack_markdown(brief, markdown_path)
    return BriefResult(
        source_count=source_count,
        raw_item_count=len(raw_items),
        candidate_count=len(events),
        selected_count=len(intelligence_items),
        skipped_reported_count=len(reported_fingerprints),
        reported_count=reported_count,
        json_path=Path(json_path),
        markdown_path=Path(markdown_path),
    )


def _reported_item_records(items: list[IntelligenceItem]) -> list[dict]:
    return [
        {
            "id": f"report:{item.content_fingerprint}",
            "canonical_title": item.title,
            "category": item.category.value,
            "importance_score": item.importance_score,
            "raw_score": item.raw_score,
            "summary": item.summary,
            "source_links": item.source_links,
            "content_fingerprint": item.content_fingerprint,
            "raw_item_ids": item.deduped_from_ids,
        }
        for item in items
    ]
