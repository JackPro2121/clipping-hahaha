"""
bilibili_subtitles.py — Fetch AI/uploader subtitle tracks from bilibili's player API.

Two public functions:
    fetch_bilibili_subtitles(bvid, headers=None)  → list[segment] | None
    make_title_captions(title, total_duration)    → list[segment] | None

A "segment" is: {"start": float, "duration": float, "text": str}
This matches exactly the format that clip.py's build_subtitles() expects.
"""

import re

import requests

_API = "https://api.bilibili.com"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
_BILI_RE = re.compile(r"bilibili\.com/video/(BV[\w]+)", re.IGNORECASE)


def _make_headers():
    """Minimal headers for bilibili's API endpoints — no spi fingerprint needed here."""
    return {
        "User-Agent": _UA,
        "Referer": "https://www.bilibili.com/",
        "Origin": "https://www.bilibili.com",
    }


def _get_cid(bvid, headers):
    """Return the first part's cid for a given bvid, or None on failure."""
    try:
        resp = requests.get(
            f"{_API}/x/player/pagelist",
            params={"bvid": bvid},
            headers=headers,
            timeout=30,
        )
        pages = (resp.json() or {}).get("data") or []
        if not pages:
            return None
        return pages[0]["cid"]
    except Exception:
        return None


def _fetch_subtitle_url(bvid, cid, headers):
    """
    Call /x/player/v2 to get the subtitle list.
    Returns the URL of the first available subtitle track, or None.
    """
    try:
        resp = requests.get(
            f"{_API}/x/player/v2",
            params={"bvid": bvid, "cid": cid},
            headers=headers,
            timeout=30,
        )
        data = (resp.json() or {}).get("data") or {}
        subtitle_list = data.get("subtitle", {}).get("subtitles") or []
        if not subtitle_list:
            return None
        sub_url = subtitle_list[0].get("subtitle_url") or ""
        if sub_url.startswith("//"):
            sub_url = "https:" + sub_url
        return sub_url or None
    except Exception:
        return None


def _parse_subtitle_file(url, headers):
    """
    Download and parse a bilibili subtitle JSON file.
    Format: {"body": [{"from": float, "to": float, "content": str}, ...]}
    Returns list of segments or None.
    """
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        body = (resp.json() or {}).get("body") or []
        if not body:
            return None
        segments = []
        for item in body:
            start = item.get("from")
            end = item.get("to")
            text = str(item.get("content") or "").strip()
            if start is None or end is None or not text:
                continue
            duration = float(end) - float(start)
            if duration < 0.1:
                continue
            segments.append(
                {"start": float(start), "duration": duration, "text": text}
            )
        return segments or None
    except Exception:
        return None


def fetch_bilibili_subtitles(bvid, headers=None):
    """
    Attempt to fetch AI/uploader subtitle segments for a bilibili video.

    Args:
        bvid: The BV ID string (e.g. "BV1bM8E6yEYd").
        headers: Optional pre-built request headers. If None, minimal headers are used.

    Returns:
        List of {"start", "duration", "text"} dicts, or None if unavailable.
    """
    if headers is None:
        headers = _make_headers()

    cid = _get_cid(bvid, headers)
    if not cid:
        print(f"bilibili subtitles: could not get cid for {bvid}")
        return None

    sub_url = _fetch_subtitle_url(bvid, cid, headers)
    if not sub_url:
        print(f"bilibili subtitles: no subtitle track found for {bvid} (cid={cid})")
        return None

    segments = _parse_subtitle_file(sub_url, headers)
    if not segments:
        print(f"bilibili subtitles: subtitle file was empty for {bvid}")
        return None

    print(f"bilibili subtitles: fetched {len(segments)} segments for {bvid}")
    return segments


def make_title_captions(title, total_duration=900.0):
    """
    Fallback caption generator when no subtitle track is available.

    Shows the video title at the start of each 10-second interval,
    so every clip window gets at least one caption line. Also appends
    a branded tagline ("Follow for more 🔥") between title appearances.

    Args:
        title: Source video title string (Chinese or otherwise).
        total_duration: Total video duration in seconds (generous default = 900s).

    Returns:
        List of {"start", "duration", "text"} dicts, or None if title is empty.
    """
    title_clean = (title or "").strip()
    # Truncate long titles — ASS wraps at 20 chars per line × 3 lines = 60 chars max.
    if len(title_clean) > 50:
        title_clean = title_clean[:47] + "..."
    if not title_clean:
        return None

    segments = []
    t = 0.0
    alternating = True  # True = title, False = tagline
    while t < total_duration - 1.0:
        text = title_clean if alternating else "Follow for more \U0001f525"
        seg_dur = min(4.0, total_duration - t - 0.1)
        if seg_dur < 0.5:
            break
        segments.append({"start": t, "duration": seg_dur, "text": text})
        t += 10.0  # gap of 6 seconds between each caption burst
        alternating = not alternating

    return segments or None


def bvid_from_url(url):
    """Extract BV ID from a bilibili URL, or None."""
    m = _BILI_RE.search(url or "")
    return m.group(1) if m else None
