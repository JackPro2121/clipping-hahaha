"""main.py — Pipeline orchestrator with retry intelligence, Slack alerts, and cleanup."""

import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from buffer_api import create_post, get_channels  # noqa: E402
from captions.bilibili_subtitles import (  # noqa: E402
    bvid_from_url,
    fetch_bilibili_subtitles,
    make_title_captions,
)
from chocodata import extract_video_id, fetch_transcript  # noqa: E402
from clip import build_clips  # noqa: E402
from download import download_video  # noqa: E402
from media import upload_video  # noqa: E402
from notifications.slack import send_slack_summary, send_slack_alert  # noqa: E402
from pipeline.cleanup import cleanup_cloudinary_clips  # noqa: E402
from pipeline.queue_manager import can_queue_posts  # noqa: E402
from utils.errors import DownloadError, QueueFullError  # noqa: E402
from utils.state import (  # noqa: E402
    load_state,
    save_state,
    should_retry,
    schedule_retry,
    mark_processed,
)

ROOT = Path(__file__).resolve().parent.parent

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_YOUTUBE_RE = re.compile(r"(?:youtube\.com|youtu\.be)")
_BILI_RE = re.compile(r"bilibili\.com/video/(BV[\w]+)", re.IGNORECASE)

# ─────────────────────────────────────────────────────────────
# Required env vars — validated once at startup.
# ─────────────────────────────────────────────────────────────
_REQUIRED_SECRETS = [
    "BUFFER_API_KEY",
    "CLOUDINARY_CLOUD_NAME",
    "CLOUDINARY_API_KEY",
    "CLOUDINARY_API_SECRET",
]


def validate_env():
    """Raise a clear RuntimeError listing any missing required secrets."""
    missing = [k for k in _REQUIRED_SECRETS if not os.environ.get(k)]
    if missing:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(missing)}\n"
            "Set them as GitHub Actions secrets or export them locally."
        )


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_caption(cfg, title, index, total, service=None):
    """Build a tailored caption string, checking per-platform template if specified."""
    buffer_cfg = cfg.get("buffer") or {}
    templates = buffer_cfg.get("per_platform_captions") or {}

    template = (
        templates.get(service)
        if service and service in templates
        else buffer_cfg.get("caption_template", "{title} - clip {index}/{total} {hashtags}")
    )
    hashtags = buffer_cfg.get("hashtags", "")
    return template.format(title=title, index=index, total=total, hashtags=hashtags)


def _fetch_captions(src, captions_cfg):
    """Fetch caption segments for a source URL with 2-tier fallback."""
    if not captions_cfg.get("enabled"):
        return None

    url = src["url"]

    # ── bilibili ──────────────────────────────────────────────
    bvid = bvid_from_url(url)
    if bvid:
        try:
            transcript = fetch_bilibili_subtitles(bvid)
        except Exception as exc:
            print(f"bilibili subtitle API error: {exc}")
            transcript = None

        if transcript:
            return transcript

        # Fallback: title-based captions
        print("No bilibili subtitle track — using title-based caption fallback")
        fallback = make_title_captions(
            src.get("title", ""),
            total_duration=900.0,
        )
        if fallback:
            print(f"Title fallback: {len(fallback)} caption segments generated")
        return fallback

    # ── YouTube ───────────────────────────────────────────────
    if _YOUTUBE_RE.search(url):
        try:
            transcript = fetch_transcript(
                extract_video_id(url), captions_cfg.get("lang", "en")
            )
            if transcript:
                print(f"Fetched {len(transcript)} ChocoData transcript segments")
            else:
                print("No transcript available from ChocoData")
            return transcript
        except Exception as exc:
            print(f"ChocoData transcript fetch failed: {exc}")
            return None

    return None


def process_source(src, cfg):
    """Process one pending source end-to-end.

    Returns:
        tuple[bool, int, str]: (success, clips_posted_count, error_message)
    """
    captions_cfg = cfg.get("captions", {})
    transcript = _fetch_captions(src, captions_cfg)

    with tempfile.TemporaryDirectory() as td:
        work = Path(td)

        # 1. Download
        try:
            raw = download_video(
                src["url"],
                work,
                max_duration_s=cfg["clipper"].get("max_source_duration_s"),
            )
        except (DownloadError, RuntimeError) as exc:
            err = f"Download failed: {exc}"
            print(err)
            return False, 0, err

        # 2. Clip
        clipper_cfg = {
            **cfg["clipper"],
            "motion": cfg.get("motion", {}),
            "effects": cfg.get("effects", {}),
            "brand": cfg.get("brand", {}),
        }
        try:
            clips = build_clips(
                raw,
                work / "clips",
                clipper_cfg,
                transcript=transcript,
                captions_enabled=captions_cfg.get("burn_in", True),
            )
        except Exception as exc:
            err = f"Clipping failed: {exc}"
            print(err)
            return False, 0, err

        if not clips:
            err = "No clips generated"
            print(err)
            return False, 0, err

        # 3. Retrieve Buffer channels
        try:
            channels = get_channels(cfg["buffer"].get("services") or None)
        except Exception as exc:
            err = f"Failed to retrieve Buffer channels: {exc}"
            print(err)
            return False, 0, err

        title = src.get("title") or raw.stem
        max_posts = cfg["buffer"].get("max_posts_per_channel", 8)
        clips = clips[:max_posts]
        posted = 0

        # Check queue capacity before flooding
        max_queue = cfg.get("buffer", {}).get("max_queue_depth", 20)

        for i, clip in enumerate(clips, 1):
            try:
                url = upload_video(clip, folder="clips")
            except Exception as exc:
                print(f"Cloudinary upload failed for {clip.name}: {exc}")
                continue

            for channel in channels:
                service = channel.get("service")
                allowed, depth = can_queue_posts(channel["id"], max_queue_depth=max_queue)
                if not allowed:
                    msg = f"Queue full for {service} ({depth} pending) — skipping clip {clip.name}"
                    print(msg)
                    send_slack_alert(f"Queue Full on {service}", msg, is_error=False)
                    return False, posted, msg

                caption = build_caption(cfg, title, i, len(clips), service=service)

                try:
                    post_id = create_post(channel["id"], caption, url)
                    posted += 1
                    print(
                        f"Posted {clip.name} -> {service} "
                        f"({channel['name']}) id={post_id}"
                    )
                except QueueFullError as exc:
                    print(f"Queue limit reached for {service}: {exc}")
                    return False, posted, str(exc)
                except Exception as exc:
                    print(f"Post failed {clip.name} -> {service}: {exc}")

        if posted == 0:
            return False, 0, "No clips successfully posted"

        return True, posted, ""


def main():
    validate_env()

    start_time = time.time()
    cfg = load_json(ROOT / "config.json")
    state = load_state()

    pending = [s for s in state["sources"] if should_retry(s)]
    if not pending:
        print("No pending sources ready for processing (all up-to-date or in retry backoff).")
        cleanup_cloudinary_clips(keep_days=cfg.get("storage", {}).get("retention_days", 14))
        return

    processed_count = 0
    total_posted_run = 0
    failed_count = 0
    now_iso = datetime.now(timezone.utc).isoformat()

    for src in pending:
        print(f"\n{'=' * 60}")
        print(f"Processing: {src['url']}")
        print(f"Title: {src.get('title', '(no title)')[:80]}")
        print(f"Quality Score: {src.get('score', 'N/A')} | Retry Count: {src.get('retry_count', 0)}")
        print(f"{'=' * 60}")

        success, posted_count, err_msg = process_source(src, cfg)
        if success:
            mark_processed(src, clips_count=posted_count)
            processed_count += 1
            total_posted_run += posted_count
            state["_meta"]["total_processed"] = state["_meta"].get("total_processed", 0) + 1
            state["_meta"]["total_clips_posted"] = (
                state["_meta"].get("total_clips_posted", 0) + posted_count
            )
            save_state(state)
            print(f"✓ Marked processed: {src['url']} ({posted_count} clips posted)")
        else:
            failed_count += 1
            schedule_retry(src, err_msg)
            save_state(state)
            print(
                f"✗ Scheduled retry #{src.get('retry_count')} "
                f"after {src.get('next_retry_after')}: {src['url']}"
            )

    state["_meta"]["last_run"] = now_iso
    save_state(state)

    # 4. Storage GC
    retention = cfg.get("storage", {}).get("retention_days", 14)
    print(f"\nRunning Cloudinary storage maintenance (retention: {retention} days)...")
    cleanup_cloudinary_clips(keep_days=retention)

    # 5. Slack Notification
    duration = time.time() - start_time
    send_slack_summary(
        {
            "processed_count": processed_count,
            "clips_posted": total_posted_run,
            "failed_count": failed_count,
            "category": state.get("_meta", {}).get("last_category", "popular"),
            "run_duration_s": duration,
        }
    )

    print(f"Pipeline complete! {total_posted_run} clips posted in {duration:.1f}s.")


if __name__ == "__main__":
    main()