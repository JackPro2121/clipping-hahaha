"""find_sources.py — Automated discovery with quality scoring, category rotation, and archiving."""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from chocodata import discover as discover_youtube  # noqa: E402
from bilibili import discover as discover_bilibili  # noqa: E402
from douyin import discover as discover_douyin  # noqa: E402
from pipeline.quality import score_source, should_process  # noqa: E402
from utils.config import load_config  # noqa: E402
from utils.state import (  # noqa: E402
    load_state,
    save_state,
    get_known_urls,
    archive_old_sources,
)

ROOT = Path(__file__).resolve().parent.parent

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _get_next_target(cfg, state):
    """Determine the next keyword or category to scrape in round-robin fashion."""
    discovery = cfg.get("discovery", {})
    keywords = discovery.get("keywords")
    if keywords:
        last_kw = state.get("_meta", {}).get("last_keyword")
        if not last_kw or last_kw not in keywords:
            return "keyword", keywords[0]
        next_idx = (keywords.index(last_kw) + 1) % len(keywords)
        return "keyword", keywords[next_idx]

    categories = discovery.get("categories") or ["popular"]
    last_cat = state.get("_meta", {}).get("last_category")
    if not last_cat or last_cat not in categories:
        return "category", categories[0]
    next_idx = (categories.index(last_cat) + 1) % len(categories)
    return "category", categories[next_idx]


def main():
    cfg = load_config()

    prof_name = cfg.get("_active_profile_name", "Default")
    print(f"Running discovery for Active Pipeline Profile: [{prof_name}]")

    discovery = cfg.get("discovery")
    if not discovery or not discovery.get("enabled", True):
        print("Discovery disabled in config")
        return

    state = load_state()

    # 1. Run automatic archiving on sources older than 30 days
    archived = archive_old_sources(state, keep_days=30)
    if archived:
        print(f"State maintenance: Archived {archived} old processed sources")

    strategy = discovery.get("strategy", "bilibili")
    target_type, target_val = _get_next_target(cfg, state)
    current_label = target_val

    # 2. Discover sources based on strategy & keyword/category
    try:
        if strategy == "bilibili":
            if target_type == "keyword":
                print(f"Bilibili discovery feed: Keyword Search -> [{target_val}]")
                found = discover_bilibili(cfg, keyword=target_val)
            else:
                print(f"Bilibili discovery feed: Category Ranking -> [{target_val}]")
                found = discover_bilibili(cfg, category=target_val)
        elif strategy == "douyin":
            print(f"Douyin discovery feed: Topic -> [{target_val}]")
            found = discover_douyin(cfg, keyword=target_val)
        elif strategy == "chinese_apps":
            # Combined Bilibili + Douyin discovery
            print(f"Chinese Apps discovery: Bilibili + Douyin -> [{target_val}]")
            bili_found = discover_bilibili(cfg, keyword=target_val) if target_type == "keyword" else discover_bilibili(cfg, category=target_val)
            dy_found = discover_douyin(cfg, keyword=target_val)
            found = bili_found + dy_found
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
                "category": src.get("category", current_label),
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
    if target_type == "keyword":
        state["_meta"]["last_keyword"] = current_label
    else:
        state["_meta"]["last_category"] = current_label
    save_state(state)
    print(f"Discovery finished: {added} new high-quality sources added.")


if __name__ == "__main__":
    main()