import pytest
from notifications.slack import send_slack_notification, send_slack_summary, send_slack_alert


def test_slack_no_webhook_graceful(monkeypatch):
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    # Should safely return False without raising exceptions
    assert send_slack_notification({"text": "Test"}) is False
    assert send_slack_summary({"processed_count": 1, "clips_posted": 3}) is False
    assert send_slack_alert("Alert Title", "Details") is False
