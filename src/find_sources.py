"""find_sources.py — Automated discovery with quality scoring, category rotation, and archiving."""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from chocodata import discover as discover_youtube  # noqa: E402
from bilibili import discover as discover_bilibili  # noqa: E402
from pipeline.quality import score_source, should_process  # noqa: E402
from utils.state import (  # noqa: E402
    load_state,
    save_state,
    get_known_urls,
    archive_old_sources,
)

ROOT = Path(__file__).resolve().parent.parent


def _get_next_category(cfg, state):
    """Determine the next Bilibili category to scrape in round-robin fashion."""
    categories = cfg.get("discovery", {}).get("categories") or ["popular"]
    last_cat = state.get("_meta", {}).get("last_category")
    if not last_cat or last_cat not in categories:
        return categories[0]
    next_idx = (categories.index(last_cat) + 1) % len(categories)
    return categories[next_idx]


def main():
    with open(ROOT / "config.json", encoding="utf-8") as f:
        cfg = json.load(f)

    discovery = cfg.get("discovery")
    if not discovery or not discovery.get("enabled"):
        print("Discovery disabled in config")
        return

    state = load_state()

    # 1. Run automatic archiving on sources older than 30 days
    archived = archive_old_sources(state, keep_days=30)
    if archived:
        print(f"State maintenance: Archived {archived} old processed sources")

    strategy = discovery.get("strategy", "bilibili")
    current_category = "popular"

    # 2. Discover sources based on strategy & category
    try:
        if strategy == "bilibili":
            current_category = _get_next_category(cfg, state)
            print(f"Bilibili discovery feed: [{current_category}]")
            found = discover_bilibili(cfg, category=current_category)
        else:
            if "CHOCODATA_API_KEY" not in os.environ:
                print("CHOCODATA_API_KEY not set, skipping discovery")
                return
            found = discover_youtube(cfg)
    except Exception as exc:
        print(f"Discovery failed: {exc}")
        return

    known_urls = get_known_urls(state)
    min_score = discovery.get("min_quality_score", 20)

    # 3. Quality score and filter candidate videos
    scored_candidates = []
    for src in found:
        if src["url"] in known_urls:
            continue
        if discovery.get("min_views") and src.get("views", 0) < discovery["min_views"]:
            continue

        score = score_source(src)
        if score >= min_score:
            scored_candidates.append((score, src))

    # Prioritize highest quality candidates first
    scored_candidates.sort(key=lambda x: x[0], reverse=True)

    max_new = discovery.get("max_new_sources", 3)
    added = 0
    now_iso = datetime.now(timezone.utc).isoformat()

    for score, src in scored_candidates:
        state["sources"].append(
            {
                "url": src["url"],
                "title": src.get("title", ""),
                "status": "pending",
                "score": score,
                "category": src.get("category", current_category),
                "discovered_at": now_iso,
                "retry_count": 0,
            }
        )
        known_urls.add(src["url"])
        added += 1
        print(f"Added source ({score}/100 pts): {src['title'][:60]} -> {src['url']}")
        if added >= max_new:
            break

    # 4. Update metadata and save state
    state["_meta"]["last_category"] = current_category
    save_state(state)
    print(f"Discovery finished: {added} new high-quality sources added.")


if __name__ == "__main__":
    main()