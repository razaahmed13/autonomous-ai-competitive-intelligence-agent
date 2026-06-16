from __future__ import annotations

import json

from ..models import DedupedEvent, IntelligenceCategory
from ..scoring import criteria_prompt_text

CATEGORY_DEFINITIONS = """
Allowed categories:
- Model Release: A new or updated AI model, model family, benchmarked model, or hosted model capability release.
- Research: Academic or technical research papers, methods, benchmark findings, architectures, training techniques, or scientific results.
- Startup Activity: Funding, acquisitions, product launches from startups, hiring, partnerships, pivots, or go-to-market activity involving AI startups.
- Competitor Update: Strategic updates from major AI companies or relevant competitors, including product direction, partnerships, platform shifts, pricing, availability, or enterprise positioning.
- Infrastructure: Developer tools, model-serving systems, chips, inference platforms, data infrastructure, AI SDKs, orchestration frameworks, cloud infrastructure, or deployment tooling.
- Regulation: AI policy, law, governance, safety standards, compliance, copyright/legal rulings, or government action.
- Other: Relevant AI developments that do not fit the above categories.
""".strip()


def build_categorization_system_prompt() -> str:
    return "You classify AI competitive intelligence events. Return valid strict JSON only."


def build_analysis_system_prompt() -> str:
    return "You are a source-grounded competitive intelligence analyst for Neodym. Return valid strict JSON only."


def build_categorization_prompt(event: DedupedEvent) -> str:
    return f"""
Categorization task: LLM-only classification.

Do not use keyword rules, hardcoded source rules, or category hints. Classify from the provided event context and category definitions only.

{CATEGORY_DEFINITIONS}

Canonical title: {event.canonical_title}
Source names: {', '.join(item.source_name for item in event.source_items)}
Source links: {', '.join(event.source_links)}
Context:
{_event_context(event)}

Return JSON exactly in this shape:
{{
  "category": "one allowed category exactly",
  "confidence": 0.0,
  "reason": "short reason"
}}
""".strip()


def build_analysis_prompt(event: DedupedEvent, category: IntelligenceCategory, neodym_profile: str | None = None) -> str:
    neodym_profile = neodym_profile or "Neodym cares about practical AI systems, AI agents, automation, model capabilities, enterprise AI adoption, developer tooling, and measurable business impact."
    return f"""
Analyze this AI competitive intelligence event for Neodym.

Rules:
- Do not invent facts.
- Use only the provided source content and links.
- Every final item must remain source-grounded.
- Keep writing concise and executive-readable.

Neodym profile:
{neodym_profile}

Scoring task:
Do not return a numeric importance score. The backend owns all score math.
Evaluate the event against each fixed criterion and assign one allowed status plus source-grounded evidence.

{criteria_prompt_text()}

Canonical title: {event.canonical_title}
Category: {category.value}
Source links: {', '.join(event.source_links)}
Context:
{_event_context(event)}

Return JSON exactly in this shape:
{{
  "title": "concise title",
  "summary": "what happened",
  "why_it_matters": "broader significance",
  "scoring_assessments": [
    {{
      "id": "neodym_relevance",
      "status": "strong",
      "evidence": "source-grounded evidence for this criterion",
      "reason": "why this status was assigned"
    }}
  ]
}}
""".strip()


def _event_context(event: DedupedEvent) -> str:
    rows = []
    for item in event.source_items:
        rows.append(
            json.dumps(
                {
                    "title": item.title,
                    "source": item.source_name,
                    "url": item.url,
                    "published_at": item.published_at.isoformat() if item.published_at else None,
                    "summary": item.raw_summary or item.content,
                },
                ensure_ascii=False,
            )
        )
    return "\n".join(rows)
