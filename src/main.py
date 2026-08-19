import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from buffer_api import create_post, get_channels  # noqa: E402
from chocodata import extract_video_id, fetch_transcript  # noqa: E402
from clip import build_clips  # noqa: E402
from download import download_video  # noqa: E402
from media import upload_video  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def build_caption(cfg, title, index, total):
    template = cfg["buffer"]["caption_template"]
    hashtags = cfg["buffer"].get("hashtags", "")
    return template.format(title=title, index=index, total=total, hashtags=hashtags)


def process_source(src, cfg):
    captions_cfg = cfg.get("captions", {})
    transcript = None
    if captions_cfg.get("enabled"):
        try:
            transcript = fetch_transcript(
                extract_video_id(src["url"]), captions_cfg.get("lang", "en")
            )
            if transcript:
                print(f"Fetched {len(transcript)} transcript segments")
            else:
                print("No transcript available, skipping captions")
        except Exception as exc:
            print(f"Transcript fetch failed: {exc}")

    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        raw = download_video(
            src["url"],
            work,
            max_duration_s=cfg["clipper"].get("max_source_duration_s"),
        )
        clipper_cfg = {**cfg["clipper"], "motion": cfg.get("motion", {})}
        clips = build_clips(
            raw,
            work / "clips",
            clipper_cfg,
            transcript=transcript,
            captions_enabled=captions_cfg.get("burn_in", True),
        )
        if not clips:
            print(f"No clips generated for {src['url']}")
            return
        channels = get_channels(cfg["buffer"].get("services") or None)
        title = src.get("title") or raw.stem
        max_posts = cfg["buffer"].get("max_posts_per_channel", 8)
        clips = clips[:max_posts]
        for i, clip in enumerate(clips, 1):
            url = upload_video(clip, folder="clips")
            caption = build_caption(cfg, title, i, len(clips))
            for channel in channels:
                try:
                    post_id = create_post(channel["id"], caption, url)
                    print(
                        f"Posted {clip.name} -> {channel['service']} "
                        f"({channel['name']}) id={post_id}"
                    )
                except Exception as exc:
                    print(f"Post failed {clip.name} -> {channel['service']}: {exc}")


def main():
    cfg = load_json(ROOT / "config.json")
    sources = load_json(ROOT / "sources.json")
    pending = [s for s in sources["sources"] if s.get("status") != "processed"]
    if not pending:
        print("No pending sources")
        return
    for src in pending:
        print(f"Processing: {src['url']}")
        process_source(src, cfg)
        src["status"] = "processed"
        save_json(ROOT / "sources.json", sources)
        print(f"Marked processed: {src['url']}")


if __name__ == "__main__":
    main()