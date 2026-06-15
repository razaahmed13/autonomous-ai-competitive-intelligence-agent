from __future__ import annotations

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html import unescape
import re
import xml.etree.ElementTree as ET

import httpx

from ..config import Settings
from ..models import RawSourceItem, SourceConfig, SourceType


def fetch_rss_source(source: SourceConfig, settings: Settings) -> list[RawSourceItem]:
    response = httpx.get(
        source.url,
        headers={"User-Agent": settings.user_agent},
        timeout=settings.request_timeout_seconds,
        follow_redirects=True,
    )
    response.raise_for_status()
    return parse_rss_feed(response.text, source, settings.max_items_per_source)


def parse_rss_feed(xml_text: str, source: SourceConfig, max_items: int = 10) -> list[RawSourceItem]:
    try:
        return _parse_with_feedparser(xml_text, source, max_items)
    except Exception:
        return _parse_with_elementtree(xml_text, source, max_items)


def _parse_with_feedparser(xml_text: str, source: SourceConfig, max_items: int) -> list[RawSourceItem]:
    import feedparser  # optional runtime dependency declared in pyproject

    feed = feedparser.parse(xml_text)
    items: list[RawSourceItem] = []
    for entry in feed.entries[:max_items]:
        title = getattr(entry, "title", "")
        link = getattr(entry, "link", "")
        if not title or not link:
            continue
        summary = _clean_html(getattr(entry, "summary", "") or getattr(entry, "description", ""))
        published_at = None
        if getattr(entry, "published_parsed", None):
            published_at = datetime(*entry.published_parsed[:6], tzinfo=UTC)
        elif getattr(entry, "updated_parsed", None):
            published_at = datetime(*entry.updated_parsed[:6], tzinfo=UTC)
        items.append(
            RawSourceItem(
                source_name=source.name,
                source_type=SourceType.RSS,
                title=title,
                url=link,
                published_at=published_at,
                author=getattr(entry, "author", None),
                raw_summary=summary,
                content=summary,
            )
        )
    return items


def _parse_with_elementtree(xml_text: str, source: SourceConfig, max_items: int) -> list[RawSourceItem]:
    root = ET.fromstring(xml_text)
    entries = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
    items: list[RawSourceItem] = []
    for entry in entries[:max_items]:
        title = _child_text(entry, "title")
        link = _child_text(entry, "link")
        if not link:
            atom_link = entry.find("{http://www.w3.org/2005/Atom}link")
            link = atom_link.attrib.get("href", "") if atom_link is not None else ""
        if not title or not link:
            continue
        summary = _clean_html(_child_text(entry, "description") or _child_text(entry, "summary") or _child_text(entry, "content"))
        published = _child_text(entry, "pubDate") or _child_text(entry, "published") or _child_text(entry, "updated")
        items.append(
            RawSourceItem(
                source_name=source.name,
                source_type=SourceType.RSS,
                title=title,
                url=link,
                published_at=_parse_date(published),
                raw_summary=summary,
                content=summary,
            )
        )
    return items


def _child_text(entry: ET.Element, tag: str) -> str:
    node = entry.find(tag)
    if node is None:
        node = entry.find(f"{{http://www.w3.org/2005/Atom}}{tag}")
    return "" if node is None or node.text is None else node.text.strip()


def _parse_date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed
    except Exception:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return None


def _clean_html(value: str | None) -> str | None:
    if not value:
        return None
    text = re.sub(r"<[^>]+>", " ", value)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None
