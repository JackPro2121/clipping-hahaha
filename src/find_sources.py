import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from chocodata import discover  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def load_sources():
    with open(ROOT / "sources.json", encoding="utf-8") as f:
        return json.load(f)


def save_sources(data):
    with open(ROOT / "sources.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def main():
    cfg = json.load(open(ROOT / "config.json", encoding="utf-8"))
    discovery = cfg.get("discovery")
    if not discovery or not discovery.get("enabled"):
        print("Discovery disabled in config")
        return
    if "CHOCODATA_API_KEY" not in os.environ:
        print("CHOCODATA_API_KEY not set, skipping discovery")
        return
    sources = load_sources()
    existing = {s["url"] for s in sources["sources"]}
    try:
        found = discover(cfg)
    except Exception as exc:
        print(f"Discovery failed: {exc}")
        return
    found.sort(key=lambda s: s.get("views", 0), reverse=True)
    max_new = discovery.get("max_new_sources", 5)
    added = 0
    for src in found:
        if src["url"] in existing:
            continue
        if discovery.get("min_views") and src.get("views", 0) < discovery["min_views"]:
            continue
        sources["sources"].append(
            {"url": src["url"], "title": src.get("title", ""), "status": "pending"}
        )
        existing.add(src["url"])
        added += 1
        if added >= max_new:
            break
    if added:
        save_sources(sources)
    print(f"Added {added} new sources")


if __name__ == "__main__":
    main()