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

        if status in ("processed", "failed") and processed_at:
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


def should_retry(src, max_retries=5):
    """Check if a pending source is eligible for retry."""
    status = src.get("status", "pending")
    if status == "processed":
        return False
    if status == "failed":
        return False

    retries = src.get("retry_count", 0)
    if retries >= max_retries:
        src["status"] = "failed"
        return False

    next_retry = src.get("next_retry_after")
    if next_retry:
        try:
            dt = datetime.fromisoformat(next_retry.replace("Z", "+00:00"))
            if dt > datetime.now(timezone.utc):
                return False  # Still in backoff window
        except (ValueError, TypeError):
            pass

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
