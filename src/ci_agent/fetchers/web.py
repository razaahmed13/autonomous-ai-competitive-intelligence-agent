from __future__ import annotations

from datetime import datetime
from html import unescape
import json
import re

import httpx

from ..config import Settings
from ..models import RawSourceItem, SourceConfig, SourceType


DAILY_PAPERS_BASE_URL = "https://huggingface.co/papers"


def fetch_web_source(source: SourceConfig, settings: Settings) -> list[RawSourceItem]:
    if source.name != "Hugging Face Daily Papers":
        raise ValueError(f"Unsupported web source: {source.name}")

    response = httpx.get(
        source.url,
        headers={"User-Agent": settings.user_agent, "Accept-Encoding": "identity"},
        timeout=settings.request_timeout_seconds,
        follow_redirects=True,
    )
    response.raise_for_status()
    return parse_huggingface_daily_papers_page(response.text, source, settings.max_items_per_source)


def parse_huggingface_daily_papers_page(
    html_text: str,
    source: SourceConfig,
    max_items: int = 10,
) -> list[RawSourceItem]:
    props = _extract_daily_papers_props(html_text)
    daily_papers = props.get("dailyPapers", [])
    items: list[RawSourceItem] = []

    for entry in daily_papers[:max_items]:
        paper = entry.get("paper", entry)
        paper_id = paper.get("id") or paper.get("paperId")
        title = paper.get("title")
        if not paper_id or not title:
            continue

        summary = paper.get("summary") or paper.get("ai_summary") or paper.get("abstract")
        authors = paper.get("authors") or []
        author_names = [author.get("name") for author in authors if author.get("name")]
        published_at = _parse_iso_datetime(
            paper.get("submittedOnDailyAt") or entry.get("submittedOnDailyAt") or paper.get("publishedAt")
        )

        items.append(
            RawSourceItem(
                source_name=source.name,
                source_type=SourceType.WEB,
                title=title,
                url=f"{DAILY_PAPERS_BASE_URL}/{paper_id}",
                published_at=published_at,
                author=", ".join(author_names) or None,
                raw_summary=summary,
                content=summary,
            )
        )

    return items


def _extract_daily_papers_props(html_text: str) -> dict:
    match = re.search(
        r'data-target="DailyPapers"[^>]*data-props="([^"]+)"',
        html_text,
        flags=re.DOTALL,
    )
    if match is None:
        raise ValueError("Hugging Face Daily Papers payload not found")
    return json.loads(unescape(match.group(1)))


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
