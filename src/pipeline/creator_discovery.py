"""creator_discovery.py — Apify & Public API powered creator discovery for Bilibili and Douyin.

Uses two approaches:
  1. themineworks/bilibili-scraper (Apify) or direct Bilibili space search API : keyword search → extract top creator UIDs
  2. toolzerhub/douyin-profile-videos-scraper (Apify) or curated seed creator profiles : profile URL → latest clean video URLs

Bilibili creator video fetching uses the public Bilibili space API (no auth needed).
Douyin video fetching extracts clean no-watermark URLs.
"""

import os
import time
import requests

_APIFY_API = "https://api.apify.com/v2"
_BILIBILI_SPACE_API = "https://api.bilibili.com/x/space/arc/search"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# ---------------------------------------------------------------------------
# Apify helpers
# ---------------------------------------------------------------------------

def _apify_run_and_wait(actor_slug, run_input, timeout_polls=90, poll_interval=5):
    """Start an Apify actor run, poll until done, return dataset items list."""
    token = os.environ.get("APIFY_TOKEN", "")
    if not token:
        raise RuntimeError("APIFY_TOKEN not set")

    actor_path = actor_slug.replace("/", "~")
    resp = requests.post(
        f"{_APIFY_API}/acts/{actor_path}/runs",
        params={"token": token},
        json=run_input,
        timeout=60,
    )
    resp.raise_for_status()
    run_id = resp.json().get("data", {}).get("id")
    if not run_id:
        raise RuntimeError(f"Apify actor did not start: {resp.text[:200]}")

    print(f"  Apify run started: {actor_slug} | run_id={run_id}")

    # Poll for completion
    status = "RUNNING"
    for _ in range(timeout_polls):
        time.sleep(poll_interval)
        try:
            st = requests.get(
                f"{_APIFY_API}/actor-runs/{run_id}",
                params={"token": token},
                timeout=30,
            ).json().get("data", {})
            status = st.get("status", "RUNNING")
        except requests.RequestException:
            continue
        if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED_OUT"):
            break

    if status != "SUCCEEDED":
        raise RuntimeError(f"Apify run {run_id} ended with status: {status}")

    # Retrieve dataset items
    items = requests.get(
        f"{_APIFY_API}/actor-runs/{run_id}/dataset/items",
        params={"token": token, "limit": 200},
        timeout=60,
    ).json()
    return items if isinstance(items, list) else []


# ---------------------------------------------------------------------------
# Bilibili creator discovery
# ---------------------------------------------------------------------------

def _fetch_bilibili_creator_videos(mid, max_count=5, min_duration_s=35, max_duration_s=600):
    """Fetch latest videos from a Bilibili creator via public space API (no auth)."""
    sources = []
    try:
        resp = requests.get(
            _BILIBILI_SPACE_API,
            params={"mid": mid, "ps": 30, "pn": 1, "order": "pubdate"},
            headers={"User-Agent": _UA, "Referer": "https://www.bilibili.com/"},
            timeout=20,
        )
        if resp.status_code != 200:
            return sources
        data = resp.json().get("data", {}) or {}
        vlist = data.get("list", {}).get("vlist") or []
        for v in vlist:
            if len(sources) >= max_count:
                break
            bvid = v.get("bvid")
            if not bvid:
                continue

            raw_len = v.get("length", "")
            if isinstance(raw_len, str) and ":" in raw_len:
                parts = raw_len.split(":")
                try:
                    if len(parts) == 2:
                        length = int(parts[0]) * 60 + int(parts[1])
                    elif len(parts) == 3:
                        length = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                    else:
                        length = 0
                except ValueError:
                    length = 0
            else:
                length = int(raw_len) if str(raw_len).isdigit() else 0

            if length < min_duration_s or (max_duration_s and length > max_duration_s):
                continue
            sources.append({
                "url": f"https://www.bilibili.com/video/{bvid}",
                "title": v.get("title") or bvid,
                "views": int(v.get("play") or 0),
                "length": length,
                "category": f"bilibili_creator_{mid}",
            })
    except Exception as exc:
        print(f"  Bilibili space API error for mid={mid}: {exc}")
    return sources


def discover_bilibili_creators(cfg, max_creators=5, max_videos_per_creator=2):
    """Use Apify or configured UIDs to find top craft creators and their latest videos."""
    discovery = cfg.get("discovery", {})
    configured_mids = discovery.get("bilibili_creator_uids", [])
    min_duration_s = discovery.get("min_source_duration_s", 35)
    max_duration_s = discovery.get("max_duration_s", 600)

    # 1. Direct configured UIDs (high performance, 0-cost, 100% reliable)
    seen_mids = list(configured_mids)

    # 2. If no configured UIDs and APIFY_TOKEN exists, discover via Apify scraper
    if not seen_mids and os.environ.get("APIFY_TOKEN"):
        keywords = discovery.get("keywords", ["木工", "老物件修复", "手工制作"])
        search_keywords = keywords[:2]
        print(f"Bilibili creator discovery via Apify: keywords={search_keywords}")
        try:
            items = _apify_run_and_wait(
                "themineworks/bilibili-scraper",
                {
                    "keywords": search_keywords,
                    "maxResultsPerKeyword": 30,
                    "type": "video",
                },
                timeout_polls=45,
                poll_interval=5,
            )
            for item in items:
                if not isinstance(item, dict):
                    continue
                mid = str(item.get("mid") or item.get("author_id") or item.get("upMid") or "")
                if mid and mid not in seen_mids:
                    seen_mids.append(mid)
                if len(seen_mids) >= max_creators:
                    break
        except Exception as exc:
            print(f"  Apify Bilibili scraper fallback: {exc}")

    print(f"  Targeting {len(seen_mids)} Bilibili creators: {seen_mids}")

    # Fetch latest videos from each creator
    all_sources = []
    for mid in seen_mids[:max_creators]:
        videos = _fetch_bilibili_creator_videos(
            mid,
            max_count=max_videos_per_creator,
            min_duration_s=min_duration_s,
            max_duration_s=max_duration_s,
        )
        all_sources.extend(videos)

    return all_sources


# ---------------------------------------------------------------------------
# Douyin creator discovery
# ---------------------------------------------------------------------------

def discover_douyin_creators(cfg, max_videos_per_creator=2):
    """Use Apify douyin-profile-videos-scraper to get latest videos from seed creators."""
    discovery = cfg.get("discovery", {})
    min_duration_s = discovery.get("min_source_duration_s", 15)
    max_duration_s = discovery.get("max_duration_s", 600)

    profile_urls = discovery.get("douyin_creator_profiles", [])
    real_profiles = [u for u in profile_urls if "placeholder" not in u]
    if not real_profiles:
        return []

    if not os.environ.get("APIFY_TOKEN"):
        print("  APIFY_TOKEN not set, skipping Douyin creator profile scraping")
        return []

    print(f"Douyin creator discovery via Apify: {len(real_profiles)} profiles")
    all_sources = []

    for profile_url in real_profiles[:3]:
        try:
            print(f"  Scraping Douyin profile: {profile_url}")
            items = _apify_run_and_wait(
                "toolzerhub/douyin-profile-videos-scraper",
                {
                    "profileUrls": [profile_url],
                    "maxVideos": 10,
                },
                timeout_polls=45,
                poll_interval=5,
            )
        except Exception as exc:
            print(f"  Apify Douyin scraper failed for {profile_url}: {exc}")
            continue

        added = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            if added >= max_videos_per_creator:
                break

            video_url = (
                item.get("playAddr")
                or item.get("downloadAddr")
                or item.get("video", {}).get("playAddr")
                or ""
            )
            if not video_url:
                continue

            clean_url = video_url.replace("/playwm/", "/play/")
            aweme_id = str(item.get("id") or item.get("awemeId") or "")
            title = (item.get("desc") or item.get("title") or "").strip()
            duration_ms = item.get("duration") or item.get("video", {}).get("duration") or 0
            duration_s = round(int(duration_ms) / 1000) if duration_ms else 30

            if duration_s < min_duration_s or (max_duration_s and duration_s > max_duration_s):
                continue

            canonical_url = f"https://www.douyin.com/video/{aweme_id}" if aweme_id else clean_url

            all_sources.append({
                "url": canonical_url,
                "title": title or "Satisfying Craft",
                "views": int(item.get("diggCount") or item.get("stats", {}).get("diggCount") or 50000),
                "length": duration_s,
                "category": "douyin_creator",
                "_direct_url": clean_url,
            })
            added += 1

    return all_sources
