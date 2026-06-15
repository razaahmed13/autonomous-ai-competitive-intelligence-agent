from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ci_agent.config import Settings, load_neodym_profile
from ci_agent.database import Database
from ci_agent.fetchers.rss import parse_rss_feed
from ci_agent.models import RawSourceItem, SourceConfig, SourceType
from ci_agent.pipeline import CollectionResult, collect_sources
from ci_agent.sources import DEFAULT_SOURCES


def test_settings_uses_defaults_and_env_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "custom.db"))
    monkeypatch.setenv("NEODYM_PROFILE_PATH", str(tmp_path / "profile.md"))
    monkeypatch.setenv("MAX_ITEMS_PER_SOURCE", "3")
    monkeypatch.setenv("BRIEF_LOOKBACK_HOURS", "12")
    monkeypatch.setenv("USER_AGENT", "test-agent")

    settings = Settings.from_env()

    assert settings.database_path == tmp_path / "custom.db"
    assert settings.neodym_profile_path == tmp_path / "profile.md"
    assert settings.max_items_per_source == 3
    assert settings.brief_lookback_hours == 12
    assert settings.user_agent == "test-agent"
    assert settings.slack_channel == "#industry-trends"


def test_load_neodym_profile_reads_configured_markdown(tmp_path):
    profile_path = tmp_path / "neodym.md"
    profile_path.write_text("Neodym profile for testing.", encoding="utf-8")

    assert load_neodym_profile(profile_path) == "Neodym profile for testing."
    assert "AI consulting" in load_neodym_profile(tmp_path / "missing.md")


def test_raw_source_item_requires_source_link_and_stable_id():
    item = RawSourceItem(
        source_name="Example Source",
        source_type=SourceType.RSS,
        title="  Example AI Update  ",
        url="https://example.com/post?utm_source=x",
        published_at=datetime(2026, 6, 15, tzinfo=UTC),
        raw_summary="Summary",
        content="Longer content",
    )

    assert item.title == "Example AI Update"
    assert item.url == "https://example.com/post?utm_source=x"
    assert item.id
    assert item.content_hash

    with pytest.raises(ValueError):
        RawSourceItem(
            source_name="Example Source",
            source_type=SourceType.RSS,
            title="No URL",
            url="",
        )


def test_source_config_validates_required_fields():
    source = SourceConfig(
        name="Hugging Face Blog",
        type=SourceType.RSS,
        url="https://huggingface.co/blog/feed.xml",
    )

    assert source.name == "Hugging Face Blog"
    assert source.type is SourceType.RSS

    with pytest.raises(ValueError):
        SourceConfig(name="", type=SourceType.RSS, url="https://example.com/feed.xml")


def test_database_initializes_tables_and_upserts_raw_items(tmp_path):
    db = Database(tmp_path / "intelligence.db")
    db.initialize()
    item = RawSourceItem(
        source_name="Example",
        source_type=SourceType.RSS,
        title="Example item",
        url="https://example.com/item",
        published_at=datetime(2026, 6, 15, tzinfo=UTC),
        raw_summary="summary",
        content="content",
    )

    inserted_first = db.upsert_raw_items([item])
    inserted_second = db.upsert_raw_items([item])
    stored = db.list_raw_items(limit=10)

    assert inserted_first == 1
    assert inserted_second == 0
    assert len(stored) == 1
    assert stored[0].title == "Example item"
    assert stored[0].url == "https://example.com/item"


def test_database_lists_only_recent_raw_items_by_fetched_at(tmp_path):
    db = Database(tmp_path / "intelligence.db")
    now = datetime.now(UTC)
    recent = RawSourceItem(
        source_name="Example",
        source_type=SourceType.RSS,
        title="Recent item",
        url="https://example.com/recent",
        fetched_at=now - timedelta(hours=2),
    )
    old = RawSourceItem(
        source_name="Example",
        source_type=SourceType.RSS,
        title="Old item",
        url="https://example.com/old",
        fetched_at=now - timedelta(hours=30),
    )

    db.upsert_raw_items([recent, old])
    stored = db.list_recent_raw_items(hours=24)

    assert [item.title for item in stored] == ["Recent item"]


def test_rss_parser_normalizes_feed_entries():
    xml = """<?xml version="1.0" encoding="UTF-8" ?>
    <rss version="2.0">
      <channel>
        <title>Example AI Feed</title>
        <item>
          <title>First AI update</title>
          <link>https://example.com/first</link>
          <description><![CDATA[Short summary]]></description>
          <pubDate>Mon, 15 Jun 2026 10:00:00 GMT</pubDate>
        </item>
        <item>
          <title>Missing link should be skipped</title>
          <description>No link</description>
        </item>
      </channel>
    </rss>
    """
    source = SourceConfig(name="Example Feed", type=SourceType.RSS, url="https://example.com/rss.xml")

    items = parse_rss_feed(xml, source, max_items=5)

    assert len(items) == 1
    assert items[0].source_name == "Example Feed"
    assert items[0].title == "First AI update"
    assert items[0].url == "https://example.com/first"
    assert items[0].raw_summary == "Short summary"
    assert items[0].published_at is not None


def test_default_sources_include_multiple_independent_rss_sources():
    rss_sources = [source for source in DEFAULT_SOURCES if source.type is SourceType.RSS]

    assert len(DEFAULT_SOURCES) >= 5
    assert len({source.name for source in DEFAULT_SOURCES}) == len(DEFAULT_SOURCES)
    assert len(rss_sources) >= 5


def test_collect_sources_orchestrates_fetch_and_storage(tmp_path):
    source = SourceConfig(name="Example Feed", type=SourceType.RSS, url="https://example.com/rss.xml")
    item = RawSourceItem(
        source_name="Example Feed",
        source_type=SourceType.RSS,
        title="Pipeline item",
        url="https://example.com/pipeline-item",
        raw_summary="summary",
    )

    def fake_fetcher(source_config: SourceConfig, settings: Settings):
        assert source_config == source
        assert settings.max_items_per_source == 10
        return [item]

    db = Database(tmp_path / "pipeline.db")
    result = collect_sources(
        sources=[source],
        settings=Settings(database_path=tmp_path / "pipeline.db"),
        database=db,
        fetcher=fake_fetcher,
    )

    assert isinstance(result, CollectionResult)
    assert result.source_count == 1
    assert result.raw_item_count == 1
    assert result.inserted_count == 1
    assert result.failed_sources == []
    assert len(db.list_raw_items()) == 1
