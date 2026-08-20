import os
import re
import time

import requests

BASE = "https://api.chocodata.com/api/v1/youtube"


def _get(path, params):
    def call():
        return requests.get(
            BASE + path,
            params={"api_key": os.environ["CHOCODATA_API_KEY"], **params},
            timeout=60,
        )

    for attempt in range(3):
        resp = call()
        if resp.status_code == 429:
            retry = float(resp.headers.get("Retry-After", 1))
            print(f"Chocodata rate limited, waiting {retry}s")
            time.sleep(retry)
            continue
        if resp.status_code >= 500:
            print(f"Chocodata server error {resp.status_code}, retrying ({attempt + 1}/3)")
            time.sleep(2 * (attempt + 1))
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError(f"Chocodata request failed after retries: {path}")


def parse_views(text):
    if text is None:
        return 0
    if isinstance(text, (int, float)):
        return int(text)
    s = str(text).replace(",", "").strip()
    m = re.search(r"([\d.]+)\s*([KMB]?)", s, re.IGNORECASE)
    if not m:
        return 0
    val = float(m.group(1))
    mult = {"": 1, "K": 1000, "M": 1000000, "B": 1000000000}[m.group(2).upper()]
    return int(val * mult)


def parse_length(text):
    if isinstance(text, (int, float)):
        return int(text)
    s = str(text).strip()
    parts = [int(p) for p in s.split(":") if p.isdigit()]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 1:
        return parts[0]
    return None


def extract_video_id(url):
    for marker in ("v=", "youtu.be/", "/shorts/"):
        if marker in url:
            return url.split(marker, 1)[1].split("&")[0].split("/")[0]
    return url


def fetch_transcript(video_id, lang="en"):
    data = _get(
        "/transcript",
        {"video_id": video_id, "lang": lang, "units": "seconds"},
    )
    if data.get("transcript_available") is False:
        return None
    segments = data.get("segments")
    if not isinstance(segments, list):
        return None
    out = []
    for item in segments:
        if not isinstance(item, dict):
            continue
        text = item.get("text") or ""
        start = item.get("start")
        dur = item.get("duration", 2)
        if text and start is not None:
            out.append(
                {"start": float(start), "duration": float(dur), "text": str(text)}
            )
    return out or None


def _video_url(video_id):
    return f"https://www.youtube.com/watch?v={video_id}"


def _as_source(item):
    video_id = item.get("video_id") or item.get("id") or item.get("videoId")
    if not video_id:
        return None
    title = item.get("title") or video_id
    views = parse_views(item.get("views") or item.get("view_count"))
    length = parse_length(
        item.get("length") or item.get("length_seconds") or item.get("duration")
    )
    url = item.get("link") or item.get("url") or _video_url(video_id)
    return {"url": url, "title": str(title), "views": views, "length": length}


def _keep(src, max_duration_s):
    return not (max_duration_s and src["length"] and src["length"] > max_duration_s)


def discover_channel(channel, max_duration_s=None, tab="videos"):
    data = _get("/channel", {"channel": channel, "tab": tab})
    return [
        src
        for item in data.get("videos") or []
        if (src := _as_source(item)) and _keep(src, max_duration_s)
    ]


SP_FILTERS = {
    "hour": "CAISBAgEEAE",
    "today": "CAISBAgEEAI",
    "week": "EgIIAg",
    "month": "EgIIAw",
    "year": "EgIIBA",
}


def discover_search(term, max_duration_s=None, upload_date=None):
    params = {"search_query": term}
    if upload_date in SP_FILTERS:
        params["sp"] = SP_FILTERS[upload_date]
    data = _get("/search", params)
    return [
        src
        for item in data.get("organic_results") or []
        if (src := _as_source(item)) and _keep(src, max_duration_s)
    ]


def suggest(term, lang="en", country="us"):
    data = _get("/suggest", {"query": term, "language": lang, "country": country})
    return data.get("related_searches") or []


def video_metadata(video_id):
    return _get("/video", {"video_id": video_id})


def discover(cfg):
    discovery = cfg["discovery"]
    strategy = discovery["strategy"]
    max_duration_s = discovery.get("max_duration_s")
    if strategy == "channel":
        found = []
        for target in discovery.get("targets", []):
            found.extend(discover_channel(target, max_duration_s))
    elif strategy == "search":
        found = []
        for term in discovery.get("search_terms", []):
            found.extend(
                discover_search(
                    term, max_duration_s, discovery.get("upload_date")
                )
            )
    else:
        return []
    return found