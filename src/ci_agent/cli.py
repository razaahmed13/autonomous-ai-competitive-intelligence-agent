from __future__ import annotations

import argparse
from pathlib import Path

from .config import Settings
from .database import Database
from .pipeline import collect_sources, generate_brief
from .slack import send_slack_markdown_report
from .sources import DEFAULT_SOURCES


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AI competitive intelligence agent")
    parser.add_argument(
        "command",
        choices=["collect", "brief", "all", "send-slack"],
        nargs="?",
        default="all",
        help="Command to run. Use collect for source collection, brief for report generation, all for both, send-slack to post an existing Markdown report.",
    )
    parser.add_argument("--json-output", default="daily_brief.json", help="Path for machine-readable JSON report.")
    parser.add_argument("--markdown-output", default="daily_brief.md", help="Path for Slack-ready Markdown report.")
    parser.add_argument("--max-items", type=int, default=None, help=argparse.SUPPRESS)
    parser.add_argument(
        "--raw-items",
        type=_positive_int,
        default=None,
        help="Process only the latest N raw items fetched within the brief lookback window.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate brief even for already-reported intelligence fingerprints.",
    )
    parser.add_argument(
        "--send-slack",
        action="store_true",
        help="Send the generated Markdown report to Slack after brief generation.",
    )
    parser.add_argument(
        "--slack-channel",
        default=None,
        help="Slack channel name or ID for delivery. Defaults to SLACK_CHANNEL or #industry-trends.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = Settings.from_env()

    if args.command == "send-slack":
        markdown_path = Path(args.markdown_output)
        if not markdown_path.exists():
            print(f"Markdown report not found: {markdown_path}")
            return 3
        markdown = markdown_path.read_text(encoding="utf-8")
        slack_result = send_slack_markdown_report(
            markdown=markdown,
            bot_token=settings.slack_bot_token,
            channel=args.slack_channel or settings.slack_channel,
            api_url=settings.slack_api_url,
            timeout_seconds=settings.request_timeout_seconds,
        )
        print(slack_result.message)
        return 0 if slack_result.sent or not slack_result.attempted else 4

    database = Database(settings.database_path)

    if args.command in {"collect", "all"}:
        result = collect_sources(DEFAULT_SOURCES, settings, database)
        print(f"Collected {result.raw_item_count} raw items from {result.source_count} sources.")
        if result.skipped_stale_count:
            print(f"Skipped {result.skipped_stale_count} items older than 24 hours based on published_at.")
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
                raw_item_limit=args.raw_items,
                force=args.force,
            )
        except (RuntimeError, ValueError) as exc:
            print(f"Could not generate brief: {exc}")
            print("Ensure Codex CLI is installed/authenticated for live LLM analysis, or set AI_MODEL=offline-demo for local smoke testing.")
            return 2
        print(f"Loaded {result.raw_item_count} raw items fetched in the last {settings.brief_lookback_hours} hours.")
        print(f"Merged into {result.candidate_count} unique candidate events.")
        if result.skipped_reported_count:
            print(f"Skipped {result.skipped_reported_count} already-reported candidate events.")
        print(f"Selected {result.selected_count} intelligence items.")
        print(f"Stored {result.reported_count} newly reported intelligence items.")
        print(f"Wrote {result.json_path}.")
        print(f"Wrote {result.markdown_path}.")
        if args.send_slack or settings.slack_enabled:
            markdown = Path(result.markdown_path).read_text(encoding="utf-8")
            slack_result = send_slack_markdown_report(
                markdown=markdown,
                bot_token=settings.slack_bot_token,
                channel=args.slack_channel or settings.slack_channel,
                api_url=settings.slack_api_url,
                timeout_seconds=settings.request_timeout_seconds,
            )
            print(slack_result.message)
    return 0
