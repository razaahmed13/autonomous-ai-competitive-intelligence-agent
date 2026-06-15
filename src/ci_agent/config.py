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


@dataclass(frozen=True)
class Settings:
    database_path: Path = Path("data/intelligence.db")
    max_items_per_source: int = 10
    user_agent: str = "neodym-competitive-intelligence-agent/0.1"
    ai_api_key: str | None = None
    ai_base_url: str | None = None
    ai_model: str | None = None
    slack_bot_token: str | None = None
    slack_channel: str = "#industry-trends"
    request_timeout_seconds: float = 20.0

    @classmethod
    def from_env(cls, env_file: Path | None = Path(".env")) -> "Settings":
        if env_file is not None:
            _load_dotenv(env_file)
        return cls(
            database_path=Path(os.getenv("DATABASE_PATH", "data/intelligence.db")),
            max_items_per_source=int(os.getenv("MAX_ITEMS_PER_SOURCE", "10")),
            user_agent=os.getenv("USER_AGENT", "neodym-competitive-intelligence-agent/0.1"),
            ai_api_key=os.getenv("AI_API_KEY") or None,
            ai_base_url=os.getenv("AI_BASE_URL") or None,
            ai_model=os.getenv("AI_MODEL") or None,
            slack_bot_token=os.getenv("SLACK_BOT_TOKEN") or None,
            slack_channel=os.getenv("SLACK_CHANNEL", "#industry-trends"),
            request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "20")),
        )
