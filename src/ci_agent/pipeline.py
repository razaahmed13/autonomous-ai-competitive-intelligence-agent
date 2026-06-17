from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Callable

from .config import Settings, load_neodym_profile
from .database import Database
from .deduplication import deduplicate_raw_items
from .fetchers.rss import fetch_rss_source
from .fetchers.web import fetch_web_source
from .intelligence import deduplicate_brief_items_with_llm, generate_intelligence_items
from .llm.client import LLMClient, build_llm_client
from .models import IntelligenceItem, RawSourceItem, SourceConfig, SourceType
from .report.json_report import write_json_report
from .report.slack_markdown import write_slack_markdown
from .sources import DEFAULT_SOURCES

Fetcher = Callable[[SourceConfig, Settings], list[RawSourceItem]]
MIN_DAILY_BRIEF_IMPORTANCE_SCORE = 7.0
SOURCE_DIVERSITY_EXCEPTION_IMPORTANCE_SCORE = 8.5


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
    if source.type is SourceType.WEB:
        return fetch_web_source(source, settings)
    raise ValueError(f"Unsupported source type: {source.type}")


def filter_collectable_items_by_published_at(
    items: list[RawSourceItem],
    *,
    now: datetime | None = None,
    max_age_hours: int = 24,
) -> list[RawSourceItem]:
    """Keep missing-date items plus published items inside the freshness window."""
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
    max_items: int | None = None,
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
    analyzed_items = generate_intelligence_items(
        eligible_events,
        llm_client=llm_client,
        max_items=None,
        neodym_profile=neodym_profile,
    )
    intelligence_items = _select_daily_brief_items(analyzed_items)
    reported_count = 0 if force else database.store_reported_intelligence_items(
        _reported_item_records(analyzed_items)
    )
    brief_items = deduplicate_brief_items_with_llm(intelligence_items, llm_client)
    source_count = len({item.source_name for item in raw_items})
    brief = write_json_report(
        brief_items,
        json_path,
        source_count=source_count,
        candidate_count=len(events),
    )
    write_slack_markdown(brief, markdown_path)
    return BriefResult(
        source_count=source_count,
        raw_item_count=len(raw_items),
        candidate_count=len(events),
        selected_count=len(brief_items),
        skipped_reported_count=len(reported_fingerprints),
        reported_count=reported_count,
        json_path=Path(json_path),
        markdown_path=Path(markdown_path),
    )


def _select_daily_brief_items(items: list[IntelligenceItem]) -> list[IntelligenceItem]:
    if not items:
        return []
    threshold_items = [item for item in items if item.importance_score >= MIN_DAILY_BRIEF_IMPORTANCE_SCORE]
    if threshold_items:
        return _diversify_daily_brief_items_by_source(threshold_items)
    return items[:1]


def _diversify_daily_brief_items_by_source(items: list[IntelligenceItem]) -> list[IntelligenceItem]:
    """Keep one selected brief item per source unless an item is very high-signal.

    This is a presentation-only selection step applied after scoring/thresholding and
    before LLM brief dedupe. It intentionally does not affect database persistence.
    """
    selected: list[IntelligenceItem] = []
    represented_sources: set[str] = set()

    for item in items:
        source_key = _primary_source_key(item)
        is_source_represented = source_key in represented_sources
        is_high_score_exception = item.importance_score >= SOURCE_DIVERSITY_EXCEPTION_IMPORTANCE_SCORE
        if not is_source_represented or is_high_score_exception:
            selected.append(item)
            represented_sources.add(source_key)

    return selected


def _primary_source_key(item: IntelligenceItem) -> str:
    if item.source_names:
        return item.source_names[0].strip().lower()
    if item.source_links:
        return item.source_links[0].strip().lower()
    return item.content_fingerprint


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
