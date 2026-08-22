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
from pipeline.creator_discovery import (  # noqa: E402
    discover_bilibili_creators,
    discover_douyin_creators,
)
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

    # 2. Discover sources based on strategy & keyword/category/creators
    try:
        if strategy == "creators" or strategy == "creator":
            print(f"Creator-targeted discovery feed: Bilibili + Douyin top creators")
            bili_creators = discover_bilibili_creators(cfg)
            dy_creators = discover_douyin_creators(cfg)
            found = bili_creators + dy_creators
        elif strategy == "bilibili":
            # If explicit creators configured, prioritize them
            if discovery.get("bilibili_creators") or discovery.get("bilibili_creator_uids"):
                print(f"Bilibili discovery feed: Curated Creators Pool")
                found = discover_bilibili_creators(cfg)
            elif target_type == "keyword":
                print(f"Bilibili discovery feed: Keyword Search -> [{target_val}]")
                found = discover_bilibili(cfg, keyword=target_val)
            else:
                print(f"Bilibili discovery feed: Category Ranking -> [{target_val}]")
                found = discover_bilibili(cfg, category=target_val)
        elif strategy == "douyin":
            if discovery.get("douyin_creator_profiles"):
                print(f"Douyin discovery feed: Seed Profiles")
                found = discover_douyin_creators(cfg)
            else:
                print(f"Douyin discovery feed: Topic -> [{target_val}]")
                found = discover_douyin(cfg, keyword=target_val)
        elif strategy == "chinese_apps":
            # Combined Bilibili + Douyin discovery
            print(f"Chinese Apps discovery: Bilibili + Douyin -> [{target_val}]")
            bili_found = (
                discover_bilibili_creators(cfg)
                if (discovery.get("bilibili_creators") or discovery.get("bilibili_creator_uids"))
                else (
                    discover_bilibili(cfg, keyword=target_val)
                    if target_type == "keyword"
                    else discover_bilibili(cfg, category=target_val)
                )
            )
            dy_found = (
                discover_douyin_creators(cfg)
                if discovery.get("douyin_creator_profiles")
                else discover_douyin(cfg, keyword=target_val)
            )
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

    # ---------------------------------------------------------------------------
    # Niche relevance filter — craft/woodworking/restoration keyword gate
    # A video must contain at least ONE keyword to pass. This prevents off-niche
    # content from curated creators (curiosity channels, animation, science trivia)
    # from entering the queue even if they pass view/quality thresholds.
    # ---------------------------------------------------------------------------
    _NICHE_KW = [
        # Woodworking / carpentry (Chinese)
        "木工", "木头", "木板", "木雕", "榫卯", "实木", "原木", "木料", "木作", "木匠",
        # Hand tools / blade / sword
        "手工", "刀", "剑", "刃", "锻造", "手艺", "匠", "锉刀", "凿子", "斧头",
        # Restoration / repair
        "修复", "修缮", "复原", "翻新", "旧物", "老物件", "修理", "还原",
        # Metalwork / machining
        "机械", "机床", "车床", "铸造", "焊接", "金属", "铁", "钢铁",
        # Stone / jade / clay craft
        "玉", "石雕", "陶", "泥塑", "雕刻", "篆刻",
        # Bamboo / fan / weave
        "扇子", "竹编", "编织", "草编", "竹艺",
        # General craft signals
        "解压", "手工制作", "制作", "工艺", "传统", "古法", "民间技艺",
        # English (for translated titles already in English)
        "wood", "carv", "craft", "restor", "knife", "sword", "lathe", "forge",
        "handmade", "repair", "machin", "jade", "bamboo", "weav", "chisel",
    ]

    def _is_niche_relevant(title: str) -> bool:
        """Return True if title contains at least one niche craft keyword."""
        t = title.lower()
        return any(kw.lower() in t for kw in _NICHE_KW)

    # 3. Quality score and filter candidate videos

    scored_candidates = []
    for src in found:
        if src["url"] in known_urls:
            continue

        # Niche gate — reject off-topic titles before any further processing
        title = src.get("title", "")
        if not _is_niche_relevant(title):
            print(f"  [niche-skip] Off-topic title: {title[:70]}")
            continue

        # For verified curated creators, relax min_views so freshly published clips get captured first!
        min_views = (
            discovery.get("creator_min_views", 1500)
            if src.get("category", "").startswith("creator_")
            else discovery.get("min_views", 30000)
        )
        if src.get("views", 0) < min_views:
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

    # ---------------------------------------------------------------------------
    # Keyword fallback — fires ONLY when creator pool yields 0 niche-relevant sources.
    # Searches Bilibili directly by craft keyword so the Buffer queue never runs dry.
    # ---------------------------------------------------------------------------
    if added == 0 and discovery.get("keywords"):
        keywords = discovery["keywords"]
        # Pick the keyword after the last one used (round-robin, same as normal)
        last_kw = state.get("_meta", {}).get("last_keyword")
        if last_kw and last_kw in keywords:
            fallback_kw = keywords[(keywords.index(last_kw) + 1) % len(keywords)]
        else:
            fallback_kw = keywords[0]

        print(f"\n  [fallback] Creator pool: 0 niche hits → keyword search: [{fallback_kw}]")
        try:
            fallback_found = discover_bilibili(cfg, keyword=fallback_kw)
            fallback_candidates = []
            for src in fallback_found:
                if src["url"] in known_urls:
                    continue
                fb_title = src.get("title", "")
                if not _is_niche_relevant(fb_title):
                    continue
                min_views_fb = discovery.get("min_views", 30000)
                if src.get("views", 0) < min_views_fb:
                    continue
                fb_score = score_source(src)
                if fb_score >= min_score:
                    fallback_candidates.append((fb_score, src))

            fallback_candidates.sort(key=lambda x: x[0], reverse=True)
            for fb_score, src in fallback_candidates:
                state["sources"].append(
                    {
                        "url": src["url"],
                        "title": src.get("title", ""),
                        "status": "pending",
                        "score": fb_score,
                        "category": f"keyword_{fallback_kw}",
                        "discovered_at": now_iso,
                        "retry_count": 0,
                    }
                )
                known_urls.add(src["url"])
                added += 1
                print(f"  [fallback] Added ({fb_score}/100 pts): {src['title'][:60]}")
                if added >= max_new:
                    break

            if added > 0:
                state["_meta"]["last_keyword"] = fallback_kw
                print(f"  [fallback] Keyword search rescued run: {added} source(s) added.")
            else:
                print(f"  [fallback] Keyword search also yielded 0 niche sources — run skipped.")
        except Exception as exc:
            print(f"  [fallback] Keyword search failed: {exc}")

    # 4. Update metadata and save state
    if target_type == "keyword":
        state["_meta"]["last_keyword"] = current_label
    else:
        state["_meta"]["last_category"] = current_label
    save_state(state)
    print(f"Discovery finished: {added} new high-quality sources added.")


if __name__ == "__main__":
    main()