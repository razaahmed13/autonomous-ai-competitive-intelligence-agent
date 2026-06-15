from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path = Path(".env")) -> None:
    """Load simple KEY=VALUE pairs without overriding existing environment vars."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _parse_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_path: Path = Path("data/intelligence.db")
    neodym_profile_path: Path = Path("docs/neodym-profile.md")
    max_items_per_source: int = 10
    brief_lookback_hours: int = 24
    user_agent: str = "neodym-competitive-intelligence-agent/0.1"
    ai_api_key: str | None = None
    ai_base_url: str | None = None
    ai_model: str | None = None
    slack_enabled: bool = False
    slack_bot_token: str | None = None
    slack_channel: str = "#industry-trends"
    slack_api_url: str = "https://slack.com/api/chat.postMessage"
    request_timeout_seconds: float = 20.0

    @classmethod
    def from_env(cls, env_file: Path | None = Path(".env")) -> "Settings":
        if env_file is not None:
            _load_dotenv(env_file)
        return cls(
            database_path=Path(os.getenv("DATABASE_PATH", "data/intelligence.db")),
            neodym_profile_path=Path(os.getenv("NEODYM_PROFILE_PATH", "docs/neodym-profile.md")),
            max_items_per_source=int(os.getenv("MAX_ITEMS_PER_SOURCE", "10")),
            brief_lookback_hours=int(os.getenv("BRIEF_LOOKBACK_HOURS", "24")),
            user_agent=os.getenv("USER_AGENT", "neodym-competitive-intelligence-agent/0.1"),
            ai_api_key=os.getenv("AI_API_KEY") or None,
            ai_base_url=os.getenv("AI_BASE_URL") or None,
            ai_model=os.getenv("AI_MODEL") or None,
            slack_enabled=_parse_bool(os.getenv("SLACK_ENABLED"), default=False),
            slack_bot_token=os.getenv("SLACK_BOT_TOKEN") or None,
            slack_channel=os.getenv("SLACK_CHANNEL", "#industry-trends"),
            slack_api_url=os.getenv("SLACK_API_URL", "https://slack.com/api/chat.postMessage"),
            request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "20")),
        )


def load_neodym_profile(path: str | Path = Path("docs/neodym-profile.md")) -> str:
    path = Path(path)
    if not path.exists():
        return DEFAULT_NEODYM_PROFILE
    profile = path.read_text(encoding="utf-8").strip()
    return profile or DEFAULT_NEODYM_PROFILE


DEFAULT_NEODYM_PROFILE = """
# Neodym Profile

Neodym is an AI consulting company focused on measurable business outcomes. It helps companies identify, build, deploy, and improve production-grade AI systems, especially AI agents, workflow automation, model/data pipelines, and AI-native product infrastructure.

Use this profile to judge strategic relevance: prioritize developments that help Neodym deliver faster ROI, reduce client costs, build more reliable production AI systems, improve agent and automation workflows, strengthen data/model engineering, or clarify market positioning for affordable, outcome-based AI consulting.
""".strip()
