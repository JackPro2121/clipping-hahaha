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
    abandon_source,
    play_url_is_stale,
    reap_expired_play_urls,
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


# ─────────────────────────────────────────────────────────────
# play_url staleness + reaping (douyin retry fix)
# ─────────────────────────────────────────────────────────────

def _hours_ago(h):
    return (datetime.now(timezone.utc) - timedelta(hours=h)).isoformat()


def test_play_url_is_stale():
    # Expired URL (>90 min old)
    old = {
        "url": "https://www.douyin.com/video/1",
        "status": "pending",
        "play_url": "https://cdn.example.com/expired",
        "discovered_at": _hours_ago(3),
    }
    assert play_url_is_stale(old) is True

    # Fresh URL (<90 min old)
    fresh = dict(old, discovered_at=_hours_ago(0.5))
    assert play_url_is_stale(fresh) is False

    # No play_url -> never stale
    assert play_url_is_stale({"url": "x", "discovered_at": _hours_ago(50)}) is False

    # Missing/garbage discovered_at -> treated as not stale (conservative)
    assert play_url_is_stale({"play_url": "u", "discovered_at": "not-a-date"}) is False
    assert play_url_is_stale({"play_url": "u"}) is False


def test_reap_expired_play_urls():
    state = {
        "sources": [
            {   # stale pending douyin -> reaped
                "url": "https://www.douyin.com/video/111",
                "status": "pending",
                "play_url": "https://cdn/dead1",
                "discovered_at": _hours_ago(20),
            },
            {   # fresh pending douyin -> untouched
                "url": "https://www.douyin.com/video/222",
                "status": "pending",
                "play_url": "https://cdn/live",
                "discovered_at": _hours_ago(0.2),
            },
            {   # bilibili, no play_url -> untouched
                "url": "https://www.bilibili.com/video/BV1abc",
                "status": "pending",
                "retry_count": 2,
            },
            {   # already processed douyin -> untouched
                "url": "https://www.douyin.com/video/333",
                "status": "processed",
                "play_url": "https://cdn/dead3",
                "discovered_at": _hours_ago(48),
            },
            {   # failed douyin in backoff -> untouched
                "url": "https://www.douyin.com/video/444",
                "status": "failed",
                "play_url": "https://cdn/dead4",
                "discovered_at": _hours_ago(48),
            },
        ],
    }

    reaped = reap_expired_play_urls(state)
    assert reaped == ["https://www.douyin.com/video/111"]

    by_url = {s["url"]: s for s in state["sources"]}
    dead = by_url["https://www.douyin.com/video/111"]
    assert dead["status"] == "failed"
    assert "expired" in dead["last_error"]
    assert dead["next_retry_after"] is None

    # Others unchanged
    assert by_url["https://www.douyin.com/video/222"]["status"] == "pending"
    assert by_url["https://www.bilibili.com/video/BV1abc"]["status"] == "pending"
    assert by_url["https://www.douyin.com/video/333"]["status"] == "processed"
    assert by_url["https://www.douyin.com/video/444"]["status"] == "failed"


def test_reap_expired_play_urls_idempotent():
    state = {
        "sources": [
            {
                "url": "https://www.douyin.com/video/999",
                "status": "pending",
                "play_url": "https://cdn/dead",
                "discovered_at": _hours_ago(5),
            }
        ],
    }
    first = reap_expired_play_urls(state)
    second = reap_expired_play_urls(state)
    assert first == ["https://www.douyin.com/video/999"]
    assert second == []


def test_abandon_source():
    src = {"url": "https://test", "status": "pending", "retry_count": 3,
           "next_retry_after": "2026-01-01T00:00:00+00:00"}
    abandon_source(src, "play_url expired")
    assert src["status"] == "failed"
    assert src["last_error"] == "play_url expired"
    assert src["next_retry_after"] is None
