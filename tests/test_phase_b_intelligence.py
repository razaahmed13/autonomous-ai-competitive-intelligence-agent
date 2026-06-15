from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ci_agent.config import Settings
from ci_agent.database import Database
from ci_agent.deduplication import deduplicate_raw_items, normalize_fingerprint
from ci_agent.intelligence import analyze_event, classify_event, generate_intelligence_items
from ci_agent.llm.client import LLMClient
from ci_agent.llm.prompts import build_analysis_prompt, build_categorization_prompt
from ci_agent.models import IntelligenceCategory, RawSourceItem, SourceType
from ci_agent.pipeline import BriefResult, generate_brief
from ci_agent.ranking import rank_intelligence_items
from ci_agent.report.json_report import write_json_report
from ci_agent.report.slack_markdown import render_slack_markdown, write_slack_markdown
from ci_agent.scoring import SCORING_CRITERIA, calculate_importance_score, calculate_raw_score


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


def analysis_response(title: str, status: str = "strong") -> dict:
    return {
        "title": title,
        "summary": f"{title} summary.",
        "why_it_matters": f"{title} broader significance.",
        "why_it_matters_to_neodym": f"{title} matters to Neodym.",
        "recommended_action": f"Review {title}.",
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

    prompt = build_analysis_prompt(
        event,
        IntelligenceCategory.MODEL_RELEASE,
        neodym_profile="Neodym prioritizes production-grade AI agents and measurable ROI.",
    )

    assert "Why It Matters to Neodym" in prompt
    assert "production-grade AI agents and measurable ROI" in prompt
    assert "Do not return a numeric importance score" in prompt
    assert "neodym_relevance" in prompt
    assert "missing: No source-grounded evidence supports this criterion." in prompt
    assert "Do not assign strong or excellent unless the source context directly supports the criterion." in prompt
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
                "why_it_matters_to_neodym": "Neodym should evaluate roadmap implications.",
                "recommended_action": "Run a competitive capability review.",
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
                "why_it_matters_to_neodym": "Neodym should evaluate roadmap implications.",
                "recommended_action": "Run a competitive capability review.",
                "scoring_assessments": scoring_assessments("strong")[:2],
            },
            {
                "title": "OpenAI releases major model",
                "summary": "OpenAI released a major model.",
                "why_it_matters": "It may shift market expectations.",
                "why_it_matters_to_neodym": "Neodym should evaluate roadmap implications.",
                "recommended_action": "Run a competitive capability review.",
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
    assert "*Daily AI Competitive Intelligence Brief*" in markdown
    assert "*1. [10.0/10] OpenAI releases major model*" in markdown
    assert "*Why it matters to Neodym:* OpenAI releases major model matters to Neodym." in md_path.read_text()


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
