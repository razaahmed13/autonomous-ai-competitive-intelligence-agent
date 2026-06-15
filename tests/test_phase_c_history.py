from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime

from ci_agent.config import Settings
from ci_agent.database import Database
from ci_agent.deduplication import deduplicate_raw_items
from ci_agent.llm.client import LLMClient
from ci_agent.models import RawSourceItem, SourceType
from ci_agent.pipeline import generate_brief
from ci_agent.scoring import SCORING_CRITERIA


class SequencedLLMClient(LLMClient):
    def __init__(self, responses: list[dict]):
        self.responses = responses
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict:
        self.calls.append((system_prompt, user_prompt))
        if not self.responses:
            raise AssertionError("No fake LLM response left")
        return self.responses.pop(0)


def raw_item(title: str, url: str, source: str = "Example") -> RawSourceItem:
    return RawSourceItem(
        source_name=source,
        source_type=SourceType.RSS,
        title=title,
        url=url,
        published_at=datetime(2026, 6, 15, tzinfo=UTC),
        raw_summary=f"{title} summary",
        content=f"{title} content",
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


def model_release_response(reason: str = "Major model release.") -> dict:
    return {"category": "Model Release", "confidence": 0.95, "reason": reason}


def test_database_stores_reported_intelligence_fingerprints(tmp_path):
    db = Database(tmp_path / "intelligence.db")
    item = raw_item("OpenAI releases major model", "https://openai.com/model", "OpenAI")
    event = deduplicate_raw_items([item])[0]

    assert db.has_reported_fingerprint(event.content_fingerprint) is False

    stored = db.store_reported_intelligence_items(
        [
            {
                "id": "report:one",
                "canonical_title": event.canonical_title,
                "category": "Model Release",
                "importance_score": 8.5,
                "raw_score": 85.0,
                "summary": "summary",
                "source_links": event.source_links,
                "content_fingerprint": event.content_fingerprint,
                "raw_item_ids": [item.id],
            }
        ]
    )

    assert stored == 1
    assert db.has_reported_fingerprint(event.content_fingerprint) is True
    assert db.store_reported_intelligence_items(
        [
            {
                "id": "report:duplicate",
                "canonical_title": event.canonical_title,
                "category": "Model Release",
                "importance_score": 8.5,
                "raw_score": 85.0,
                "summary": "summary",
                "source_links": event.source_links,
                "content_fingerprint": event.content_fingerprint,
                "raw_item_ids": [item.id],
            }
        ]
    ) == 0


def test_generate_brief_skips_already_reported_fingerprints_on_repeated_runs(tmp_path):
    db_path = tmp_path / "intelligence.db"
    json_path = tmp_path / "daily_brief.json"
    md_path = tmp_path / "daily_brief.md"
    raw = [raw_item("OpenAI releases major model", "https://openai.com/model", "OpenAI")]
    db = Database(db_path)
    settings = Settings(database_path=db_path)

    first_llm = SequencedLLMClient([model_release_response(), analysis_response("OpenAI releases major model", "excellent")])
    first = generate_brief(
        raw_items=raw,
        settings=settings,
        database=db,
        llm_client=first_llm,
        json_path=json_path,
        markdown_path=md_path,
        max_items=5,
    )

    assert first.selected_count == 1
    assert first.reported_count == 1
    assert len(first_llm.calls) == 2

    second_llm = SequencedLLMClient([])
    second = generate_brief(
        raw_items=raw,
        settings=settings,
        database=db,
        llm_client=second_llm,
        json_path=json_path,
        markdown_path=md_path,
        max_items=5,
    )

    assert second.candidate_count == 1
    assert second.skipped_reported_count == 1
    assert second.selected_count == 0
    assert second.reported_count == 0
    assert second_llm.calls == []
    data = json.loads(json_path.read_text())
    assert data["selected_count"] == 0
    assert data["items"] == []


def test_generate_brief_force_regenerates_already_reported_fingerprints(tmp_path):
    db_path = tmp_path / "intelligence.db"
    raw = [raw_item("OpenAI releases major model", "https://openai.com/model", "OpenAI")]
    db = Database(db_path)
    settings = Settings(database_path=db_path)

    first_llm = SequencedLLMClient([model_release_response(), analysis_response("OpenAI releases major model", "excellent")])
    generate_brief(raw_items=raw, settings=settings, database=db, llm_client=first_llm, json_path=tmp_path / "first.json", markdown_path=tmp_path / "first.md")

    forced_llm = SequencedLLMClient([model_release_response("Forced regeneration."), analysis_response("OpenAI releases major model", "strong")])
    forced = generate_brief(
        raw_items=raw,
        settings=settings,
        database=db,
        llm_client=forced_llm,
        json_path=tmp_path / "forced.json",
        markdown_path=tmp_path / "forced.md",
        force=True,
    )

    assert forced.skipped_reported_count == 0
    assert forced.selected_count == 1
    assert forced.reported_count == 0
    assert len(forced_llm.calls) == 2


def test_cli_exposes_force_option():
    result = subprocess.run(
        [sys.executable, "run.py", "--help"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "--force" in result.stdout
    assert "already-reported" in result.stdout
