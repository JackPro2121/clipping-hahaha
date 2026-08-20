"""slack.py — Slack notification system for pipeline run summaries and health alerts.

Uses Slack Incoming Webhooks (configured via SLACK_WEBHOOK_URL env var).
Fails gracefully without crashing if no webhook is configured.
"""

import os
from datetime import datetime, timezone
import requests


def _get_webhook():
    return os.environ.get("SLACK_WEBHOOK_URL")


def send_slack_notification(payload):
    """Send a formatted JSON payload to the Slack Incoming Webhook.

    Args:
        payload: Dict containing 'text' or 'blocks'.

    Returns:
        bool: True if delivered successfully, False otherwise.
    """
    webhook_url = _get_webhook()
    if not webhook_url:
        return False

    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        return resp.status_code == 200
    except Exception as exc:
        print(f"Slack notification failed to send: {exc}")
        return False


def send_slack_summary(run_stats):
    """Send a structured run summary to Slack.

    Args:
        run_stats: Dictionary with keys:
            - processed_count: int
            - clips_posted: int
            - failed_count: int
            - category: str
            - run_duration_s: float (optional)
    """
    processed = run_stats.get("processed_count", 0)
    clips = run_stats.get("clips_posted", 0)
    failed = run_stats.get("failed_count", 0)
    category = run_stats.get("category", "popular")
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    status_emoji = "✅" if failed == 0 else "⚠️"

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{status_emoji} Clip & Post — Run Complete",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Time:* {now_str}"},
                {"type": "mrkdwn", "text": f"*Category:* `{category}`"},
                {"type": "mrkdwn", "text": f"*Sources Processed:* `{processed}`"},
                {"type": "mrkdwn", "text": f"*Clips Posted:* `{clips}`"},
            ],
        },
    ]

    if failed > 0:
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"⚠️ *{failed} source(s)* encountered an error and entered retry backoff.",
                    }
                ],
            }
        )

    return send_slack_notification(
        {
            "text": f"Clip & Post: {clips} clips posted ({status_emoji})",
            "blocks": blocks,
        }
    )


def send_slack_alert(title, details, is_error=True):
    """Send an immediate alert message to Slack (e.g. for stale sources or queue full)."""
    icon = "🚨" if is_error else "ℹ️"
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{icon} Pipeline Alert: {title}*\n{details}",
            },
        }
    ]
    return send_slack_notification({"text": f"{icon} {title}", "blocks": blocks})
