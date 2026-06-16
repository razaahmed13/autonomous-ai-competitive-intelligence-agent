from __future__ import annotations

from datetime import UTC, datetime

from ci_agent.config import Settings
from ci_agent.fetchers.web import parse_huggingface_daily_papers_page
from ci_agent.models import SourceConfig, SourceType
from ci_agent.pipeline import default_fetcher


def test_parse_huggingface_daily_papers_page_extracts_svelte_payload():
    source = SourceConfig(
        name="Hugging Face Daily Papers",
        type=SourceType.WEB,
        url="https://huggingface.co/papers",
    )
    html = '''
    <div class="SVELTE_HYDRATER contents" data-target="DailyPapers"
      data-props="{&quot;dailyPapers&quot;:[{&quot;paper&quot;:{&quot;id&quot;:&quot;2606.14777&quot;,&quot;title&quot;:&quot;JoyAI-VL-Interaction&quot;,&quot;summary&quot;:&quot;A real-time vision-language model.&quot;,&quot;submittedOnDailyAt&quot;:&quot;2026-06-16T00:00:00.000Z&quot;,&quot;authors&quot;:[{&quot;name&quot;:&quot;Dingyu Yao&quot;},{&quot;name&quot;:&quot;Junhao Zhou&quot;}]}}]}" />
    '''

    items = parse_huggingface_daily_papers_page(html, source, max_items=5)

    assert len(items) == 1
    assert items[0].source_name == "Hugging Face Daily Papers"
    assert items[0].source_type is SourceType.WEB
    assert items[0].title == "JoyAI-VL-Interaction"
    assert items[0].url == "https://huggingface.co/papers/2606.14777"
    assert items[0].published_at == datetime(2026, 6, 16, tzinfo=UTC)
    assert items[0].author == "Dingyu Yao, Junhao Zhou"
    assert items[0].raw_summary == "A real-time vision-language model."


def test_default_fetcher_supports_huggingface_daily_papers_web_source(monkeypatch):
    source = SourceConfig(
        name="Hugging Face Daily Papers",
        type=SourceType.WEB,
        url="https://huggingface.co/papers",
    )
    called = {}

    def fake_fetch_web_source(source_config: SourceConfig, settings: Settings):
        called["source"] = source_config
        called["settings"] = settings
        return []

    monkeypatch.setattr("ci_agent.pipeline.fetch_web_source", fake_fetch_web_source)

    result = default_fetcher(source, Settings(max_items_per_source=3))

    assert result == []
    assert called["source"] == source
    assert called["settings"].max_items_per_source == 3
