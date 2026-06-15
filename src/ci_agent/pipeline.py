from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .config import Settings
from .database import Database
from .fetchers.rss import fetch_rss_source
from .models import RawSourceItem, SourceConfig, SourceType
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
