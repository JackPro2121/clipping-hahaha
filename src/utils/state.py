"""state.py — State management, deduplication, auto-archiving, and retry intelligence.

Manages sources.json structure:
{
  "sources": [
    {
      "url": "...",
      "title": "...",
      "status": "pending" | "processed" | "failed",
      "score": 75,
      "discovered_at": "2026-08-20T16:00:00Z",
      "processed_at": "2026-08-20T16:05:00Z",
      "clips_count": 3,
      "retry_count": 0,
      "next_retry_after": null,
      "last_error": null
    }
  ],
  "archived_urls": ["..."],
  "_meta": {
    "last_run": "2026-08-20T16:05:00Z",
    "total_processed": 10,
    "total_clips_posted": 30,
    "last_category": "popular"
  }
}
"""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SOURCES_FILE = ROOT / "sources.json"


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_state(path=None):
    """Load sources.json, returning initialized default state if file doesn't exist."""
    p = Path(path) if path else SOURCES_FILE
    if not p.exists():
        return {
            "sources": [],
            "archived_urls": [],
            "_meta": {
                "last_run": None,
                "total_processed": 0,
                "total_clips_posted": 0,
            },
        }

    with open(p, encoding="utf-8") as f:
        data = json.load(f)

    # Normalize structure if loading legacy sources.json
    if "sources" not in data:
        data = {"sources": []}
    if "archived_urls" not in data:
        data["archived_urls"] = []
    if "_meta" not in data:
        data["_meta"] = {
            "last_run": None,
            "total_processed": sum(1 for s in data["sources"] if s.get("status") == "processed"),
            "total_clips_posted": 0,
        }
    return data


def save_state(data, path=None):
    """Save state dictionary to sources.json."""
    p = Path(path) if path else SOURCES_FILE
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_known_urls(data):
    """Return a set of all active and archived URLs for deduplication."""
    active = {s["url"] for s in data.get("sources", []) if s.get("url")}
    archived = set(data.get("archived_urls", []))
    return active | archived


def archive_old_sources(data, keep_days=30):
    """Archive processed items older than keep_days into archived_urls list.

    Returns:
        int: Number of sources archived.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
    active = []
    archived_urls = set(data.get("archived_urls", []))
    archived_count = 0

    for src in data.get("sources", []):
        status = src.get("status")
        processed_at = src.get("processed_at")

        if status == "processed" and processed_at:
            try:
                dt = datetime.fromisoformat(processed_at.replace("Z", "+00:00"))
                if dt < cutoff:
                    archived_urls.add(src["url"])
                    archived_count += 1
                    continue
            except (ValueError, TypeError):
                pass

        active.append(src)

    data["sources"] = active
    data["archived_urls"] = sorted(list(archived_urls))
    return archived_count


def _parse_iso(ts):
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


# Douyin CDN play URLs are signed and expire ~1h after the Apify scrape.
# 90 min gives safe margin against clock skew before a URL is declared dead.
PLAY_URL_MAX_AGE_S = 5400


def play_url_is_stale(src, max_age_s=PLAY_URL_MAX_AGE_S):
    """True when a source's signed play_url is past its usable lifetime."""
    if not src.get("play_url"):
        return False
    discovered = _parse_iso(src.get("discovered_at"))
    if discovered is None:
        return False
    age_s = (datetime.now(timezone.utc) - discovered).total_seconds()
    return age_s > max_age_s


def abandon_source(src, error_msg):
    """Mark a source failed immediately — for deterministically unrecoverable errors.

    Unlike schedule_retry, no backoff window is set: retrying would be futile
    (e.g. an expired douyin play URL cannot be renewed).
    """
    src["status"] = "failed"
    src["last_error"] = str(error_msg)[:200]
    src["next_retry_after"] = None


def reap_expired_play_urls(state, max_age_s=PLAY_URL_MAX_AGE_S):
    """Fail pending douyin sources whose signed play_url has expired.

    Retrying these is guaranteed futile: the CDN signature cannot be renewed,
    and each doomed attempt used to burn a processing slot and suppress new
    douyin discovery via the backlog gate. Idempotent — already-failed sources
    are skipped on subsequent calls.

    Returns:
        list[str]: URLs of sources marked failed by this call.
    """
    reaped = []
    for src in state.get("sources", []):
        if src.get("status") != "pending":
            continue
        if not play_url_is_stale(src, max_age_s=max_age_s):
            continue
        discovered = _parse_iso(src.get("discovered_at"))
        age_h = (
            (datetime.now(timezone.utc) - discovered).total_seconds() / 3600
            if discovered
            else 0
        )
        abandon_source(
            src,
            f"play_url expired ({age_h:.1f}h old) — douyin CDN signatures "
            "cannot be refreshed; retries skipped",
        )
        reaped.append(src["url"])
    return reaped


def should_retry(src, max_retries=5):
    """Check if a pending source is eligible for retry (pure query without side-effects)."""
    status = src.get("status", "pending")
    if status != "pending":
        return False

    retries = src.get("retry_count", 0)
    if retries >= max_retries:
        return False

    next_retry = src.get("next_retry_after")
    if next_retry:
        dt = _parse_iso(next_retry)
        if dt and dt > datetime.now(timezone.utc):
            return False  # Still in backoff window

    return True


def schedule_retry(src, error_msg):
    """Record an error and schedule the next retry with exponential backoff (2h, 4h, 8h, 16h, 32h)."""
    retry_count = src.get("retry_count", 0) + 1
    src["retry_count"] = retry_count
    src["last_error"] = str(error_msg)[:200]

    wait_hours = min(2 ** retry_count, 48)  # capped at 48h
    next_time = datetime.now(timezone.utc) + timedelta(hours=wait_hours)
    src["next_retry_after"] = next_time.isoformat()

    if retry_count >= 5:
        src["status"] = "failed"
    else:
        src["status"] = "pending"


def mark_processed(src, clips_count=0):
    """Mark a source as successfully processed with timestamp and stats."""
    src["status"] = "processed"
    src["processed_at"] = _now_iso()
    src["clips_count"] = clips_count
    src["next_retry_after"] = None
    src["last_error"] = None
