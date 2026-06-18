from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ci_agent.config import Settings
from ci_agent.database import Database
from ci_agent.models import RawSourceItem, SourceConfig, SourceType
from ci_agent.pipeline import collect_sources, filter_collectable_items_by_published_at
from ci_agent.sources import DEFAULT_SOURCES


REQUIRED_PHASE_E_SOURCE_NAMES = [
    "OpenAI Blog",
    "Anthropic News",
    "Google DeepMind Blog",
    "Meta AI Blog",
    "Microsoft AI Blog",
    "NVIDIA Technical Blog",
    "Hugging Face Blog",
    "AWS Machine Learning Blog",
    "Mistral AI News",
    "Cohere Blog",
    "LlamaIndex Blog",
    "CrewAI Blog",
    "Papers with Code",
    "MIT CSAIL News",
    "TechCrunch AI",
    "VentureBeat AI",
    "The Verge AI",
    "Ars Technica AI",
    "WIRED AI",
    "The Decoder",
    "a16z AI",
]


def _raw_item(title: str, *, published_at: datetime | None) -> RawSourceItem:
    slug = title.lower().replace(" ", "-")
    return RawSourceItem(
        source_name="Example Feed",
        source_type=SourceType.RSS,
        title=title,
        url=f"https://example.com/{slug}",
        published_at=published_at,
    )


def test_collection_filter_skips_stale_published_items_and_keeps_missing_dates():
    now = datetime(2026, 6, 15, 12, tzinfo=UTC)
    fresh = _raw_item("Fresh item", published_at=now - timedelta(hours=23, minutes=59))
    stale = _raw_item("Stale item", published_at=now - timedelta(hours=24, minutes=1))
    missing_date = _raw_item("Missing date item", published_at=None)

    filtered = filter_collectable_items_by_published_at([fresh, stale, missing_date], now=now)

    assert [item.title for item in filtered] == ["Fresh item", "Missing date item"]


def test_collection_filter_treats_naive_published_at_as_utc():
    now = datetime(2026, 6, 15, 12, tzinfo=UTC)
    naive_fresh = _raw_item("Naive fresh", published_at=datetime(2026, 6, 15, 11))
    naive_stale = _raw_item("Naive stale", published_at=datetime(2026, 6, 14, 10))

    filtered = filter_collectable_items_by_published_at([naive_fresh, naive_stale], now=now)

    assert [item.title for item in filtered] == ["Naive fresh"]


def test_collect_sources_filters_stale_published_items_before_db_insert(tmp_path):
    now = datetime.now(UTC)
    source = SourceConfig(name="Example Feed", type=SourceType.RSS, url="https://example.com/rss.xml")
    fresh = _raw_item("Fresh pipeline item", published_at=now - timedelta(hours=2))
    stale = _raw_item("Stale pipeline item", published_at=now - timedelta(days=2))
    missing_date = _raw_item("Missing date pipeline item", published_at=None)

    def fake_fetcher(source_config: SourceConfig, settings: Settings):
        return [fresh, stale, missing_date]

    db = Database(tmp_path / "pipeline.db")
    result = collect_sources(
        sources=[source],
        settings=Settings(database_path=tmp_path / "pipeline.db"),
        database=db,
        fetcher=fake_fetcher,
    )

    assert result.raw_item_count == 2
    assert result.skipped_stale_count == 1
    assert [item.title for item in db.list_raw_items(limit=10)] == [
        "Missing date pipeline item",
        "Fresh pipeline item",
    ]


def test_default_sources_are_exact_refined_batch_of_21():
    source_by_name = {source.name: source for source in DEFAULT_SOURCES}

    assert [source.name for source in DEFAULT_SOURCES] == REQUIRED_PHASE_E_SOURCE_NAMES
    assert len(DEFAULT_SOURCES) == 21
    assert len({source.name for source in DEFAULT_SOURCES}) == 21
    assert len({source.url for source in DEFAULT_SOURCES}) == 21
    assert all(source.url.startswith("https://") for source in DEFAULT_SOURCES)
    assert source_by_name["AWS Machine Learning Blog"].type is SourceType.RSS
    assert source_by_name["AWS Machine Learning Blog"].url == "https://aws.amazon.com/blogs/machine-learning/feed/"
    assert "Hugging Face Daily Papers" not in source_by_name
    assert "LangChain Blog" not in source_by_name
    assert "Zapier AI Blog" not in source_by_name
    assert "n8n Blog" not in source_by_name
    assert "Berkeley BAIR Blog" not in source_by_name
    assert "Stanford HAI Blog" not in source_by_name
    assert "arXiv cs.AI" not in source_by_name
    assert "arXiv cs.LG" not in source_by_name
    assert "arXiv cs.CL" not in source_by_name
