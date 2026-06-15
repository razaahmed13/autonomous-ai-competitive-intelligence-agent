from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .config import Settings, load_neodym_profile
from .database import Database
from .deduplication import deduplicate_raw_items
from .fetchers.rss import fetch_rss_source
from .intelligence import generate_intelligence_items
from .llm.client import LLMClient, build_llm_client
from .models import RawSourceItem, SourceConfig, SourceType
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
    failed_sources: list[SourceFailure] = field(default_factory=list)


@dataclass(frozen=True)
class BriefResult:
    source_count: int
    raw_item_count: int
    candidate_count: int
    selected_count: int
    json_path: Path
    markdown_path: Path


def default_fetcher(source: SourceConfig, settings: Settings) -> list[RawSourceItem]:
    if source.type is SourceType.RSS:
        return fetch_rss_source(source, settings)
    raise ValueError(f"Unsupported source type: {source.type}")


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

    all_items: list[RawSourceItem] = []
    failures: list[SourceFailure] = []
    for source in sources:
        try:
            all_items.extend(fetcher(source, settings))
        except Exception as exc:
            failures.append(SourceFailure(source_name=source.name, error=str(exc)))

    inserted = database.upsert_raw_items(all_items)
    return CollectionResult(
        source_count=len(sources),
        raw_item_count=len(all_items),
        inserted_count=inserted,
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
    max_items: int = 8,
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
    intelligence_items = generate_intelligence_items(
        events,
        llm_client=llm_client,
        max_items=max_items,
        neodym_profile=neodym_profile,
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
        json_path=Path(json_path),
        markdown_path=Path(markdown_path),
    )
