import requests

BASE = "https://api.bilibili.com/x/web-interface"


def _popular(max_count=40):
    out = []
    pn = 1
    while len(out) < max_count:
        resp = requests.get(
            f"{BASE}/popular",
            params={"ps": 30, "pn": pn},
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
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
                }
            )
        pn += 1
    return out


def discover(cfg):
    discovery = cfg["discovery"]
    max_duration_s = discovery.get("max_duration_s")
    min_duration_s = discovery.get("min_source_duration_s", 40)
    max_count = discovery.get("max_new_sources", 5) * 4
    found = []
    for src in _popular(max_count):
        length = src.get("length") or 0
        if length < min_duration_s:
            continue
        if max_duration_s and length > max_duration_s:
            continue
        found.append(src)
    return found