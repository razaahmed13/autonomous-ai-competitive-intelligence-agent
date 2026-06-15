from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from ci_agent.config import Settings
from ci_agent.deduplication import deduplicate_raw_items, normalize_fingerprint
from ci_agent.intelligence import generate_intelligence_items
from ci_agent.llm.client import LLMClient
from ci_agent.llm.prompts import build_analysis_prompt, build_categorization_prompt
from ci_agent.models import IntelligenceCategory, RawSourceItem, SourceType
from ci_agent.pipeline import BriefResult, generate_brief
from ci_agent.ranking import rank_intelligence_items
from ci_agent.report.json_report import write_json_report
from ci_agent.report.slack_markdown import render_slack_markdown, write_slack_markdown


class SequencedLLMClient(LLMClient):
    def __init__(self, responses: list[dict]):
        self.responses = responses
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict:
        self.calls.append((system_prompt, user_prompt))
        if not self.responses:
            raise AssertionError("No fake LLM response left")
        return self.responses.pop(0)


def raw_item(title: str, url: str, source: str = "Example", summary: str = "summary") -> RawSourceItem:
    return RawSourceItem(
        source_name=source,
        source_type=SourceType.RSS,
        title=title,
        url=url,
        published_at=datetime(2026, 6, 15, tzinfo=UTC),
        raw_summary=summary,
        content=summary,
    )


def test_deterministic_deduplication_merges_similar_titles_and_preserves_sources():
    items = [
        raw_item("OpenAI releases GPT-5 for developers", "https://openai.com/gpt-5", "OpenAI"),
        raw_item("Microsoft discusses OpenAI GPT-5 release for developers", "https://microsoft.com/openai-gpt-5", "Microsoft"),
        raw_item("Anthropic launches Claude update", "https://anthropic.com/claude", "Anthropic"),
    ]

    events = deduplicate_raw_items(items)

    assert len(events) == 2
    merged = next(event for event in events if "GPT" in event.canonical_title)
    assert len(merged.source_items) == 2
    assert merged.source_links == ["https://openai.com/gpt-5", "https://microsoft.com/openai-gpt-5"]
    assert normalize_fingerprint("OpenAI releases GPT-5!") == normalize_fingerprint("openai releases gpt 5")


def test_llm_only_categorization_prompt_contains_allowed_categories_and_no_rules():
    event = deduplicate_raw_items([raw_item("NVIDIA launches new inference platform", "https://nvidia.com/inference")])[0]

    prompt = build_categorization_prompt(event)

    assert "LLM-only" in prompt
    assert "Model Release" in prompt
    assert "Infrastructure" in prompt
    assert "Do not use keyword rules" in prompt
    assert "NVIDIA launches new inference platform" in prompt


def test_analysis_prompt_requires_grounded_neodym_specific_output():
    event = deduplicate_raw_items([raw_item("Anthropic releases Claude update", "https://anthropic.com/claude")])[0]

    prompt = build_analysis_prompt(event, IntelligenceCategory.MODEL_RELEASE)

    assert "Why It Matters to Neodym" in prompt
    assert "Recommended Action" in prompt
    assert "Do not invent facts" in prompt
    assert "https://anthropic.com/claude" in prompt


def test_generate_intelligence_items_uses_llm_categorization_and_analysis():
    events = deduplicate_raw_items([raw_item("Anthropic releases Claude update", "https://anthropic.com/claude", "Anthropic")])
    llm = SequencedLLMClient(
        [
            {
                "category": "Model Release",
                "confidence": 0.94,
                "reason": "The event is a model capability release.",
            },
            {
                "title": "Anthropic releases Claude update",
                "importance_score": 8,
                "score_reason": "Relevant competitor model capability movement.",
                "summary": "Anthropic released an update to Claude.",
                "why_it_matters": "Major model updates shift expectations for AI products.",
                "why_it_matters_to_neodym": "Neodym should compare the capabilities against its agent/product roadmap.",
                "recommended_action": "Review the release and identify product implications.",
            },
        ]
    )

    items = generate_intelligence_items(events, llm_client=llm, max_items=5)

    assert len(items) == 1
    assert items[0].category is IntelligenceCategory.MODEL_RELEASE
    assert items[0].importance_score == 8
    assert items[0].source_links == ["https://anthropic.com/claude"]
    assert len(llm.calls) == 2


def test_ranking_orders_by_importance_score_descending():
    low, high = generate_intelligence_items(
        deduplicate_raw_items([
            raw_item("Minor AI conference update", "https://example.com/conference"),
            raw_item("OpenAI releases major model", "https://openai.com/model"),
        ]),
        llm_client=SequencedLLMClient(
            [
                {"category": "Other", "confidence": 0.8, "reason": "Conference item."},
                {
                    "title": "Minor AI conference update",
                    "importance_score": 3,
                    "score_reason": "Low strategic relevance.",
                    "summary": "A conference update was announced.",
                    "why_it_matters": "It is useful context only.",
                    "why_it_matters_to_neodym": "Low immediate relevance.",
                    "recommended_action": "No immediate action.",
                },
                {"category": "Model Release", "confidence": 0.95, "reason": "Major model release."},
                {
                    "title": "OpenAI releases major model",
                    "importance_score": 9,
                    "score_reason": "High competitive relevance.",
                    "summary": "OpenAI released a major model.",
                    "why_it_matters": "It may shift market expectations.",
                    "why_it_matters_to_neodym": "Neodym should evaluate capability gaps and opportunities.",
                    "recommended_action": "Run a competitive capability review.",
                },
            ]
        ),
        max_items=5,
    )

    ranked = rank_intelligence_items([low, high])

    assert ranked[0].title == "OpenAI releases major model"
    assert ranked[1].title == "Minor AI conference update"


def test_report_writers_generate_json_and_slack_markdown(tmp_path):
    item = generate_intelligence_items(
        deduplicate_raw_items([raw_item("OpenAI releases major model", "https://openai.com/model", "OpenAI")]),
        llm_client=SequencedLLMClient(
            [
                {"category": "Model Release", "confidence": 0.95, "reason": "Major model release."},
                {
                    "title": "OpenAI releases major model",
                    "importance_score": 9,
                    "score_reason": "High competitive relevance.",
                    "summary": "OpenAI released a major model.",
                    "why_it_matters": "It may shift market expectations.",
                    "why_it_matters_to_neodym": "Neodym should evaluate roadmap implications.",
                    "recommended_action": "Run a competitive capability review.",
                },
            ]
        ),
    )[0]

    json_path = tmp_path / "daily_brief.json"
    md_path = tmp_path / "daily_brief.md"
    brief = write_json_report([item], json_path, source_count=1, candidate_count=1)
    markdown = write_slack_markdown(brief, md_path)

    data = json.loads(json_path.read_text())
    assert data["selected_count"] == 1
    assert data["items"][0]["source_links"] == ["https://openai.com/model"]
    assert "*Daily AI Competitive Intelligence Brief*" in markdown
    assert "*Why it matters to Neodym:* Neodym should evaluate roadmap implications." in md_path.read_text()


def test_generate_brief_pipeline_writes_both_outputs(tmp_path):
    db_path = tmp_path / "intelligence.db"
    json_path = tmp_path / "daily_brief.json"
    md_path = tmp_path / "daily_brief.md"
    settings = Settings(database_path=db_path)
    llm = SequencedLLMClient(
        [
            {"category": "Model Release", "confidence": 0.95, "reason": "Major model release."},
            {
                "title": "OpenAI releases major model",
                "importance_score": 9,
                "score_reason": "High competitive relevance.",
                "summary": "OpenAI released a major model.",
                "why_it_matters": "It may shift market expectations.",
                "why_it_matters_to_neodym": "Neodym should evaluate roadmap implications.",
                "recommended_action": "Run a competitive capability review.",
            },
        ]
    )

    result = generate_brief(
        raw_items=[raw_item("OpenAI releases major model", "https://openai.com/model", "OpenAI")],
        settings=settings,
        llm_client=llm,
        json_path=json_path,
        markdown_path=md_path,
        max_items=5,
    )

    assert isinstance(result, BriefResult)
    assert result.candidate_count == 1
    assert result.selected_count == 1
    assert json_path.exists()
    assert md_path.exists()
    assert "OpenAI releases major model" in md_path.read_text()
