from __future__ import annotations

import hashlib
import re
from collections import OrderedDict

from .models import DedupedEvent, RawSourceItem

_STOPWORDS = {
    "a", "an", "and", "are", "as", "for", "from", "in", "into", "is", "new", "of", "on", "the", "to", "with",
    "officially", "stock", "shares", "details", "update", "latest",
}

_BUSINESS_EVENT_TOKENS = {
    "acquire", "fund", "funding", "ipo", "valuation", "price", "pricing", "market", "share", "merger", "raise",
}

_BUSINESS_SYNONYMS = {
    "acquires": "acquire",
    "acquired": "acquire",
    "acquisition": "acquire",
    "buy": "acquire",
    "buying": "acquire",
    "buys": "acquire",
    "bought": "acquire",
    "bet": "acquire",
    "bets": "acquire",
    "raises": "raise",
    "raised": "raise",
}


def normalize_fingerprint(text: str) -> str:
    text = re.sub(r"\$(\d+(?:\.\d+)?)\s*billion\b", r"\1b", text.lower())
    text = re.sub(r"\$(\d+(?:\.\d+)?)\s*bn\b", r"\1b", text)
    normalized = re.sub(r"[^a-z0-9]+", " ", text)
    tokens = [_normalize_token(token) for token in normalized.split() if token and token not in _STOPWORDS]
    return " ".join(tokens)


def _normalize_token(token: str) -> str:
    token = _BUSINESS_SYNONYMS.get(token, token)
    return _stem_token(token)


def _stem_token(token: str) -> str:
    if len(token) > 4 and token.endswith("es"):
        return token[:-2]
    if len(token) > 3 and token.endswith("s"):
        return token[:-1]
    return token


def content_fingerprint_for_items(items: list[RawSourceItem]) -> str:
    text = " ".join([item.title for item in items] + [item.raw_summary or "" for item in items])
    return hashlib.sha256(normalize_fingerprint(text).encode("utf-8")).hexdigest()[:24]


def deduplicate_raw_items(items: list[RawSourceItem], similarity_threshold: float = 0.8) -> list[DedupedEvent]:
    groups: list[list[RawSourceItem]] = []
    for item in items:
        placed = False
        for group in groups:
            if _items_match(item, group[0], similarity_threshold):
                group.append(item)
                placed = True
                break
        if not placed:
            groups.append([item])

    events: list[DedupedEvent] = []
    for group in groups:
        links = list(OrderedDict((item.url, None) for item in group).keys())
        fingerprint = content_fingerprint_for_items(group)
        events.append(
            DedupedEvent(
                id=f"event:{fingerprint}",
                canonical_title=_choose_canonical_title(group),
                source_items=group,
                source_links=links,
                merged_summary=_merge_summaries(group),
                content_fingerprint=fingerprint,
            )
        )
    return events


def _items_match(left: RawSourceItem, right: RawSourceItem, threshold: float) -> bool:
    if left.url == right.url:
        return True
    left_fp = normalize_fingerprint(left.title)
    right_fp = normalize_fingerprint(right.title)
    if left_fp == right_fp:
        return True
    if _business_event_match(left_fp, right_fp):
        return True
    return _token_similarity(left_fp, right_fp) >= threshold


def _business_event_match(left: str, right: str) -> bool:
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    if not left_tokens or not right_tokens:
        return False
    shared_tokens = left_tokens & right_tokens
    shared_business_tokens = shared_tokens & _BUSINESS_EVENT_TOKENS
    shared_entity_tokens = {
        token
        for token in shared_tokens
        if token not in _BUSINESS_EVENT_TOKENS and not re.fullmatch(r"\d+(?:\.\d+)?b", token)
    }
    has_money_overlap = any(re.fullmatch(r"\d+(?:\.\d+)?b", token) for token in shared_tokens)
    return bool(shared_business_tokens) and (
        len(shared_entity_tokens) >= 2 or (len(shared_entity_tokens) >= 1 and has_money_overlap)
    )


def _token_similarity(left: str, right: str) -> float:
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    if not left_tokens or not right_tokens:
        return 0.0
    jaccard = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
    containment = len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens))
    return max(jaccard, containment)


def _choose_canonical_title(items: list[RawSourceItem]) -> str:
    return max((item.title for item in items), key=len)


def _merge_summaries(items: list[RawSourceItem]) -> str | None:
    summaries = [item.raw_summary or item.content for item in items if item.raw_summary or item.content]
    if not summaries:
        return None
    return " ".join(OrderedDict((summary, None) for summary in summaries).keys())
