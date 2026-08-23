"""douyin_apify.py — $0 Douyin discovery via Apify (zen-studio/douyin-search-scraper).

Discovers native vertical 1080x1920 Douyin videos by craft keyword and returns a
fresh CDN play_url per source. The play URL is signed and expires in ~1 hour, so
it must be consumed in the same workflow run (find_sources -> main runs back to
back). Falls back gracefully when APIFY_TOKEN is missing or the run fails.
"""

import os
import time
from pathlib import Path

import requests

_APIFY_API = "https://api.apify.com/v2"
_ACTOR = "zen-studio~douyin-search-scraper"

# Mobile UA — the amemv/douyinvod CDNs serve the mp4 without cookies for this client
_UA_MOBILE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
)


def map_apify_item(item):
    """Map one Apify dataset item to a pipeline source dict.

    Returns None when the item is not usable (not a video, no play URL, or
    duration out of range). Pure function — unit-testable without network.
    """
    if not isinstance(item, dict):
        return None
    item_type = item.get("type")
    if item_type is not None:
        if item_type != "video":
            return None
    elif item.get("mediaTypeLabel") != "video":
        return None

    vm = item.get("videoMeta") or {}
    aweme_id = item.get("id") or item.get("groupId")
    # Prefer playUrl (no-watermark api-play endpoint); downloadUrl is the fallback
    play_url = vm.get("playUrl") or vm.get("downloadUrl")
    if not aweme_id or not play_url:
        return None

    duration_s = round((vm.get("duration") or 0) / 1000, 1)

    return {
        "url": f"https://www.douyin.com/video/{aweme_id}",
        "title": (item.get("text") or item.get("caption") or "").strip(),
        "views": (item.get("statistics") or {}).get("playCount") or 0,
        "length": int(duration_s),
        "category": "douyin_apify",
        "origin": "douyin_apify",
        "play_url": play_url,
        "resolution": f"{vm.get('width')}x{vm.get('height')}" if vm.get("width") else None,
    }


def discover_douyin_apify(cfg, keyword=None, timeout_s=300):
    """Run one Apify search scrape and return filtered douyin sources.

    Args:
        cfg: Full pipeline config (reads discovery.douyin_apify_max_items).
        keyword: Chinese craft search term; falls back to first discovery keyword.
        timeout_s: Max seconds to wait for the Apify run.

    Returns:
        list of source dicts (possibly empty on any failure — never raises).
    """
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        print("douyin_apify: APIFY_TOKEN not set — skipping Apify discovery")
        return []

    discovery = cfg.get("discovery", {})
    keywords = discovery.get("keywords") or []
    term = keyword or (keywords[0] if keywords else None)
    if not term:
        print("douyin_apify: no search term available — skipping")
        return []
    max_items = discovery.get("douyin_apify_max_items", 8)

    try:
        resp = requests.post(
            f"{_APIFY_API}/acts/{_ACTOR}/run-sync-get-dataset-items",
            params={"token": token, "timeout": timeout_s * 1000},
            json={
                "keywords": [term],
                "maxResultsPerQuery": max_items,
                "sort": "general",
            },
            timeout=timeout_s + 30,
        )
        resp.raise_for_status()
        items = resp.json() or []
    except Exception as exc:
        print(f"douyin_apify: scrape failed: {str(exc)[:160]}")
        return []

    min_dur = discovery.get("min_source_duration_s", 40)
    max_dur = discovery.get("max_duration_s", 900)
    found = []
    for item in items:
        src = map_apify_item(item)
        if not src:
            continue
        if not (min_dur <= src["length"] <= max_dur):
            continue
        found.append(src)

    print(f"douyin_apify: {len(found)} usable sources for [{term}] "
          f"(resolutions: {sorted({s['resolution'] for s in found if s['resolution']})})")
    return found


def download_douyin_direct(play_url, dest_path):
    """Stream-download a douyin CDN play URL with retries.

    Args:
        play_url: Signed CDN url from videoMeta (expires ~1h after scraping).
        dest_path: Output Path for the mp4.

    Raises:
        RuntimeError: On repeated failure or an invalid (too small) file.
    """
    dest_path = Path(dest_path)
    last = ""
    for attempt in range(3):
        try:
            with requests.get(
                play_url, headers={"User-Agent": _UA_MOBILE}, stream=True, timeout=60
            ) as resp:
                resp.raise_for_status()
                with open(dest_path, "wb") as fh:
                    for chunk in resp.iter_content(1024 * 1024):
                        fh.write(chunk)
            size = dest_path.stat().st_size
            if size >= 200_000:
                return size
            last = f"stream too small ({size}B)"
        except Exception as exc:
            last = str(exc)[:160]
        time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"douyin direct download failed: {last}")
