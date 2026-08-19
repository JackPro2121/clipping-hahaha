import os

import requests

BASE = "https://api.chocodata.com/api/v1/youtube"


def _first(obj, keys):
    if not isinstance(obj, dict):
        return None
    for key in keys:
        if key in obj and obj[key] not in (None, ""):
            return obj[key]
    return None


def _get(path, params):
    resp = requests.get(
        BASE + path,
        params={"api_key": os.environ["CHOCODATA_API_KEY"], **params},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def extract_video_id(url):
    for marker in ("v=", "youtu.be/"):
        if marker in url:
            return url.split(marker, 1)[1].split("&")[0]
    return url


def fetch_transcript(video_id, lang="en"):
    data = _get("/transcript", {"video_id": video_id, "lang": lang})
    transcript = data.get("transcript")
    if isinstance(transcript, list):
        segments = transcript
    elif isinstance(data, dict):
        segments = data.get("segments")
        if not segments and isinstance(data.get("data"), dict):
            segments = data["data"].get("segments") or data["data"].get("transcript")
    else:
        segments = None
    if not isinstance(segments, list):
        return None
    out = []
    for item in segments:
        if not isinstance(item, dict):
            continue
        text = item.get("text") or item.get("caption") or ""
        start = item.get("start") or item.get("startTime") or item.get("t")
        dur = item.get("duration") or item.get("dur") or 2
        if text and start is not None:
            out.append({"start": float(start), "duration": float(dur), "text": str(text)})
    return out or None


def _video_url(video_id):
    return f"https://www.youtube.com/watch?v={video_id}"


def _parse_video_list(data):
    videos = []
    for bucket in (data.get("videos"), data.get("items"), data.get("results")):
        if isinstance(bucket, list):
            videos.extend(bucket)
            break
    if not videos and isinstance(data.get("data"), dict):
        for bucket in (data["data"].get("videos"), data["data"].get("items")):
            if isinstance(bucket, list):
                videos.extend(bucket)
                break
    return videos


def _as_source(item):
    video_id = _first(item, ["videoId", "id", "video_id", "videoID"])
    if not video_id:
        return None
    title = _first(item, ["title", "name"]) or video_id
    views = _first(item, ["viewCount", "views", "view_count", "stats.views"])
    try:
        views = int(views)
    except (TypeError, ValueError):
        views = 0
    length = _first(item, ["lengthSeconds", "duration", "lengthText"])
    return {
        "url": _video_url(video_id),
        "title": str(title),
        "views": views,
        "length": length,
    }


def discover_channel(channel, max_duration_s=None, tab="videos"):
    data = _get("/channel", {"channel": channel, "tab": tab})
    sources = []
    for item in _parse_video_list(data):
        src = _as_source(item)
        if not src:
            continue
        if max_duration_s and src.get("length"):
            try:
                if int(src["length"]) > max_duration_s:
                    continue
            except (TypeError, ValueError):
                pass
        sources.append(src)
    return sources


def discover_search(term, max_duration_s=None):
    data = _get("/search", {"q": term})
    sources = []
    for item in _parse_video_list(data):
        src = _as_source(item)
        if not src:
            continue
        if max_duration_s and src.get("length"):
            try:
                if int(src["length"]) > max_duration_s:
                    continue
            except (TypeError, ValueError):
                pass
        sources.append(src)
    return sources


def discover_trending(country="US", max_duration_s=None):
    data = _get("/trending", {"country": country})
    sources = []
    for item in _parse_video_list(data):
        src = _as_source(item)
        if not src:
            continue
        if max_duration_s and src.get("length"):
            try:
                if int(src["length"]) > max_duration_s:
                    continue
            except (TypeError, ValueError):
                pass
        sources.append(src)
    return sources


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
            found.extend(discover_search(term, max_duration_s))
    elif strategy == "trending":
        found = discover_trending(discovery.get("country", "US"), max_duration_s)
    else:
        return []
    return found