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
    except Exception as exc:
        print(f"bilibili pagelist failed for {bvid}: {exc}")
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
    except Exception as exc:
        print(f"bilibili player/v2 failed for {bvid} cid={cid}: {exc}")
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
    except Exception as exc:
        print(f"bilibili parse subtitle file failed ({url[:40]}...): {exc}")
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
    High-retention 3-second hook generator for ASMR and craftsmanship videos.

    Displays a curiosity-inducing visual hook during the first 3.2 seconds
    to maximize 3-second scroll-stop rate, then leaves the rest of the video
    100% clean and immersion-focused for pure visual/acoustic ASMR.

    Args:
        title: Source video title string (translated English).
        total_duration: Total video duration in seconds.

    Returns:
        List of {"start", "duration", "text"} dicts, or None if title is empty.
    """
    title_clean = (title or "").strip()
    if len(title_clean) > 48:
        title_clean = title_clean[:44] + "..."
    if not title_clean:
        return None

    # Only show high-retention hook for first 3.2 seconds
    intro_dur = min(3.2, total_duration - 0.1)
    if intro_dur < 0.5:
        return None

    hook_text = f"🔨 Wait For The Result ✨\\N{title_clean}"
    return [{"start": 0.0, "duration": intro_dur, "text": hook_text}]


def bvid_from_url(url):
    """Extract BV ID from a bilibili URL, or None."""
    m = _BILI_RE.search(url or "")
    return m.group(1) if m else None
