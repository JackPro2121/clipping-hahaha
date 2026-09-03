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
from douyin_apify import discover_douyin_apify  # noqa: E402
from pipeline.creator_discovery import (  # noqa: E402
    discover_bilibili_creators,
    discover_bilibili_creator_accounts,
    discover_douyin_creators,
)
from pipeline.quality import score_source, should_process  # noqa: E402
from utils.config import load_config  # noqa: E402
from utils.state import (  # noqa: E402
    load_state,
    save_state,
    get_known_urls,
    archive_old_sources,
    reap_expired_play_urls,
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


# Niche craft keywords used specifically for creator-account discovery.
# These are separate from (and broader than) the video-search keywords so
# that the user-search API finds channels whose PROFILE NAME contains the
# craft even when their individual video titles vary.
_CREATOR_SEARCH_KW = [
    "木工",        # woodworking
    "手工制作",    # handmade craft
    "老物件修复",  # antique restoration
    "锻造",        # forging / blacksmith
    "传统手艺",    # traditional skill
    "木雕",        # wood carving
    "竹编",        # bamboo weaving
    "修复",        # restoration
]

# Creators whose content or handles represent known off-niche categories (gaming, civil engineering, clinic, etc.)
_BLOCKED_CREATOR_TERMS = [
    "木可雕real", "土木工程", "土木白工", "正骨", "刺血", "中医",
    "沙雕", "动漫", "健身", "搞笑", "解说", "游戏", "吃播"
]

# ── Niche relevance keyword gate (module level so tests can import them) ──
# A video must contain at least ONE _NICHE_KW term to pass, and must contain
# NO _NEGATIVE_KW term. Negative keywords win over positive ones: a palace-park
# workout video titled "宫廷盘杠传承人…非遗正青春" used 非遗/传承 to slip past a
# positive-only gate and reached the Buffer queue as "craft".
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
    "玉", "石雕", "陶", "泥塑", "雕刻", "篆刻", "砚台",
    # Bamboo / fan / weave
    "扇子", "竹编", "编织", "草编", "竹艺",
    # Lamp / lantern / cultural artifact craft
    "灯", "灯笼", "文物", "古董", "老物", "古物",
    # Intangible cultural heritage / traditional skills
    "非遗", "传承", "非物质文化", "传统技艺", "老手艺", "百年工艺",
    # Lacquer / embroidery / paper / leather craft
    "漆器", "漆", "刺绣", "绣花", "皮影", "剪纸", "泥人", "风筝", "蓝染", "蜡染",
    # General craft signals
    "解压手工", "手工制作", "传统工艺", "古法工艺", "民间技艺",
    # English (for translated titles already in English)
    "wood", "carv", "craft", "restor", "knife", "sword", "lathe", "forge",
    "handmade", "repair", "machin", "jade", "bamboo", "weav", "chisel",
    "lamp", "lantern", "relic", "heritage", "lacquer", "embroider", "pottery",
    "antique", "artisan", "traditional", "intangible",
]

_NEGATIVE_KW = [
    # Food / cooking (prevents "美食制作" food prep sneaking in)
    "美食", "做菜", "食谱", "吃播", "料理", "炒菜", "小吃", "甜品", "烹饪",
    # Gaming / Anime / Music
    "游戏", "实况", "动漫", "二次元", "音乐", "唱歌", "舞蹈", "跳舞",
    # General non-craft trivia
    "搞笑", "段子", "免疫系统", "科普", "冷知识", "未解之谜",
    # Fitness / sports / park exercise. The 宫廷盘杠 (palace-park pull-up bar)
    # workout videos claim "非遗/传统技艺" — fitness terms veto them.
    "健身", "强身健体", "单杠", "盘杠", "引体向上", "锻炼", "瑜伽", "跑步",
    "街头健身", "篮球", "足球", "跳绳", "仰卧起坐", "俯卧撑",
    "workout", "fitness", "calisthenics", "pull-up", "gym",
]


def _auto_expand_creators(cfg, state):
    """Auto-discover new Bilibili niche creators every AUTO_EXPAND_EVERY_N runs.

    1. Always merges previously saved `state._meta.auto_creators` into cfg so
       every run benefits from the expanded pool.
    2. Every AUTO_EXPAND_EVERY_N runs it searches Bilibili for new creator
       accounts by craft keywords and saves the results back to state.

    Never raises — failures print a warning and proceed with existing pool.
    """
    META_KEY = "auto_creators"
    RUN_KEY = "auto_creator_run_count"
    AUTO_EXPAND_EVERY_N = 3   # search for new creators every 3 pipeline runs
    MAX_AUTO_CREATORS = 50    # cap the auto pool to avoid config bloat

    meta = state.setdefault("_meta", {})
    run_count = meta.get(RUN_KEY, 0) + 1
    meta[RUN_KEY] = run_count

    # Filter out any blacklisted creator accounts from state auto_pool
    auto_pool = [
        c for c in auto_pool
        if not any(blocked.lower() in str(c).lower() for blocked in _BLOCKED_CREATOR_TERMS)
    ]
    meta[META_KEY] = auto_pool
    existing_curated: list = list(cfg.get("discovery", {}).get("bilibili_creators") or [])
    all_known: set = set(auto_pool) | set(existing_curated)

    # ——— always merge saved auto-creators into cfg for this run ———
    if auto_pool:
        merged = existing_curated + [c for c in auto_pool if c not in existing_curated]
        cfg.setdefault("discovery", {})["bilibili_creators"] = merged
        print(f"  [auto-pool] Loaded {len(auto_pool)} auto-discovered creators into pool "
              f"(total: {len(merged)} creators)")

    # ——— periodically search for new ones ———
    if run_count % AUTO_EXPAND_EVERY_N != 0:
        return  # not time yet

    discovery = cfg.get("discovery", {})
    search_keywords = discovery.get("keywords") or _CREATOR_SEARCH_KW
    # Use a dedicated broader set merged with the profile keywords
    search_terms = list(dict.fromkeys(_CREATOR_SEARCH_KW + list(search_keywords)))[:8]

    print(f"\n  [auto-expand] Run #{run_count}: searching Bilibili for new niche creators "
          f"across {len(search_terms)} keywords ...")
    try:
        found = discover_bilibili_creator_accounts(
            search_terms,
            min_fans=3000,
            min_videos=3,
            max_per_keyword=6,
        )
        new_creators = [
            c for c in found
            if c not in all_known
            and not any(blocked.lower() in str(c).lower() for blocked in _BLOCKED_CREATOR_TERMS)
        ]
        if new_creators:
            # Prepend high-reach creators to front of auto_pool
            auto_pool = new_creators + [c for c in auto_pool if c not in new_creators]
            auto_pool = auto_pool[:MAX_AUTO_CREATORS]
            meta[META_KEY] = auto_pool
            # Patch cfg so the current run immediately benefits
            merged = existing_curated + [c for c in auto_pool if c not in existing_curated]
            cfg["discovery"]["bilibili_creators"] = merged
            print(f"  [auto-expand] +{len(new_creators)} new niche creators added: "
                  + ", ".join(new_creators[:8])
                  + (" ..." if len(new_creators) > 8 else ""))
        else:
            print(f"  [auto-expand] No new niche creators found this scan "
                  f"(pool already has {len(all_known)} unique accounts).")
    except Exception as exc:
        print(f"  [auto-expand] Creator search error (proceeding with existing pool): "
              f"{str(exc)[:120]}")


def main():
    cfg = load_config()

    prof_name = cfg.get("_active_profile_name", "Default")
    print(f"Running discovery for Active Pipeline Profile: [{prof_name}]")

    discovery = cfg.get("discovery")
    if not discovery or not discovery.get("enabled", True):
        print("Discovery disabled in config")
        return

    # Run gate: when any channel queue is at/over the threshold, skip
    # discovery entirely (saves Apify credits; nothing new is needed).
    gate_threshold = cfg.get("buffer", {}).get("run_gate_depth", 8)
    try:
        from buffer_api import get_channels
        from pipeline.queue_manager import get_channel_queue_depth

        channels = get_channels(discovery.get("services") or cfg.get("buffer", {}).get("services") or [])
        full = [
            f"{c['service']}={get_channel_queue_depth(c['id'])}"
            for c in channels
        ]
        full = [x for x in full if int(x.split("=")[1]) >= gate_threshold]
        if full:
            print(f"Run gate: queue >= {gate_threshold} on {', '.join(full)} — skipping discovery")
            return
    except Exception as exc:
        print(f"Discovery run-gate check failed (proceeding anyway): {str(exc)[:100]}")

    # Curated-creator allowlist — captured BEFORE _auto_expand_creators merges
    # auto-discovered accounts into cfg. Auto accounts must NOT inherit the
    # curated niche-filter bypass: a channel NAMED "传统技艺传承人" can still
    # post park-workout videos.
    curated_names = {str(c) for c in (discovery.get("bilibili_creators") or [])}

    state = load_state()

    # Reap douyin sources with expired play_urls BEFORE the backlog gate below.
    # Without this, zombies keep dy_backlog >= 2 and permanently suppress new
    # Apify discovery. (Discovery runs before main.py in the workflow.)
    reaped = reap_expired_play_urls(state)
    if reaped:
        save_state(state)
        print(f"Reaped {len(reaped)} expired play-url source(s): {reaped}")

    # 1. Auto-expand creator pool from Bilibili user search (every 3 runs)
    _auto_expand_creators(cfg, state)

    # 2. Run automatic archiving on sources older than 30 days
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
            dy_backlog = sum(
                1 for s in state["sources"]
                if s.get("status") == "pending" and "douyin.com" in s.get("url", "")
            )
            if os.environ.get("APIFY_TOKEN") and dy_backlog < 2:
                print(f"Douyin discovery feed: Apify 1080p Search -> [{target_val}]")
                found = discover_douyin_apify(cfg, keyword=target_val)
            elif os.environ.get("APIFY_TOKEN"):
                print(f"douyin_apify skipped: {dy_backlog} douyin sources already pending")
                found = []
            elif discovery.get("douyin_creator_profiles"):
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
            if os.environ.get("APIFY_TOKEN"):
                # Apify credits + play URLs (~1h expiry) are wasted if we keep
                # scraping while older douyin sources are still unprocessed.
                dy_backlog = sum(
                    1 for s in state["sources"]
                    if s.get("status") == "pending" and "douyin.com" in s.get("url", "")
                )
                if dy_backlog < 2:
                    dy_found = discover_douyin_apify(cfg, keyword=target_val)
                else:
                    print(f"douyin_apify skipped: {dy_backlog} douyin sources already pending")
                    dy_found = []
            else:
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
    # Niche relevance filter — craft/woodworking/restoration keyword gate.
    # Keyword lists (_NICHE_KW / _NEGATIVE_KW) live at module level so tests
    # can exercise them directly. Negative keywords ALWAYS win.
    # ---------------------------------------------------------------------------

    def _is_niche_relevant(title: str) -> bool:
        """Return True if title contains at least one niche craft keyword and no negative keywords."""
        t = title.lower()
        if any(neg.lower() in t for neg in _NEGATIVE_KW):
            return False
        return any(kw.lower() in t for kw in _NICHE_KW)

    # Meta-moderation safety gate — accident/injury/dangerous-act content got
    # the Facebook page restricted and age-flagged. Rejected BEFORE scoring so
    # nothing unsafe ever enters sources.json.
    def _is_meta_safe(title: str) -> bool:
        from llm.safety import classify_content_safety

        verdict = classify_content_safety(title, use_llm=False)
        if not verdict["safe"]:
            print(f"  [safety-skip] {verdict['reason'][:80]} :: {title[:50]}")
            return False
        return True

    # 3. Quality score and filter candidate videos
    safety_cfg = cfg.get("safety", {})
    relevance_llm_on = safety_cfg.get("enabled", True) and safety_cfg.get("relevance_llm", True)
    relevance_budget = int(safety_cfg.get("relevance_llm_max_calls", 8)) if relevance_llm_on else 0

    scored_candidates = []
    for src in found:
        if src["url"] in known_urls:
            continue

        # Niche gate — negative keywords ALWAYS veto (fitness/workout/food…).
        # Non-creator sources additionally need one positive craft keyword.
        # Curated-creator videos skip the positive-keyword requirement (their
        # catalogue is manually vetted) but still face the negative veto here
        # AND the LLM relevance check below — a channel NAMED "传统技艺传承人"
        # can still post palace-park workout videos.
        title = src.get("title", "")
        category = src.get("category", "")
        creator_name = category[len("creator_"):] if category.startswith("creator_") else None
        if creator_name and any(b.lower() in creator_name.lower() for b in _BLOCKED_CREATOR_TERMS):
            print(f"  [creator-skip] Blacklisted creator account: {creator_name}")
            continue

        t_lower = title.lower()
        if any(neg.lower() in t_lower for neg in _NEGATIVE_KW):
            print(f"  [niche-skip] Negative keyword: {title[:70]}")
            continue
        if creator_name is None and not _is_niche_relevant(title):
            print(f"  [niche-skip] Off-topic title: {title[:70]}")
            continue

        # Moderation gate — reject accident/injury/dangerous-act content
        if not _is_meta_safe(title):
            continue

        # For verified curated creators, relax min_views so freshly published clips get captured first!
        # Apify douyin sources: free tier doesn't expose playCount — gate on niche + duration instead.
        if src.get("origin") == "douyin_apify":
            min_views = 0
        elif src.get("category", "").startswith("creator_"):
            min_views = discovery.get("creator_min_views", 1500)
        else:
            min_views = discovery.get("min_views", 30000)
        if src.get("views", 0) < min_views:
            continue

        # LLM relevance veto — keywords cannot judge MEANING ("宫廷盘杠传承人…
        # 非遗正青春" is park calisthenics, not a craft). Budget-limited so a
        # discovery run never explodes in LLM latency; fails open on LLM errors.
        if relevance_llm_on and relevance_budget > 0:
            relevance_budget -= 1
            try:
                from llm.safety import classify_relevance

                rel = classify_relevance(title, use_llm=True)
            except Exception:
                rel = {"relevant": True, "reason": "import failed", "source": "failopen"}
            if not rel["relevant"]:
                print(f"  [relevance-skip] {rel['reason'][:60]} :: {title[:50]}")
                continue
            # If LLM failed open, creator video must still satisfy positive craft check
            if creator_name is not None and rel.get("source") in ("failopen", "disabled"):
                if not _is_niche_relevant(title):
                    print(f"  [niche-skip] Off-topic creator video (LLM failopen): {title[:70]}")
                    continue
        elif creator_name is not None:
            # LLM budget exhausted (or disabled) — creator videos fall back to
            # requiring a positive craft keyword like any other source.
            if not _is_niche_relevant(title):
                print(f"  [niche-skip] Off-topic creator video: {title[:70]}")
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
        entry = {
            "url": src["url"],
            "title": src.get("title", ""),
            "status": "pending",
            "score": score,
            "category": src.get("category", current_label),
            "discovered_at": now_iso,
            "retry_count": 0,
        }
        # Apify douyin sources carry a ~1h-lived signed play URL for same-run download
        if src.get("play_url"):
            entry["play_url"] = src["play_url"]
        state["sources"].append(entry)
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
                if not _is_meta_safe(fb_title):
                    continue
                min_views_fb = discovery.get("min_views", 30000)
                if src.get("views", 0) < min_views_fb:
                    continue
                fb_score = score_source(src)
                if fb_score >= min_score:
                    fallback_candidates.append((fb_score, src))

            fallback_candidates.sort(key=lambda x: x[0], reverse=True)
            for fb_score, src in fallback_candidates:
                entry = {
                    "url": src["url"],
                    "title": src.get("title", ""),
                    "status": "pending",
                    "score": fb_score,
                    "category": f"keyword_{fallback_kw}",
                    "discovered_at": now_iso,
                    "retry_count": 0,
                }
                if src.get("play_url"):
                    entry["play_url"] = src["play_url"]
                state["sources"].append(entry)
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