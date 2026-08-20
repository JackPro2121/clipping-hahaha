"""bilibili.py — Bilibili discovery with multi-category rotation and ranking support."""

import requests

BASE = "https://api.bilibili.com/x/web-interface"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# Public Bilibili category IDs (rid) that do not require WBI signing or login
CATEGORY_RIDS = {
    "food": 76,
    "tech": 188,
    "travel": 223,
    "music": 3,
    "games": 4,
    "knowledge": 36,
    "auto": 223,
}


def _fetch_popular(max_count=40):
    out = []
    pn = 1
    while len(out) < max_count:
        resp = requests.get(
            f"{BASE}/popular",
            params={"ps": 30, "pn": pn},
            headers={"User-Agent": _UA},
            timeout=60,
        )
        resp.raise_for_status()
        data = (resp.json() or {}).get("data") or {}
        items = data.get("list") or []
        if not items:
            break
        for item in items:
            if len(out) >= max_count:
                break
            bvid = item.get("bvid")
            if not bvid:
                continue
            stat = item.get("stat") or {}
            out.append(
                {
                    "url": f"https://www.bilibili.com/video/{bvid}",
                    "title": item.get("title") or bvid,
                    "views": int(stat.get("view") or 0),
                    "length": int(item.get("duration") or 0),
                    "category": "popular",
                }
            )
        pn += 1
    return out


def _fetch_ranking(category="ranking", max_count=40):
    rid = CATEGORY_RIDS.get(category, 0)
    params = {"rid": rid, "type": "all"} if rid else {"rid": 0, "type": "all"}
    try:
        resp = requests.get(
            f"{BASE}/ranking/v2",
            params=params,
            headers={"User-Agent": _UA},
            timeout=60,
        )
        resp.raise_for_status()
        data = (resp.json() or {}).get("data") or {}
        items = data.get("list") or []
    except Exception:
        # Fallback to popular if ranking endpoint is unavailable
        return _fetch_popular(max_count)

    out = []
    for item in items:
        if len(out) >= max_count:
            break
        bvid = item.get("bvid")
        if not bvid:
            continue
        stat = item.get("stat") or {}
        out.append(
            {
                "url": f"https://www.bilibili.com/video/{bvid}",
                "title": item.get("title") or bvid,
                "views": int(stat.get("view") or 0),
                "length": int(item.get("duration") or 0),
                "category": category,
            }
        )
    return out or _fetch_popular(max_count)


def _parse_duration(duration_str):
    """Parse duration like '0:52', '2:48', '1:02:15' or integer seconds."""
    if isinstance(duration_str, (int, float)):
        return int(duration_str)
    if not duration_str or not isinstance(duration_str, str):
        return 0
    parts = duration_str.strip().split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        return int(parts[0])
    except (ValueError, IndexError):
        return 0


def _fetch_search(keyword, max_count=30, order="click"):
    """Search Bilibili for high-performing videos matching a keyword."""
    import urllib.parse
    import tempfile
    from pathlib import Path
    from download import _bili_headers

    out = []
    try:
        with tempfile.TemporaryDirectory() as td:
            headers, _ = _bili_headers(Path(td))
            kw_encoded = urllib.parse.quote(str(keyword))
            url = (
                f"{BASE}/search/type"
                f"?search_type=video&keyword={kw_encoded}&order={order}&page=1"
            )
            resp = requests.get(url, headers=headers, timeout=20)
            if resp.status_code != 200:
                return out
            data = resp.json().get("data", {}) or {}
            items = data.get("result", []) or []
            for item in items:
                if len(out) >= max_count:
                    break
                bvid = item.get("bvid")
                if not bvid:
                    continue
                # Clean html tags from title (Bilibili search highlights keywords with <em class="keyword">)
                raw_title = item.get("title") or bvid
                clean_title = (
                    raw_title.replace('<em class="keyword">', "")
                    .replace("</em>", "")
                    .strip()
                )
                views = int(item.get("play") or 0)
                length = _parse_duration(item.get("duration"))
                out.append(
                    {
                        "url": f"https://www.bilibili.com/video/{bvid}",
                        "title": clean_title,
                        "views": views,
                        "length": length,
                        "category": keyword,
                    }
                )
    except Exception as exc:
        print(f"Bilibili search for '{keyword}' error: {exc}")
    return out


def discover(cfg, category="popular", keyword=None):
    """Discover candidate videos from Bilibili based on keyword or category selection."""
    discovery = cfg.get("discovery", {})
    max_duration_s = discovery.get("max_duration_s")
    min_duration_s = discovery.get("min_source_duration_s", 35)
    max_count = discovery.get("max_new_sources", 5) * 4

    if keyword:
        order = discovery.get("order", "click")
        raw_items = _fetch_search(keyword, max_count=max_count, order=order)
    elif category == "popular" or not category:
        raw_items = _fetch_popular(max_count)
    else:
        raw_items = _fetch_ranking(category, max_count)

    found = []
    for src in raw_items:
        length = src.get("length") or 0
        if length < min_duration_s:
            continue
        if max_duration_s and length > max_duration_s:
            continue
        found.append(src)
    return found