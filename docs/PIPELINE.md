# Pipeline — How a Run Works

Step-by-step walkthrough of one GitHub Actions run, with the exact commands, workflow steps, and expected outputs.
Companion to `AGENTS.md` and `ARCHITECTURE.md`.

---

## 1. Trigger

`.github/workflows/clip-and-post.yml` runs on:
- `workflow_dispatch` — manual trigger from GitHub Actions dashboard.
- `schedule: "0 */6 * * *"` — recurring automated run every 6 hours (UTC).
- `concurrency: clip-post` guarantees only one run at a time to prevent race conditions.

---

## 2. Workflow Job Steps

| Step | Command | Responsibility |
|---|---|---|
| checkout | `actions/checkout@v4` | Fetches `main` branch |
| setup-python | `actions/setup-python@v5`, 3.12 | Initializes Python toolchain |
| Install ffmpeg | `apt-get install -y ffmpeg` | Installs system FFmpeg media processor |
| Install deps | `pip install -r requirements.txt` | Installs requests, cloudinary, yt-dlp, pytest |
| Run Test Suite | `pytest tests/ -v` | Executes 49 unit tests to validate pipeline health |
| Discover Sources | `python src/find_sources.py` | Profile-based keyword search & scoring; updates `sources.json` |
| Process & Post | `python src/main.py` | Downloads ➔ Translates ➔ Clips ➔ Uploads ➔ Buffer queue |
| Commit State | `git add sources.json; git commit; git push` | Persists processed markers and runtime metrics |

---

## 3. Discovery (`python src/find_sources.py`)

1. Load active profile configuration via `load_config()`.
2. Determine current keyword / category target in round-robin fashion (e.g. `木工` ➔ `修复` ➔ `解压` ➔ `手工` ➔ `机械制造`).
3. Query Bilibili Search API / Douyin Extractor.
4. Filter candidate sources by `min_views` (50,000+) and duration boundaries (`min_source_duration_s=35`, `max_duration_s=600`).
5. Score candidates (0–100 pts) based on engagement and length sweet-spots.
6. Append top candidate URLs to `sources.json` with status `"pending"`.

---

## 4. Pipeline Execution (`python src/main.py`)

For each pending source in `sources.json`:

1. **AI Translation**:
   - Chinese video title translated into fluent English.
   - Any embedded Chinese hashtags (`#高空伐木` etc.) stripped cleanly.
   - Subtitle segments translated into English for burn-in.
2. **Download Engine**:
   - **Bilibili**: Direct Akamai CDN DASH `.m4s` streams downloaded & merged.
   - **Douyin**: Direct clean `play_addr` extraction (watermark-free 1080p MP4).
3. **Clip Engine**:
   - 9:16 vertical crop with 6% safe overscan margin (eliminates any corner stamps/UIDs).
   - 4-second motion cycles (`pan_rl`, `pan_lr`, `zoom_in`).
   - Dynamic burned-in ASS captions in safe lower-third (`MarginV=240`).
   - Subtle acoustic EQ and frequency modification to change digital audio fingerprints.
   - Synthesized ambient background soundscape (lowpass 950Hz, volume `0.18`).
   - Transparent Z-logo (`135px`) + persistent `@ZenCut` text watermark overlay.
4. **Cloudinary Upload**:
   - Uploads rendered vertical `.mp4` to Cloudinary bucket.
5. **Buffer Queue Scheduling**:
   - Queues post to **TikTok (`jackoscar287`)** with `{title} 🔨✨ Wait for the end result! {hashtags}`.
   - Queues post to **Instagram Reels (`zencutofficials`)** with `metadata: { instagram: { type: "reel", shouldShareToFeed: True } }`.
   - Spaced out automatically across scheduled Buffer time slots.
6. **State Update**:
   - Source marked `"processed"`, retry counters cleared, Cloudinary 14-day GC executed.

---

## 5. Typical Runtime & Performance

| Stage | Duration |
|---|---|
| Setup & Pytest Validation | ~35 s |
| Keyword Discovery | ~2 s |
| Video Download (Bilibili/Douyin) | ~10–25 s |
| Rendering (1080x1920 with Filters & Audio) | ~15–30 s per clip |
| Cloudinary Upload & Buffer Queue | ~5 s per clip |
| Total Full Run (3 Sources / 5–6 Clips) | ~4–6 minutes |