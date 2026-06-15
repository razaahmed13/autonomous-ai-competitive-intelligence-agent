from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class URLOpener(Protocol):
    def __call__(self, request: Request, timeout: float): ...


@dataclass(frozen=True)
class SlackDeliveryResult:
    attempted: bool
    sent: bool
    channel: str
    message: str
    slack_ts: str | None = None


def send_slack_markdown_report(
    *,
    markdown: str,
    bot_token: str | None,
    channel: str,
    api_url: str = "https://slack.com/api/chat.postMessage",
    timeout_seconds: float = 20,
    opener: URLOpener = urlopen,
) -> SlackDeliveryResult:
    """Send Slack-ready markdown through chat.postMessage.

    The token is intentionally accepted as a plain argument so callers can keep
    credentials in env/config. Return values never include the token.
    """
    channel = channel.strip() or "#industry-trends"
    if not bot_token:
        return SlackDeliveryResult(
            attempted=False,
            sent=False,
            channel=channel,
            message="Slack delivery skipped: SLACK_BOT_TOKEN is not configured.",
        )

    text = markdown.strip()
    if not text:
        return SlackDeliveryResult(
            attempted=False,
            sent=False,
            channel=channel,
            message="Slack delivery skipped: Markdown report is empty.",
        )

    payload = {
        "channel": channel,
        "text": text,
        "unfurl_links": False,
        "unfurl_media": False,
    }
    request = Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {bot_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with opener(request, timeout=timeout_seconds) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        return SlackDeliveryResult(
            attempted=True,
            sent=False,
            channel=channel,
            message=f"Slack delivery failed: HTTP {exc.code}.",
        )
    except URLError as exc:
        return SlackDeliveryResult(
            attempted=True,
            sent=False,
            channel=channel,
            message=f"Slack delivery failed: {exc.reason}.",
        )
    except (json.JSONDecodeError, OSError) as exc:
        return SlackDeliveryResult(
            attempted=True,
            sent=False,
            channel=channel,
            message=f"Slack delivery failed: {exc}.",
        )

    if not response_payload.get("ok"):
        error = str(response_payload.get("error") or "unknown_error")
        return SlackDeliveryResult(
            attempted=True,
            sent=False,
            channel=channel,
            message=f"Slack delivery failed: {error}.",
        )

    slack_ts = response_payload.get("ts")
    return SlackDeliveryResult(
        attempted=True,
        sent=True,
        channel=channel,
        slack_ts=str(slack_ts) if slack_ts else None,
        message=f"Sent Slack report to {channel}.",
    )
