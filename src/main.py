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
from captions.translator import translate_to_english, translate_segments  # noqa: E402
from chocodata import extract_video_id, fetch_transcript  # noqa: E402
from clip import build_clips  # noqa: E402
from download import download_video  # noqa: E402
from media import upload_video  # noqa: E402
from notifications.slack import send_slack_summary, send_slack_alert  # noqa: E402
from pipeline.cleanup import cleanup_cloudinary_clips  # noqa: E402
from pipeline.queue_manager import can_queue_posts  # noqa: E402
from utils.config import load_config  # noqa: E402
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
        else buffer_cfg.get("caption_template", "{title} {hashtags}")
    )
    hashtags = buffer_cfg.get("hashtags", "")
    part = f" (Part {index}/{total})" if total and total > 1 else ""
    return template.format(
        title=title,
        index=index,
        total=total,
        part=part,
        hashtags=hashtags,
    ).strip()


def _fetch_captions(src, captions_cfg):
    """Fetch caption segments for a source URL with 2-tier fallback.

    All segments are auto-translated to English for Tier-1 audiences.
    """
    if not captions_cfg.get("enabled"):
        return None

    url = src["url"]
    segments = None

    # ── bilibili ──────────────────────────────────────────────
    bvid = bvid_from_url(url)
    if bvid:
        try:
            segments = fetch_bilibili_subtitles(bvid)
        except Exception as exc:
            print(f"bilibili subtitle API error: {exc}")
            segments = None

        if not segments:
            # Fallback: title-based captions (translate title first)
            print("No bilibili subtitle track — using title-based caption fallback")
            raw_title = src.get("title", "")
            eng_title = translate_to_english(raw_title)
            print(f"Title translated: '{raw_title[:40]}' → '{eng_title[:60]}'")
            fallback = make_title_captions(eng_title, total_duration=900.0)
            if fallback:
                print(f"Title fallback: {len(fallback)} caption segments generated")
            return fallback

    # ── YouTube ───────────────────────────────────────────────
    elif _YOUTUBE_RE.search(url):
        try:
            segments = fetch_transcript(
                extract_video_id(url), captions_cfg.get("lang", "en")
            )
            if segments:
                print(f"Fetched {len(segments)} ChocoData transcript segments")
            else:
                print("No transcript available from ChocoData")
        except Exception as exc:
            print(f"ChocoData transcript fetch failed: {exc}")
            return None

    # ── Translate all caption segments to English ─────────────
    if segments:
        print(f"Translating {len(segments)} caption segments to English...")
        segments = translate_segments(segments)
        print("Caption translation complete")

    return segments


# ─────────────────────────────────────────────────────────────
# Caption title sanitization (BUG-05, BUG-15)
# ─────────────────────────────────────────────────────────────
_CAPTION_CRAFT_PATTERNS = [
    re.compile(r"\b" + re.escape(kw), re.IGNORECASE)
    for kw in [
        "wood", "carv", "craft", "restor", "knife", "sword", "lathe", "forge",
        "handmade", "repair", "machin", "jade", "bamboo", "weav", "chisel",
        "tool", "metal", "iron", "steel", "weld", "polish", "sculpt", "engrav",
        "fan", "clay", "potter", "making", "build", "creat", "art", "master",
        "satisfying", "traditional", "ancient", "skill", "technique", "carpenter",
        "blacksmith", "craftsman", "woodwork"
    ]
]


def sanitize_caption_title(translated: str) -> str:
    """Return translated title if craft-relevant, else a safe generic fallback."""
    if not translated:
        return "Incredible Craft Mastery You Have to See"
    for pat in _CAPTION_CRAFT_PATTERNS:
        if pat.search(translated):
            return translated
    # Off-niche translation detected — use generic on-brand caption
    print(
        f"  [caption-sanitize] Off-niche title detected: '{translated[:60]}' "
        f"→ using generic craft caption"
    )
    return "Incredible Craft Mastery You Have to See"


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
                play_url=src.get("play_url"),
            )
        except (DownloadError, RuntimeError) as exc:
            err = f"Download failed: {exc}"
            print(err)
            return False, 0, err

        # 1b. Smart AI Speech-to-Text via Faster-Whisper
        # BUG-10 fix: Only transcribe if no official subtitle track was fetched
        if captions_cfg.get("enabled", True) and not transcript:
            from captions.whisper_transcriber import transcribe_and_translate
            try:
                whisper_segments = transcribe_and_translate(raw)
                if whisper_segments:
                    transcript = whisper_segments
            except Exception as exc:
                print(f"Whisper AI check skipped: {exc}")

        # 2. Clip
        clipper_cfg = {
            **cfg["clipper"],
            "motion": cfg.get("motion", {}),
            "effects": cfg.get("effects", {}),
            "brand": cfg.get("brand", {}),
        }
        # Smart window selection: LLM reads the transcript (or audio-energy
        # peaks for music/ASMR videos) to pick the most engaging moments.
        # Falls back to the built-in heuristic windows on any failure.
        smart_windows = None
        if cfg["clipper"].get("smart_windows", True):
            try:
                from clip import probe as _probe
                from llm.windows import compute_windows
                from utils.audio_energy import (
                    extract_loudness_profile,
                    find_energy_peaks,
                )

                _, _, duration_s, _ = _probe(raw)
                cl = cfg["clipper"]
                audio_candidates = None
                if not transcript:
                    profile = extract_loudness_profile(raw)
                    audio_candidates = find_energy_peaks(
                        profile,
                        duration_s,
                        cl.get("clip_length_s", 45),
                        cl.get("max_clips_per_video", 3) + 2,
                        cl.get("min_clip_s", 10),
                    )
                smart_windows = compute_windows(
                    duration_s,
                    cl,
                    transcript=transcript,
                    audio_candidates=audio_candidates,
                )
                if smart_windows:
                    print(f"Smart windows: {smart_windows}")
                else:
                    print("Smart windows: using heuristic fallback")
            except Exception as exc:
                smart_windows = None
                print(f"Smart windows skipped: {str(exc)[:80]}")
        try:
            clips = build_clips(
                raw,
                work / "clips",
                clipper_cfg,
                transcript=transcript,
                captions_enabled=captions_cfg.get("burn_in", True),
                windows=smart_windows,
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

        # Translate title to English for Buffer captions, then sanitize
        raw_title = src.get("title") or raw.stem
        title = translate_to_english(raw_title)
        if title != raw_title:
            print(f"Title translated for captions: '{raw_title[:40]}' → '{title[:60]}'")
        title = sanitize_caption_title(title)
        max_posts = cfg["buffer"].get("max_posts_per_channel", 8)
        clips = clips[:max_posts]
        posted = 0

        # Check queue capacity before flooding
        max_queue = cfg.get("buffer", {}).get("max_queue_depth", 20)

        post_mode = cfg.get("buffer", {}).get("mode", "shareNow")

        for i, clip in enumerate(clips, 1):
            # In addToQueue mode, Buffer handles time slot spacing automatically.
            # Only brief 3-5s spacing between API calls is needed.
            if i > 1:
                delay_s = 5 if post_mode == "addToQueue" else 180
                print(f"\nSpacing {delay_s}s before queueing next clip ({i}/{len(clips)})...")
                time.sleep(delay_s)

            try:
                url = upload_video(clip, folder="clips")
            except Exception as exc:
                print(f"Cloudinary upload failed for {clip.name}: {exc}")
                continue

            # LLM caption: one unique hook caption per clip (shared across channels).
            # Falls back to the per-service template whenever LLM is unavailable.
            llm_caption = None
            try:
                from llm.captions import generate_caption

                transcript_text = (
                    " ".join(
                        (seg.get("text") or seg.get("caption") or "").strip()
                        for seg in (transcript or [])
                    ).strip()
                    or None
                )
                llm_caption = generate_caption(
                    title,
                    transcript_text=transcript_text,
                    index=i,
                    total=len(clips),
                )
                if llm_caption:
                    print(f"LLM caption: {llm_caption[:80]}")
            except Exception as exc:
                print(f"LLM caption skipped: {str(exc)[:80]}")

            for channel in channels:
                service = channel.get("service")
                allowed, depth = can_queue_posts(channel["id"], max_queue_depth=max_queue)
                if not allowed:
                    msg = f"Queue full for {service} ({depth} pending) — skipping clip {clip.name}"
                    print(msg)
                    send_slack_alert(f"Queue Full on {service}", msg, is_error=False)
                    return False, posted, msg

                caption = llm_caption or build_caption(
                    cfg, title, i, len(clips), service=service
                )

                try:
                    post_id = create_post(
                        channel["id"], caption, url, service=service, mode=post_mode
                    )
                    posted += 1
                    print(
                        f"Published {clip.name} ({post_mode}) -> {service} "
                        f"({channel['name']}) id={post_id}"
                    )
                except QueueFullError as exc:
                    print(f"Queue limit (10 posts) reached for {service}: {exc}")
                    if posted > 0:
                        return True, posted, f"Queue filled to limit ({posted} clips queued)"
                    return False, 0, str(exc)
                except Exception as exc:
                    print(f"Post failed {clip.name} -> {service}: {exc}")

        if posted == 0:
            return False, 0, "No clips successfully posted"

        return True, posted, ""


def main():
    validate_env()

    start_time = time.time()
    cfg = load_config()
    prof_name = cfg.get("_active_profile_name", "Default")
    print(f"Running pipeline for Active Profile: [{prof_name}]")
    state = load_state()

    max_src_run = cfg.get("clipper", {}).get("max_sources_per_run", 1)
    ready = [s for s in state["sources"] if should_retry(s)]
    # Douyin play URLs expire ~1h after discovery — process the freshest ones
    # first, otherwise an old expired-URL source blocks fresh sources behind it.
    with_url = [s for s in ready if s.get("play_url")]
    with_url.sort(key=lambda s: s.get("discovered_at", ""), reverse=True)
    rest = [s for s in ready if not s.get("play_url")]
    pending = (with_url + rest)[:max_src_run]
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