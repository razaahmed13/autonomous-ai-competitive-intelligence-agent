from __future__ import annotations

import argparse

from .config import Settings
from .database import Database
from .pipeline import collect_sources, generate_brief
from .sources import DEFAULT_SOURCES


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AI competitive intelligence agent")
    parser.add_argument(
        "command",
        choices=["collect", "brief", "all"],
        nargs="?",
        default="all",
        help="Command to run. Use collect for source collection, brief for report generation, all for both.",
    )
    parser.add_argument("--json-output", default="daily_brief.json", help="Path for machine-readable JSON report.")
    parser.add_argument("--markdown-output", default="daily_brief.md", help="Path for Slack-ready Markdown report.")
    parser.add_argument("--max-items", type=int, default=8, help="Maximum intelligence items in the report.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = Settings.from_env()
    database = Database(settings.database_path)

    if args.command in {"collect", "all"}:
        result = collect_sources(DEFAULT_SOURCES, settings, database)
        print(f"Collected {result.raw_item_count} raw items from {result.source_count} sources.")
        print(f"Inserted {result.inserted_count} new raw items into {settings.database_path}.")
        if result.failed_sources:
            print(f"{len(result.failed_sources)} sources failed:")
            for failure in result.failed_sources:
                print(f"- {failure.source_name}: {failure.error}")

    if args.command in {"brief", "all"}:
        try:
            result = generate_brief(
                settings=settings,
                database=database,
                json_path=args.json_output,
                markdown_path=args.markdown_output,
                max_items=args.max_items,
            )
        except ValueError as exc:
            print(f"Could not generate brief: {exc}")
            print("Set AI_API_KEY/AI_MODEL for live LLM analysis, or set AI_MODEL=offline-demo for local smoke testing.")
            return 2
        print(f"Loaded {result.raw_item_count} raw items fetched in the last {settings.brief_lookback_hours} hours.")
        print(f"Merged into {result.candidate_count} unique candidate events.")
        print(f"Selected {result.selected_count} intelligence items.")
        print(f"Wrote {result.json_path}.")
        print(f"Wrote {result.markdown_path}.")
    return 0
