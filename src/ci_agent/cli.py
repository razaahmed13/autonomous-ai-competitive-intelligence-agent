from __future__ import annotations

import argparse

from .config import Settings
from .database import Database
from .pipeline import collect_sources
from .sources import DEFAULT_SOURCES


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AI competitive intelligence agent")
    parser.add_argument(
        "command",
        choices=["collect", "all"],
        nargs="?",
        default="all",
        help="Command to run. Phase A supports collect/all source collection.",
    )
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
        return 0

    return 1
