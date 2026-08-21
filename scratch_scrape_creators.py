"""scratch/scrape_creators.py — Scrape top craft creators from Bilibili & Douyin APIs."""

import json
import os
import sys
import tempfile
import time
import urllib.parse
from pathlib import Path
import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from download import _bili_headers

CRAFT_KEYWORDS = [
    ("木工", "Traditional Woodworking & Carpentry"),
    ("老物件修复", "Antique Restoration"),
    ("沉浸式修复", "Immersive ASMR Restoration"),
    ("手工制作", "Precision Handcraft"),
    ("解压手工", "Oddly Satisfying Craft"),
    ("刀剑锻造", "Blacksmith Knife Forging"),
    ("机械制造", "Precision Machine Art"),
    ("榫卯", "Mortise & Tenon Joinery"),
]

def scrape_bilibili_creators():
    creators = {}
    
    with tempfile.TemporaryDirectory() as td:
        headers, _ = _bili_headers(Path(td))
        
        for kw, label in CRAFT_KEYWORDS:
            kw_enc = urllib.parse.quote(kw)
            url = f"https://api.bilibili.com/x/web-interface/search/type?search_type=video&keyword={kw_enc}&order=click&page=1"
            try:
                resp = requests.get(url, headers=headers, timeout=25)
                if resp.status_code != 200:
                    continue
                data = resp.json().get("data", {})
                items = data.get("result", [])
                for item in items[:10]:
                    mid = str(item.get("mid") or "")
                    author = item.get("author") or "Unknown"
                    play = int(item.get("play") or 0)
                    raw_title = item.get("title", "").replace('<em class="keyword">', "").replace("</em>", "").strip()
                    
                    negatives = ["游戏", "歌", "dance", "动漫", "解说", "reaction"]
                    if any(neg in raw_title.lower() for neg in negatives):
                        continue
                    if play < 50000:
                        continue
                    
                    if mid and mid not in creators:
                        creators[mid] = {
                            "uid": mid,
                            "author": author,
                            "category_label": label,
                            "keyword": kw,
                            "top_play": play,
                            "sample_title": raw_title,
                            "profile_url": f"https://space.bilibili.com/{mid}",
                        }
                    elif mid in creators:
                        if play > creators[mid]["top_play"]:
                            creators[mid]["top_play"] = play
            except Exception as exc:
                print(f"Bilibili query error for keyword: {exc}")

    ranked = sorted(creators.values(), key=lambda x: x["top_play"], reverse=True)
    return ranked

if __name__ == "__main__":
    ranked = scrape_bilibili_creators()
    print(f"Found {len(ranked)} verified top craft creators:\n")
    for idx, c in enumerate(ranked[:15], 1):
        print(f"{idx}. [{c['category_label']}] {c['author']} (UID: {c['uid']})")
        print(f"   Views: {c['top_play']:,} | Sample: {c['sample_title']}")
        print(f"   Profile: {c['profile_url']}\n")
    
    with open("scraped_creators.json", "w", encoding="utf-8") as f:
        json.dump(ranked, f, ensure_ascii=False, indent=2)
    print("Saved to scraped_creators.json")


if __name__ == "__main__":
    ranked = scrape_bilibili_creators()
    print(f"Found {len(ranked)} verified top craft creators:\n")
    for idx, c in enumerate(ranked[:15], 1):
        print(f"{idx}. [{c['category_label']}] {c['author']} (UID: {c['uid']})")
        print(f"   Views: {c['top_play']:,} | Sample: {c['sample_title']}")
        print(f"   Profile: {c['profile_url']}\n")
    
    # Save to JSON
    with open("scraped_creators.json", "w", encoding="utf-8") as f:
        json.dump(ranked, f, ensure_ascii=False, indent=2)
    print("Saved to scraped_creators.json")
