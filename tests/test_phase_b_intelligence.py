from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
import sqlite3

from ci_agent.config import Settings
from ci_agent.database import Database
from ci_agent.deduplication import deduplicate_raw_items, normalize_fingerprint
from ci_agent.intelligence import (
    analyze_event,
    classify_event,
    deduplicate_brief_items_with_llm,
    generate_intelligence_items,
)
from ci_agent.llm.client import LLMClient
from ci_agent.llm.prompts import build_analysis_prompt, build_categorization_prompt
from ci_agent.models import IntelligenceCategory, RawSourceItem, SourceType
from ci_agent.pipeline import BriefResult, generate_brief
from ci_agent.ranking import rank_intelligence_items
from ci_agent.report.json_report import write_json_report
from ci_agent.report.slack_markdown import render_slack_markdown, write_slack_markdown
from ci_agent.scoring import CriterionStatus, SCORING_CRITERIA, calculate_importance_score, calculate_raw_score


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


def scoring_assessments(status: str = "strong") -> list[dict]:
    return [
        {
            "id": criterion_id,
            "status": status,
            "evidence": f"Evidence for {criterion_id}.",
            "reason": f"Reason for {criterion_id}.",
        }
        for criterion_id in SCORING_CRITERIA
    ]


def custom_scoring_assessments(statuses: dict[str, str]) -> list[dict]:
    return [
        {
            "id": criterion_id,
            "status": statuses.get(criterion_id, CriterionStatus.PARTIAL.value),
            "evidence": f"Evidence for {criterion_id}.",
            "reason": f"Reason for {criterion_id}.",
        }
        for criterion_id in SCORING_CRITERIA
    ]


def analysis_response(title: str, status: str = "strong") -> dict:
    return {
        "title": title,
        "summary": f"{title} summary.",
        "why_it_matters": f"{title} broader significance.",
        "scoring_assessments": scoring_assessments(status),
    }


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


def test_deterministic_deduplication_merges_shared_entities_and_business_event_synonyms():
    items = [
        raw_item(
            "SpaceX is officially buying Cursor for $60 billion",
            "https://www.theverge.com/spacex-cursor",
            "The Verge AI",
        ),
        raw_item(
            "SpaceX to acquire Cursor for $60B in stock",
            "https://techcrunch.com/spacex-cursor",
            "TechCrunch AI",
        ),
        raw_item(
            "NVIDIA shares Blackwell MLPerf benchmark results",
            "https://developer.nvidia.com/mlperf",
            "NVIDIA Technical Blog",
        ),
    ]

    events = deduplicate_raw_items(items)

    assert len(events) == 2
    cursor_event = next(event for event in events if "Cursor" in event.canonical_title)
    assert len(cursor_event.source_items) == 2
    assert cursor_event.source_links == [
        "https://www.theverge.com/spacex-cursor",
        "https://techcrunch.com/spacex-cursor",
    ]


def test_llm_only_categorization_prompt_contains_allowed_categories_and_no_rules():
    event = deduplicate_raw_items([raw_item("NVIDIA launches new inference platform", "https://nvidia.com/inference")])[0]

    prompt = build_categorization_prompt(event)

    assert "LLM-only" in prompt
    assert "Model Release" in prompt
    assert "Infrastructure" in prompt
    assert "Do not use keyword rules" in prompt
    assert "NVIDIA launches new inference platform" in prompt


def test_analysis_prompt_omits_removed_neodym_action_outputs():
    event = deduplicate_raw_items([raw_item("Anthropic releases Claude update", "https://anthropic.com/claude")])[0]

    prompt = build_analysis_prompt(
        event,
        IntelligenceCategory.MODEL_RELEASE,
        neodym_profile="Neodym prioritizes production-grade AI agents and measurable ROI.",
    )

    assert "Why It Matters to Neodym" not in prompt
    assert "why_it_matters_to_neodym" not in prompt
    assert "Recommended Action" not in prompt
    assert "recommended_action" not in prompt
    assert "production-grade AI agents and measurable ROI" in prompt
    assert "Do not return a numeric importance score" in prompt
    assert "neodym_relevance" in prompt
    assert "missing: No source-grounded evidence supports this criterion." in prompt
    assert "very_weak: Only a bare, indirect, or speculative signal supports this criterion." in prompt
    assert "weak: Some source-grounded relevance, but the evidence or expected impact is limited." in prompt
    assert "partial: Clear source-grounded relevance, but the signal is incomplete, narrow, early, or not yet decisive." in prompt
    assert "good: Solid source-grounded relevance with plausible practical or strategic impact." in prompt
    assert "strong: Clear, important, well-supported relevance with meaningful impact for this criterion." in prompt
    assert "excellent: Exceptional, source-grounded relevance with immediate, strategic, or unusually high impact for this criterion." in prompt
    assert "Do not assign strong or excellent unless the source context directly supports the criterion." in prompt
    assert "ai_developer_relevance" in prompt
    assert "foundation models, agent frameworks, coding tools, AI infrastructure, evaluation systems, and AI developer tooling" in prompt
    assert "Do not assign strong or excellent for market_impact, strategic_business_signal, urgency, or client_roi_potential" in prompt
    assert "generic funding, acquisition, valuation, or business news" in prompt
    assert "large acquisition, funding round, IPO, valuation change, pricing war, market-share shift" in prompt
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
            analysis_response("Anthropic releases Claude update", "strong"),
        ]
    )

    items = generate_intelligence_items(
        events,
        llm_client=llm,
        max_items=5,
        neodym_profile="Neodym evaluates model releases for consulting delivery impact.",
    )

    assert len(items) == 1
    assert items[0].category is IntelligenceCategory.MODEL_RELEASE
    assert items[0].raw_score == 85.0
    assert items[0].importance_score == 8.5
    assert "deterministic weighted criteria" in items[0].score_reason
    assert items[0].source_links == ["https://anthropic.com/claude"]
    assert len(llm.calls) == 2
    assert "consulting delivery impact" in llm.calls[1][1]


def test_analysis_retries_when_llm_returns_incomplete_scoring_assessments():
    event = deduplicate_raw_items([raw_item("OpenAI releases major model", "https://openai.com/model", "OpenAI")])[0]
    llm = SequencedLLMClient(
        [
            {
                "title": "OpenAI releases major model",
                "summary": "OpenAI released a major model.",
                "why_it_matters": "It may shift market expectations.",
                "scoring_assessments": scoring_assessments("strong")[:2],
            },
            analysis_response("OpenAI releases major model", "excellent"),
        ]
    )

    analysis = analyze_event(event, IntelligenceCategory.MODEL_RELEASE, llm)

    assert len(analysis.scoring_assessments) == len(SCORING_CRITERIA)
    assert len(llm.calls) == 2
    assert "failed validation" in llm.calls[1][1]


def test_generate_intelligence_items_skips_event_when_scoring_stays_malformed_after_retry():
    event = deduplicate_raw_items([raw_item("OpenAI releases major model", "https://openai.com/model", "OpenAI")])[0]
    llm = SequencedLLMClient(
        [
            {"category": "Model Release", "confidence": 0.95, "reason": "Major model release."},
            {
                "title": "OpenAI releases major model",
                "summary": "OpenAI released a major model.",
                "why_it_matters": "It may shift market expectations.",
                "scoring_assessments": scoring_assessments("strong")[:2],
            },
            {
                "title": "OpenAI releases major model",
                "summary": "OpenAI released a major model.",
                "why_it_matters": "It may shift market expectations.",
                "scoring_assessments": scoring_assessments("strong")[:2],
            },
        ]
    )

    items = generate_intelligence_items([event], llm_client=llm)

    assert items == []


def test_deterministic_scoring_converts_statuses_to_decimal_importance():
    event = deduplicate_raw_items([raw_item("OpenAI releases major model", "https://openai.com/model", "OpenAI")])[0]
    analysis = analyze_event(
        event,
        IntelligenceCategory.MODEL_RELEASE,
        SequencedLLMClient([analysis_response("OpenAI releases major model", "strong")]),
    )

    raw_score = calculate_raw_score(analysis.scoring_assessments)
    importance_score = calculate_importance_score(raw_score)

    assert raw_score == 85.0
    assert importance_score == 8.5


def test_market_moving_business_event_scores_above_vendor_tutorial_with_status_rules():
    business_event, vendor_tutorial = deduplicate_raw_items(
        [
            raw_item(
                "SpaceX to acquire Cursor for $60B in stock",
                "https://techcrunch.com/spacex-cursor",
                "TechCrunch AI",
                summary="SpaceX is buying AI coding startup Cursor for $60B to compete in enterprise AI.",
            ),
            raw_item(
                "Building AI Agents for AR Glasses with NVIDIA XR AI",
                "https://developer.nvidia.com/xr-ai",
                "NVIDIA Technical Blog",
                summary="NVIDIA explains how developers can build AI agents for AR and XR devices.",
            ),
        ]
    )
    llm = SequencedLLMClient(
        [
            {"category": "Startup Activity", "confidence": 0.95, "reason": "Large AI acquisition."},
            {
                "title": "SpaceX to acquire Cursor for $60B",
                "summary": "SpaceX is buying Cursor for $60B.",
                "why_it_matters": "A very large AI acquisition changes competitive positioning.",
                "scoring_assessments": custom_scoring_assessments(
                    {
                        "ai_developer_relevance": "strong",
                        "market_impact": "excellent",
                        "strategic_business_signal": "excellent",
                        "neodym_relevance": "strong",
                        "client_roi_potential": "good",
                        "agent_automation_relevance": "partial",
                        "technical_novelty": "partial",
                        "urgency": "strong",
                        "source_credibility": "strong",
                    }
                ),
            },
            {"category": "Infrastructure", "confidence": 0.85, "reason": "Vendor technical guide."},
            {
                "title": "Building AI Agents for AR Glasses with NVIDIA XR AI",
                "summary": "NVIDIA explains XR AI agent infrastructure.",
                "why_it_matters": "Useful technical signal, but not a major market-moving update.",
                "scoring_assessments": custom_scoring_assessments(
                    {
                        "market_impact": "partial",
                        "strategic_business_signal": "partial",
                        "neodym_relevance": "strong",
                        "client_roi_potential": "good",
                        "agent_automation_relevance": "strong",
                        "technical_novelty": "good",
                        "urgency": "partial",
                        "source_credibility": "strong",
                    }
                ),
            },
        ]
    )

    items = generate_intelligence_items([business_event, vendor_tutorial], llm_client=llm, max_items=None)

    assert items[0].title == "SpaceX to acquire Cursor for $60B"
    assert items[0].importance_score >= 8.0
    assert items[1].title == "Building AI Agents for AR Glasses with NVIDIA XR AI"
    assert items[1].importance_score < 7.0


def test_ai_developer_ecosystem_item_scores_above_generic_business_news():
    foundation_model_event, generic_funding_event = deduplicate_raw_items(
        [
            raw_item(
                "Anthropic releases Claude Code agent framework for enterprise developers",
                "https://anthropic.com/claude-code-agent-framework",
                "Anthropic",
                summary="Anthropic released an agent framework and coding toolchain for enterprise AI developers.",
            ),
            raw_item(
                "Generic AI startup raises $35M Series B",
                "https://example.com/startup-raises-series-b",
                "Example Business",
                summary="An AI startup raised a normal Series B round without disclosed platform, model, or developer ecosystem impact.",
            ),
        ]
    )
    llm = SequencedLLMClient(
        [
            {"category": "Infrastructure", "confidence": 0.95, "reason": "Agent framework and coding toolchain."},
            {
                "title": "Anthropic releases Claude Code agent framework for enterprise developers",
                "summary": "Anthropic released developer-facing agent framework capabilities.",
                "why_it_matters": "It directly affects AI developers building agentic systems.",
                "scoring_assessments": custom_scoring_assessments(
                    {
                        "ai_developer_relevance": "excellent",
                        "market_impact": "good",
                        "strategic_business_signal": "good",
                        "neodym_relevance": "strong",
                        "client_roi_potential": "good",
                        "agent_automation_relevance": "excellent",
                        "technical_novelty": "strong",
                        "urgency": "good",
                        "source_credibility": "strong",
                    }
                ),
            },
            {"category": "Startup Activity", "confidence": 0.9, "reason": "Routine funding announcement."},
            {
                "title": "Generic AI startup raises $35M Series B",
                "summary": "A startup raised funding without unusual strategic impact.",
                "why_it_matters": "Funding alone is a weaker signal for developer-facing AI priorities.",
                "scoring_assessments": custom_scoring_assessments(
                    {
                        "ai_developer_relevance": "weak",
                        "market_impact": "good",
                        "strategic_business_signal": "good",
                        "neodym_relevance": "partial",
                        "client_roi_potential": "weak",
                        "agent_automation_relevance": "weak",
                        "technical_novelty": "weak",
                        "urgency": "weak",
                        "source_credibility": "strong",
                    }
                ),
            },
        ]
    )

    items = generate_intelligence_items([foundation_model_event, generic_funding_event], llm_client=llm, max_items=None)

    assert items[0].title == "Anthropic releases Claude Code agent framework for enterprise developers"
    assert items[0].importance_score >= 7.0
    assert items[1].title == "Generic AI startup raises $35M Series B"
    assert items[1].importance_score < 7.0


def test_unusually_high_impact_business_story_can_still_rank_highly():
    event = deduplicate_raw_items(
        [
            raw_item(
                "NVIDIA acquires major AI inference platform for $60B",
                "https://example.com/nvidia-inference-acquisition",
                "Example Business",
                summary="NVIDIA acquired a major AI inference platform for $60B, changing distribution and platform control for AI developers.",
            )
        ]
    )[0]
    item = generate_intelligence_items(
        [event],
        llm_client=SequencedLLMClient(
            [
                {"category": "Competitor Update", "confidence": 0.95, "reason": "Major strategic platform acquisition."},
                {
                    "title": "NVIDIA acquires major AI inference platform for $60B",
                    "summary": "NVIDIA acquired an AI inference platform at unusual scale.",
                    "why_it_matters": "The deal changes AI infrastructure platform control and developer distribution.",
                    "scoring_assessments": custom_scoring_assessments(
                        {
                            "ai_developer_relevance": "strong",
                            "market_impact": "excellent",
                            "strategic_business_signal": "excellent",
                            "neodym_relevance": "strong",
                            "client_roi_potential": "good",
                            "agent_automation_relevance": "good",
                            "technical_novelty": "partial",
                            "urgency": "strong",
                            "source_credibility": "strong",
                        }
                    ),
                },
            ]
        ),
        max_items=None,
    )[0]

    assert item.importance_score >= 7.0


def test_category_retries_before_falling_back_to_other():
    event = deduplicate_raw_items([raw_item("Ambiguous AI update", "https://example.com/update")])[0]
    llm = SequencedLLMClient(
        [
            {"category": "Not A Real Category", "confidence": 0.8, "reason": "Invalid."},
            {"category": "Other", "confidence": 0.6, "reason": "Ambiguous but relevant."},
        ]
    )

    category = classify_event(event, llm)

    assert category.category is IntelligenceCategory.OTHER
    assert category.reason == "Ambiguous but relevant."
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
                analysis_response("Minor AI conference update", "weak"),
                {"category": "Model Release", "confidence": 0.95, "reason": "Major model release."},
                analysis_response("OpenAI releases major model", "excellent"),
            ]
        ),
        max_items=5,
    )

    ranked = rank_intelligence_items([low, high])

    assert ranked[0].title == "OpenAI releases major model"
    assert ranked[1].title == "Minor AI conference update"


def test_llm_brief_dedupe_merges_duplicates_but_keeps_unrelated_item_exactly_unchanged():
    raw_items = [
        raw_item("OpenAI launches GPT-5", "https://openai.com/gpt-5", "OpenAI"),
        raw_item("Microsoft details GPT-5 availability", "https://microsoft.com/gpt-5", "Microsoft"),
        raw_item("Anthropic updates Claude Code", "https://anthropic.com/claude-code", "Anthropic"),
    ]
    items = generate_intelligence_items(
        deduplicate_raw_items(raw_items),
        llm_client=SequencedLLMClient(
            [
                {"category": "Model Release", "confidence": 0.95, "reason": "Major model release."},
                analysis_response("OpenAI launches GPT-5", "excellent"),
                {"category": "Model Release", "confidence": 0.92, "reason": "Same model availability news."},
                analysis_response("Microsoft details GPT-5 availability", "strong"),
                {"category": "Infrastructure", "confidence": 0.9, "reason": "Developer tooling update."},
                analysis_response("Anthropic updates Claude Code", "strong"),
            ]
        ),
        max_items=None,
    )
    unchanged = next(item for item in items if item.title == "Anthropic updates Claude Code")
    llm = SequencedLLMClient(
        [
            {
                "groups": [
                    {
                        "item_ids": [
                            next(item.content_fingerprint for item in items if item.title == "OpenAI launches GPT-5"),
                            next(item.content_fingerprint for item in items if item.title == "Microsoft details GPT-5 availability"),
                        ],
                        "title": "OpenAI and Microsoft detail GPT-5 availability",
                        "summary": "OpenAI launched GPT-5 and Microsoft detailed availability.",
                        "reason": "Same GPT-5 launch/update.",
                    },
                    {
                        "item_ids": [unchanged.content_fingerprint],
                        "title": "LLM should not rewrite this unrelated title",
                        "summary": "LLM should not rewrite this unrelated summary.",
                        "reason": "Distinct item.",
                    },
                ]
            }
        ]
    )

    deduped = deduplicate_brief_items_with_llm(items, llm)

    assert len(deduped) == 2
    merged = deduped[0]
    assert merged.title == "OpenAI and Microsoft detail GPT-5 availability"
    assert merged.importance_score == 10.0
    assert merged.source_links == ["https://openai.com/gpt-5", "https://microsoft.com/gpt-5"]
    assert set(merged.deduped_from_ids) >= {
        next(item.id for item in raw_items if item.title == "OpenAI launches GPT-5"),
        next(item.id for item in raw_items if item.title == "Microsoft details GPT-5 availability"),
    }
    assert deduped[1] == unchanged
    assert "If an item does not resemble any other selected item, keep it exactly as-is" in llm.calls[0][1]


def test_llm_brief_dedupe_invalid_response_falls_back_to_original_items():
    items = generate_intelligence_items(
        deduplicate_raw_items([raw_item("OpenAI releases model", "https://openai.com/model")]),
        llm_client=SequencedLLMClient(
            [
                {"category": "Model Release", "confidence": 0.95, "reason": "Major model release."},
                analysis_response("OpenAI releases model", "excellent"),
            ]
        ),
    )

    deduped = deduplicate_brief_items_with_llm(items, SequencedLLMClient([{"groups": []}]))

    assert deduped == items


def test_generate_brief_selects_all_items_with_importance_score_at_least_seven(tmp_path):
    raw_items = [raw_item(f"AI development {index}", f"https://example.com/item-{index}") for index in range(6)]
    statuses = ["excellent", "strong", "good", "partial", "weak", "missing"]
    llm_responses = []
    for item, status in zip(raw_items, statuses, strict=True):
        llm_responses.extend(
            [
                {"category": "Other", "confidence": 0.9, "reason": "Relevant AI development."},
                analysis_response(item.title, status),
            ]
        )

    result = generate_brief(
        raw_items=raw_items,
        settings=Settings(database_path=tmp_path / "intelligence.db"),
        llm_client=SequencedLLMClient(llm_responses),
        json_path=tmp_path / "daily_brief.json",
        markdown_path=tmp_path / "daily_brief.md",
    )

    data = json.loads(result.json_path.read_text())
    assert result.selected_count == 3
    assert result.reported_count == 6
    with sqlite3.connect(tmp_path / "intelligence.db") as conn:
        stored_scores = [
            row[0]
            for row in conn.execute(
                "SELECT importance_score FROM intelligence_items ORDER BY importance_score DESC"
            ).fetchall()
        ]
    assert stored_scores == [10.0, 8.5, 7.0, 5.0, 3.0, 1.0]
    assert data["selected_count"] == 3
    assert [item["importance_score"] for item in data["items"]] == [10.0, 8.5, 7.0]
    markdown = result.markdown_path.read_text()
    assert "AI development 0" in markdown
    assert "AI development 1" in markdown
    assert "AI development 2" in markdown
    assert "AI development 3" not in markdown
    assert "high-signal developments selected" not in markdown
    assert "candidates across" not in markdown


def test_generate_brief_runs_llm_dedupe_only_for_json_markdown_not_database(tmp_path):
    raw_items = [
        raw_item("OpenAI announces enterprise agent platform", "https://openai.com/agents", "OpenAI"),
        raw_item("Azure introduces autonomous workflow suite", "https://microsoft.com/agents", "Microsoft"),
        raw_item("Anthropic updates Claude Code", "https://anthropic.com/claude-code", "Anthropic"),
    ]
    events = deduplicate_raw_items(raw_items)
    fingerprints_by_title = {event.canonical_title: event.content_fingerprint for event in events}
    llm_responses = []
    for item in raw_items:
        llm_responses.extend(
            [
                {"category": "Other", "confidence": 0.9, "reason": "Relevant AI development."},
                analysis_response(item.title, "strong"),
            ]
        )
    llm_responses.append(
        {
            "groups": [
                {
                    "item_ids": [
                        fingerprints_by_title["OpenAI announces enterprise agent platform"],
                        fingerprints_by_title["Azure introduces autonomous workflow suite"],
                    ],
                    "title": "OpenAI and Microsoft advance enterprise agent platforms",
                    "summary": "OpenAI and Microsoft both advanced enterprise agent/workflow platforms.",
                    "reason": "Both describe the same enterprise agent platform trend.",
                },
                {
                    "item_ids": [fingerprints_by_title["Anthropic updates Claude Code"]],
                    "title": "Do not rewrite unrelated singleton",
                    "summary": "Do not rewrite unrelated singleton.",
                    "reason": "Distinct item.",
                },
            ]
        }
    )

    result = generate_brief(
        raw_items=raw_items,
        settings=Settings(database_path=tmp_path / "intelligence.db"),
        llm_client=SequencedLLMClient(llm_responses),
        json_path=tmp_path / "daily_brief.json",
        markdown_path=tmp_path / "daily_brief.md",
    )

    data = json.loads(result.json_path.read_text())
    assert result.reported_count == 3
    assert result.selected_count == 2
    assert data["selected_count"] == 2
    assert [item["title"] for item in data["items"]] == [
        "OpenAI and Microsoft advance enterprise agent platforms",
        "Anthropic updates Claude Code",
    ]
    markdown = result.markdown_path.read_text()
    assert "OpenAI and Microsoft advance enterprise agent platforms" in markdown
    assert "Do not rewrite unrelated singleton" not in markdown
    with sqlite3.connect(tmp_path / "intelligence.db") as conn:
        stored_titles = [
            row[0]
            for row in conn.execute("SELECT canonical_title FROM intelligence_items ORDER BY canonical_title").fetchall()
        ]
        stored_links = [
            json.loads(row[0])
            for row in conn.execute("SELECT source_links_json FROM intelligence_items ORDER BY canonical_title").fetchall()
        ]
        source_link_rows = conn.execute("SELECT COUNT(*) FROM source_item_links").fetchone()[0]
    assert stored_titles == sorted(item.title for item in raw_items)
    assert stored_links == [[item.url] for item in sorted(raw_items, key=lambda item: item.title)]
    assert source_link_rows == 3


def test_generate_brief_falls_back_to_highest_scored_item_when_none_reach_threshold(tmp_path):
    raw_items = [
        raw_item("Minor integration update", "https://example.com/low-0"),
        raw_item("Small model benchmark note", "https://example.com/low-1"),
        raw_item("Routine AI newsletter recap", "https://example.com/low-2"),
    ]
    statuses = ["weak", "partial", "missing"]
    llm_responses = []
    for item, status in zip(raw_items, statuses, strict=True):
        llm_responses.extend(
            [
                {"category": "Other", "confidence": 0.9, "reason": "Lower-signal AI update."},
                analysis_response(item.title, status),
            ]
        )

    result = generate_brief(
        raw_items=raw_items,
        settings=Settings(database_path=tmp_path / "intelligence.db"),
        llm_client=SequencedLLMClient(llm_responses),
        json_path=tmp_path / "daily_brief.json",
        markdown_path=tmp_path / "daily_brief.md",
    )

    data = json.loads(result.json_path.read_text())
    assert result.selected_count == 1
    assert data["selected_count"] == 1
    assert data["items"][0]["title"] == "Small model benchmark note"
    assert data["items"][0]["importance_score"] == 5.0


def test_report_writers_generate_json_and_slack_markdown(tmp_path):
    item = generate_intelligence_items(
        deduplicate_raw_items([raw_item("OpenAI releases major model", "https://openai.com/model", "OpenAI")]),
        llm_client=SequencedLLMClient(
            [
                {"category": "Model Release", "confidence": 0.95, "reason": "Major model release."},
                analysis_response("OpenAI releases major model", "excellent"),
            ]
        ),
    )[0]

    json_path = tmp_path / "daily_brief.json"
    md_path = tmp_path / "daily_brief.md"
    brief = write_json_report([item], json_path, source_count=1, candidate_count=1)
    markdown = write_slack_markdown(brief, md_path)

    data = json.loads(json_path.read_text())
    assert data["selected_count"] == 1
    assert data["items"][0]["importance_score"] == 10.0
    assert data["items"][0]["raw_score"] == 100.0
    assert data["items"][0]["source_links"] == ["https://openai.com/model"]
    assert "why_it_matters_to_neodym" not in data["items"][0]
    assert "recommended_action" not in data["items"][0]
    assert "*Daily AI Competitive Intelligence Brief*" in markdown
    assert "*1. OpenAI releases major model [<https://openai.com/model|OpenAI>]*" in markdown
    assert "[10.0/10]" not in markdown
    assert "• *Category:*" not in markdown
    assert "• *Sources:*" not in markdown
    assert "Why it matters to Neodym" not in md_path.read_text()
    assert "Recommended action" not in md_path.read_text()


def test_slack_markdown_is_presentable_message_without_internal_methodology_or_dividers(tmp_path):
    item = generate_intelligence_items(
        deduplicate_raw_items([raw_item("OpenAI releases major model", "https://openai.com/model", "OpenAI")]),
        llm_client=SequencedLLMClient(
            [
                {"category": "Model Release", "confidence": 0.95, "reason": "Major model release."},
                analysis_response("OpenAI releases major model", "excellent"),
            ]
        ),
    )[0]
    brief = write_json_report([item], tmp_path / "daily_brief.json", source_count=1, candidate_count=1)

    markdown = write_slack_markdown(brief, tmp_path / "daily_brief.md")

    assert "*Methodology:*" not in markdown
    assert brief.methodology not in markdown
    assert "\n---\n" not in markdown
    assert "━━━━━━━━" in markdown
    assert "*1. OpenAI releases major model [<https://openai.com/model|OpenAI>]*" in markdown
    assert "• *Category:*" not in markdown
    assert "• *Sources:*" not in markdown
    assert "[10.0/10]" not in markdown
    assert "• *Recommended action:*" not in markdown
    assert "• *Why it matters to Neodym:*" not in markdown


def test_generate_brief_pipeline_writes_both_outputs(tmp_path):
    db_path = tmp_path / "intelligence.db"
    json_path = tmp_path / "daily_brief.json"
    md_path = tmp_path / "daily_brief.md"
    settings = Settings(database_path=db_path)
    llm = SequencedLLMClient(
        [
            {"category": "Model Release", "confidence": 0.95, "reason": "Major model release."},
            analysis_response("OpenAI releases major model", "excellent"),
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


def test_generate_brief_uses_fetched_at_lookback_when_loading_from_database(tmp_path):
    db_path = tmp_path / "intelligence.db"
    json_path = tmp_path / "daily_brief.json"
    md_path = tmp_path / "daily_brief.md"
    db = Database(db_path)
    now = datetime.now(UTC)
    recent = raw_item("Recent OpenAI model update", "https://openai.com/recent", "OpenAI")
    recent.fetched_at = now - timedelta(hours=1)
    old = raw_item("Old OpenAI model update", "https://openai.com/old", "OpenAI")
    old.fetched_at = now - timedelta(hours=48)
    db.upsert_raw_items([recent, old])
    llm = SequencedLLMClient(
        [
            {"category": "Model Release", "confidence": 0.95, "reason": "Recent model release."},
            analysis_response("Recent OpenAI model update", "excellent"),
        ]
    )

    result = generate_brief(
        settings=Settings(database_path=db_path, brief_lookback_hours=24),
        database=db,
        llm_client=llm,
        json_path=json_path,
        markdown_path=md_path,
        max_items=5,
    )

    assert result.raw_item_count == 1
    assert result.candidate_count == 1
    assert "Recent OpenAI model update" in md_path.read_text()
    assert "Old OpenAI model update" not in md_path.read_text()
