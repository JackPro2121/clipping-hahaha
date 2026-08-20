"""douyin.py — $0 Douyin (TikTok China) No-Watermark Video Extractor.

Extracts raw 1080p/720p MP4 streams from Douyin share links without watermarks.
Works by resolving the short URL to aweme_id, querying the public item endpoint,
and transforming the CDN stream URL from 'playwm' (with watermark) to 'play' (clean).
"""

import re
import urllib.parse
from pathlib import Path
import requests

_UA_MOBILE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
)

_DOUYIN_SHARE_RE = re.compile(r"(https?://v\.douyin\.com/[A-Za-z0-9]+)")
_DOUYIN_VIDEO_ID_RE = re.compile(r"(?:video|note)/([0-9]+)")


def extract_douyin_video_id(url_or_text):
    """Extract the numeric Aweme video ID from a Douyin URL or share text."""
    if not url_or_text:
        return None

    # 1. Match direct numeric video ID in standard URL
    m = _DOUYIN_VIDEO_ID_RE.search(str(url_or_text))
    if m:
        return m.group(1)

    # 2. Resolve short share URL (v.douyin.com/...)
    m_share = _DOUYIN_SHARE_RE.search(str(url_or_text))
    if m_share:
        short_url = m_share.group(1)
        try:
            resp = requests.get(
                short_url,
                headers={"User-Agent": _UA_MOBILE},
                allow_redirects=True,
                timeout=15,
            )
            redirected_url = resp.url
            m_id = _DOUYIN_VIDEO_ID_RE.search(redirected_url)
            if m_id:
                return m_id.group(1)
        except Exception as exc:
            print(f"Douyin short link resolution failed: {exc}")

    return None


def get_no_watermark_url(raw_play_url):
    """Convert a Douyin CDN video URL with watermark ('playwm') to clean ('play')."""
    if not raw_play_url:
        return ""
    # Replace 'playwm' with 'play' in the path
    clean = re.sub(r"/playwm/", "/play/", str(raw_play_url))
    return clean


def fetch_douyin_video_info(aweme_id):
    """Fetch video metadata and clean no-watermark stream URL from Douyin."""
    if not aweme_id:
        return None

    api_url = f"https://www.iesdouyin.com/web/api/v2/aweme/iteminfo/?item_ids={aweme_id}"
    try:
        resp = requests.get(
            api_url,
            headers={"User-Agent": _UA_MOBILE},
            timeout=15,
        )
        if resp.status_code != 200:
            return None

        data = resp.json() or {}
        item_list = data.get("item_list") or []
        if not item_list:
            return None

        item = item_list[0]
        title = (item.get("desc") or "").strip()
        author = item.get("author", {}).get("nickname", "DouyinCreator")
        duration_ms = item.get("duration", 0)
        duration_s = round(duration_ms / 1000, 1) if duration_ms else 0

        # Video stream extraction
        video_data = item.get("video", {})
        play_addr = video_data.get("play_addr", {})
        url_list = play_addr.get("url_list") or []
        if not url_list:
            return None

        raw_url = url_list[0]
        clean_url = get_no_watermark_url(raw_url)

        return {
            "aweme_id": aweme_id,
            "title": title,
            "author": author,
            "duration": duration_s,
            "clean_video_url": clean_url,
        }
    except Exception as exc:
        print(f"Failed to fetch Douyin video info for {aweme_id}: {exc}")
        return None


def download_douyin_video(url, out_dir):
    """Download a watermark-free Douyin video directly to out_dir.

    Args:
        url: Douyin URL or share string.
        out_dir: Path to directory where {aweme_id}.mp4 will be saved.

    Returns:
        Path: Path to the downloaded clean MP4 file.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    aweme_id = extract_douyin_video_id(url)
    if not aweme_id:
        raise RuntimeError(f"Could not extract Douyin video ID from: {url}")

    info = fetch_douyin_video_info(aweme_id)
    if not info or not info.get("clean_video_url"):
        raise RuntimeError(f"Could not fetch clean video URL for Douyin ID: {aweme_id}")

    clean_url = info["clean_video_url"]
    out_path = out_dir / f"douyin_{aweme_id}.mp4"

    # Stream download with proper mobile headers
    resp = requests.get(
        clean_url,
        headers={"User-Agent": _UA_MOBILE},
        stream=True,
        timeout=30,
    )
    resp.raise_for_status()

    with open(out_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1024 * 1024):
            if chunk:
                f.write(chunk)

    if not out_path.exists() or out_path.stat().st_size < 10000:
        raise RuntimeError(f"Douyin downloaded file is invalid or empty: {out_path}")

    print(f"Download OK via 'douyin' -> {out_path.name} ({out_path.stat().st_size // 1024 // 1024}MB)")
    return out_path


# Curated Douyin satisfying craft keywords and high-performing video topics
DOUYIN_CRAFT_TOPICS = [
    {"keyword": "木工手艺", "title": "Traditional Chinese Woodworking Mastery", "category": "woodworking"},
    {"keyword": "沉浸式修复", "title": "Immersive Antique Restoration ASMR", "category": "restoration"},
    {"keyword": "解压手工", "title": "Oddly Satisfying Precision Craft", "category": "crafts"},
    {"keyword": "机械制造", "title": "Satisfying Precision Machine Factory", "category": "machining"},
]


def discover(cfg, keyword=None):
    """Discover candidate Douyin videos matching active craft profile."""
    discovery = cfg.get("discovery", {})
    max_new = discovery.get("max_new_sources", 2)

    found = []
    # If custom douyin URLs provided in config
    custom_urls = discovery.get("douyin_urls", [])
    for url in custom_urls[:max_new]:
        aweme_id = extract_douyin_video_id(url)
        if aweme_id:
            info = fetch_douyin_video_info(aweme_id)
            if info:
                found.append({
                    "url": f"https://www.douyin.com/video/{aweme_id}",
                    "title": info.get("title") or "Satisfying Douyin Craft",
                    "views": 100000,
                    "length": int(info.get("duration", 45)),
                    "category": "douyin_craft",
                })
    return found
