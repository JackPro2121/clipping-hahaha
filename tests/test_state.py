import pytest
from datetime import datetime, timezone, timedelta
from utils.state import (
    load_state,
    save_state,
    get_known_urls,
    archive_old_sources,
    should_retry,
    schedule_retry,
    mark_processed,
)


def test_get_known_urls():
    state = {
        "sources": [{"url": "https://url1"}, {"url": "https://url2"}],
        "archived_urls": ["https://url3", "https://url4"],
    }
    known = get_known_urls(state)
    assert len(known) == 4
    assert "https://url1" in known
    assert "https://url3" in known


def test_archive_old_sources():
    old_date = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    recent_date = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()

    state = {
        "sources": [
            {"url": "https://old_processed", "status": "processed", "processed_at": old_date},
            {"url": "https://recent_processed", "status": "processed", "processed_at": recent_date},
            {"url": "https://pending", "status": "pending"},
        ],
        "archived_urls": [],
    }

    archived_count = archive_old_sources(state, keep_days=30)
    assert archived_count == 1
    assert len(state["sources"]) == 2
    assert "https://old_processed" in state["archived_urls"]
    assert any(s["url"] == "https://recent_processed" for s in state["sources"])


def test_should_retry_backoff():
    # 1. Normal fresh pending
    src = {"url": "https://fresh", "status": "pending", "retry_count": 0}
    assert should_retry(src) is True

    # 2. Already in future backoff window
    future_time = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    src["next_retry_after"] = future_time
    assert should_retry(src) is False

    # 3. Backoff elapsed
    past_time = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    src["next_retry_after"] = past_time
    assert should_retry(src) is True

    # 4. Max retries exceeded (pure query returns False, status stays pending until schedule_retry)
    src["retry_count"] = 5
    assert should_retry(src) is False


def test_schedule_retry():
    src = {"url": "https://test", "status": "pending"}
    schedule_retry(src, "Download timed out")
    assert src["retry_count"] == 1
    assert src["last_error"] == "Download timed out"
    assert src["next_retry_after"] is not None
    assert src["status"] == "pending"

    # Test transition to failed when retry_count reaches 5
    src["retry_count"] = 4
    schedule_retry(src, "Permanent failure")
    assert src["retry_count"] == 5
    assert src["status"] == "failed"


def test_mark_processed():
    src = {"url": "https://test", "status": "pending", "retry_count": 2}
    mark_processed(src, clips_count=3)
    assert src["status"] == "processed"
    assert src["clips_count"] == 3
    assert src["processed_at"] is not None
    assert src["next_retry_after"] is None
