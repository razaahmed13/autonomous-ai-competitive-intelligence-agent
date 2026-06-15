from __future__ import annotations

from pathlib import Path

from ..models import DailyBrief


def render_slack_markdown(brief: DailyBrief) -> str:
    lines = [
        "*Daily AI Competitive Intelligence Brief*",
        f"_Date: {brief.date}_",
        "",
        f"Generated from {brief.source_count} sources. Selected {brief.selected_count} high-signal developments from {brief.candidate_count} candidates.",
        "",
    ]
    for index, item in enumerate(brief.items, start=1):
        lines.extend(
            [
                f"*{index}. [{item.importance_score:.1f}/10] {item.title}*",
                f"*Category:* {item.category.value}",
                f"*Summary:* {item.summary}",
                f"*Why it matters:* {item.why_it_matters}",
                f"*Why it matters to Neodym:* {item.why_it_matters_to_neodym}",
                f"*Recommended action:* {item.recommended_action}",
                f"*Sources:* {_format_sources(item.source_links, item.source_names)}",
                "",
                "---",
                "",
            ]
        )
    lines.extend([f"*Methodology:* {brief.methodology}", ""])
    return "\n".join(lines)


def write_slack_markdown(brief: DailyBrief, path: str | Path) -> str:
    markdown = render_slack_markdown(brief)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")
    return markdown


def _format_sources(links: list[str], names: list[str]) -> str:
    formatted = []
    for index, link in enumerate(links):
        label = names[index] if index < len(names) else f"Source {index + 1}"
        formatted.append(f"<{link}|{label}>")
    return ", ".join(formatted)
