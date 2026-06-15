from __future__ import annotations

import json
import os
import subprocess
import sys
from urllib.error import URLError

from ci_agent.config import Settings
from ci_agent.slack import send_slack_markdown_report


class FakeHTTPResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_settings_loads_optional_slack_delivery_config(monkeypatch):
    monkeypatch.setenv("SLACK_ENABLED", "true")
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test-token")
    monkeypatch.setenv("SLACK_CHANNEL", "#industry-trends")
    monkeypatch.setenv("SLACK_API_URL", "https://slack.example.test/chat.postMessage")

    settings = Settings.from_env(env_file=None)

    assert settings.slack_enabled is True
    assert settings.slack_bot_token == "xoxb-test-token"
    assert settings.slack_channel == "#industry-trends"
    assert settings.slack_api_url == "https://slack.example.test/chat.postMessage"


def test_settings_defaults_keep_slack_delivery_disabled(monkeypatch):
    monkeypatch.delenv("SLACK_ENABLED", raising=False)
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    monkeypatch.delenv("SLACK_CHANNEL", raising=False)
    monkeypatch.delenv("SLACK_API_URL", raising=False)

    settings = Settings.from_env(env_file=None)

    assert settings.slack_enabled is False
    assert settings.slack_bot_token is None
    assert settings.slack_channel == "#industry-trends"
    assert settings.slack_api_url == "https://slack.com/api/chat.postMessage"


def test_slack_delivery_skips_cleanly_without_token():
    result = send_slack_markdown_report(
        markdown="*Daily brief*",
        bot_token=None,
        channel="#industry-trends",
    )

    assert result.attempted is False
    assert result.sent is False
    assert result.channel == "#industry-trends"
    assert "SLACK_BOT_TOKEN" in result.message


def test_slack_delivery_posts_markdown_without_exposing_token():
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["headers"] = dict(request.header_items())
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeHTTPResponse({"ok": True, "channel": "C123", "ts": "123.456"})

    result = send_slack_markdown_report(
        markdown="*Daily brief*\n- One important thing",
        bot_token="xoxb-secret-token",
        channel="#industry-trends",
        api_url="https://slack.example.test/chat.postMessage",
        timeout_seconds=7,
        opener=fake_urlopen,
    )

    assert result.attempted is True
    assert result.sent is True
    assert result.slack_ts == "123.456"
    assert result.channel == "#industry-trends"
    assert "xoxb-secret-token" not in result.message
    assert captured["url"] == "https://slack.example.test/chat.postMessage"
    assert captured["timeout"] == 7
    assert captured["headers"]["Authorization"] == "Bearer xoxb-secret-token"
    assert captured["headers"]["Content-type"] == "application/json"
    assert captured["payload"] == {
        "channel": "#industry-trends",
        "text": "*Daily brief*\n- One important thing",
        "unfurl_links": False,
        "unfurl_media": False,
    }


def test_slack_delivery_returns_clean_failure_for_slack_api_error():
    def fake_urlopen(request, timeout):
        return FakeHTTPResponse({"ok": False, "error": "channel_not_found"})

    result = send_slack_markdown_report(
        markdown="brief",
        bot_token="xoxb-secret-token",
        channel="#industry-trends",
        opener=fake_urlopen,
    )

    assert result.attempted is True
    assert result.sent is False
    assert "channel_not_found" in result.message
    assert "xoxb-secret-token" not in result.message


def test_slack_delivery_returns_clean_failure_for_network_error():
    def fake_urlopen(request, timeout):
        raise URLError("temporary outage")

    result = send_slack_markdown_report(
        markdown="brief",
        bot_token="xoxb-secret-token",
        channel="#industry-trends",
        opener=fake_urlopen,
    )

    assert result.attempted is True
    assert result.sent is False
    assert "temporary outage" in result.message
    assert "xoxb-secret-token" not in result.message


def test_cli_exposes_slack_delivery_options():
    result = subprocess.run(
        [sys.executable, "run.py", "--help"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "--send-slack" in result.stdout
    assert "--slack-channel" in result.stdout


def test_cli_send_slack_without_token_does_not_crash(tmp_path):
    env = os.environ.copy()
    env.update(
        {
            "DATABASE_PATH": str(tmp_path / "intelligence.db"),
            "AI_MODEL": "offline-demo",
            "SLACK_BOT_TOKEN": "",
            "SLACK_ENABLED": "false",
        }
    )
    json_path = tmp_path / "daily_brief.json"
    markdown_path = tmp_path / "daily_brief.md"

    result = subprocess.run(
        [
            sys.executable,
            "run.py",
            "brief",
            "--json-output",
            str(json_path),
            "--markdown-output",
            str(markdown_path),
            "--send-slack",
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    assert "Slack delivery skipped: SLACK_BOT_TOKEN is not configured." in result.stdout
    assert json_path.exists()
    assert markdown_path.exists()
