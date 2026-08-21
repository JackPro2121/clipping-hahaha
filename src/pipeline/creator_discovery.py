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

def _parse_len(raw_len):
    if isinstance(raw_len, (int, float)):
        return int(raw_len)
    if not raw_len or not isinstance(raw_len, str):
        return 0
    parts = raw_len.strip().split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        return int(parts[0])
    except (ValueError, IndexError):
        return 0


def _fetch_bilibili_creator_videos(creator_target, max_count=3, min_duration_s=35, max_duration_s=600):
    """Fetch latest videos from a Bilibili creator name or UID via public search API."""
    import tempfile
    import urllib.parse
    from pathlib import Path
    from download import _bili_headers

    sources = []
    try:
        with tempfile.TemporaryDirectory() as td:
            headers, _ = _bili_headers(Path(td))
            kw_enc = urllib.parse.quote(str(creator_target))
            url = (
                f"https://api.bilibili.com/x/web-interface/search/type"
                f"?search_type=video&keyword={kw_enc}&order=click&page=1"
            )
            resp = requests.get(url, headers=headers, timeout=20)
            if resp.status_code != 200:
                return sources
            data = resp.json().get("data", {}) or {}
            items = data.get("result", []) or []
            for item in items:
                if len(sources) >= max_count:
                    break
                bvid = item.get("bvid")
                if not bvid:
                    continue

                raw_title = item.get("title", "").replace('<em class="keyword">', "").replace("</em>", "").strip()
                length = _parse_len(item.get("duration"))
                views = int(item.get("play") or 0)

                if length < min_duration_s or (max_duration_s and length > max_duration_s):
                    continue

                sources.append({
                    "url": f"https://www.bilibili.com/video/{bvid}",
                    "title": raw_title or bvid,
                    "views": views,
                    "length": length,
                    "category": f"creator_{creator_target}",
                })
    except Exception as exc:
        print(f"  Bilibili creator video fetch error for '{creator_target}': {exc}")
    return sources


def discover_bilibili_creators(cfg, max_creators=6, max_videos_per_creator=2):
    """Discover candidate videos from curated craft creators."""
    discovery = cfg.get("discovery", {})
    configured_creators = (
        discovery.get("bilibili_creators")
        or discovery.get("bilibili_creator_uids")
        or [
            "才疏学浅的才浅",
            "手工耿",
            "阿木爷爷",
            "王小师傅1",
            "苏清吾",
            "玉师傅手工匠人",
            "我的修复师",
            "听雨剑阁",
            "机械造型",
        ]
    )
    min_duration_s = discovery.get("min_source_duration_s", 35)
    max_duration_s = discovery.get("max_duration_s", 600)

    print(f"  Targeting {len(configured_creators)} verified Bilibili craft masters")

    all_sources = []
    for target in configured_creators[:max_creators]:
        videos = _fetch_bilibili_creator_videos(
            target,
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
