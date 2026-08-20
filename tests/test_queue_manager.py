import pytest
from pipeline.queue_manager import can_queue_posts


def test_can_queue_posts_under_limit(monkeypatch):
    monkeypatch.setattr(
        "pipeline.queue_manager.get_channel_queue_depth",
        lambda channel_id: 5,
    )
    allowed, depth = can_queue_posts("channel_123", max_queue_depth=20)
    assert allowed is True
    assert depth == 5


def test_can_queue_posts_at_limit(monkeypatch):
    monkeypatch.setattr(
        "pipeline.queue_manager.get_channel_queue_depth",
        lambda channel_id: 20,
    )
    allowed, depth = can_queue_posts("channel_123", max_queue_depth=20)
    assert allowed is False
    assert depth == 20
