# Pipeline — How a Run Works

Step-by-step walkthrough of one GitHub Actions run, with the exact commands and what each one does.
Companion to `AGENTS.md` and `ARCHITECTURE.md`.

---

## 1. Trigger

`.github/workflows/clip-and-post.yml` runs on:
- `workflow_dispatch` — manual trigger (Settings → Actions → "Clip & Post" → Run workflow).
- `schedule: "0 */6 * * *"` — every 6 hours (UTC).

`concurrency: clip-post` guarantees only one run at a time; a new run waits for the old one.

## 2. Job steps

| Step | Command | What happens |
|---|---|---|
| checkout | `actions/checkout@v4` | Fetches `main` |
| setup-python | `actions/setup-python@v5`, 3.12 | Python toolchain |
| Install ffmpeg | `apt-get install -y ffmpeg` → static fallback | ffmpeg 6.1.1 on runner |
| Install deps | `pip install -r requirements.txt` | yt-dlp, requests, cloudinary, curl_cffi<0.16 |
| Discover | `python src/find_sources.py` | Reads config; appends new pending URLs to `sources.json` |
| Run pipeline | `python src/main.py` | Downloads → clips → uploads → queues posts → marks `processed` |
| Commit state | `git add sources.json; git commit; git push` | Persists processed markers + new sources |

## 3. Discovery (`python src/find_sources.py`)

1. Read `config.json`.
2. If `discovery.enabled == false` → print `Discovery disabled in config`, exit 0 (pipeline still runs
   on whatever is already pending).
3. Dispatch on `discovery.strategy`:
   - `bilibili` → `bilibili.discover(cfg)` (no key required).
   - `search` / `channel` → `chocodata.discover(cfg)` (requires `CHOCODATA_API_KEY`).
4. Load `sources.json`, build set of existing URLs.
5. Sort found sources by `views` desc; for each not-already-present and `views >= min_views` (if set),
   append `{url, title, status: "pending"}` until `max_new_sources` reached.
6. Save only if anything was added; print `Added {n} new sources`.

## 4. Pipeline (`python src/main.py`)

`main()`:
1. Load `config.json` + `sources.json`.
2. `pending = [s for s in sources if s.status != "processed"]`; if none → `No pending sources`, exit.
3. For each pending source → `process_source(src, cfg)`:

   a. **Transcript** (YouTube URLs only): `fetch_transcript(video_id, lang)`; failures are caught and
      printed, never fatal. bilibili URLs skip this (YouTube-specific API).
   b. **Download**: `download_video(url, work, max_duration_s=clipper.max_source_duration_s)`.
      - bilibili URL → API-only downloader (§ download.py).
      - YouTube URL → strategy ladder (embedded → cookies-default → cookies-safari → apify).
   c. **Clip**: `build_clips(raw, work/"clips", {**clipper, motion}, transcript, burn_in)`.
      - Produces `clip_01.mp4 … clip_0N.mp4` (N ≤ `max_clips_per_video`).
      - If no clips → keep source pending (return `False`).
   d. **Upload + post** (limit `max_posts_per_channel`):
      ```
      for i, clip in enumerate(clips, 1):
          url  = upload_video(clip, folder="clips")            # Cloudinary
          cap  = build_caption(cfg, title, i, len(clips))       # template + hashtags
          for channel in get_channels(services):
              post_id = create_post(channel["id"], cap, url)   # Buffer addToQueue
              print("Posted {clip} -> {service} ({channel}) id={post_id}")
      ```
      - "queue full" errors → stop posting, return `False` (source stays pending).
      - other post errors → print, continue to next clip/channel.
   e. If at least one post was created → return `True`.
4. On `True`: `src["status"] = "processed"`; save `sources.json`; print `Marked processed`.

## 5. Commit & push

The workflow commits `sources.json` (processed markers + any newly discovered URLs) and pushes to
`main`. A failed `main.py` still runs the commit step, so partial state is persisted and pending items
retry next time.

---

## 6. Timing expectations (measured)

| Stage | Typical time |
|---|---|
| Setup (checkout, python, ffmpeg, pip) | ~30–45 s |
| Discovery | ~1–2 s |
| Download one bilibili video (≤480p) | ~5–20 s |
| Clip one 45s window | ~10–20 s per clip |
| Cloudinary upload + Buffer post | a few s per clip |
| 3 videos × 3 clips (full run) | ~3–5 min total |

A run must finish before the job timeout (default 6h) — current runs use ~3–5 min.

---

## 7. What "success" looks like in logs

```
Added 3 new sources
Processing: https://www.bilibili.com/video/BV1BS876oEwP
bilibili BV1BS876oEwP: cid=41060401808
bilibili BV1BS876oEwP: picking video 480x852 + audio 124kbps
Download OK via 'bilibili' -> BV1BS876oEwP.mp4 (63MB)
Posted clip_01.mp4 -> tiktok (jackoscar287) id=6a86d742033879f23cb1e3b1
Posted clip_02.mp4 -> tiktok (jackoscar287) id=6a86d7459d8b5661e841edac
Posted clip_03.mp4 -> tiktok (jackoscar287) id=6a86d7479d8b5661e841ee29
Marked processed: https://www.bilibili.com/video/BV1BS876oEwP
...
```

After the run: posts appear as **scheduled** in the Buffer app under the TikTok channel. The operator
confirms/publishes them there (TikTok blocks third-party auto-publish).

---

## 8. Failure modes & their effect

| Failure | Effect |
|---|---|
| Discovery disabled / network error in discovery | `Discovery disabled in config` or `Discovery failed: …`; pipeline still runs pending sources |
| Download fails for a source | Source stays pending; retried next run |
| Clip encoding fails twice | Clip skipped for that window (if all fail → no clips → source stays pending) |
| Cloudinary upload fails | Exception propagates → source stays pending |
| Buffer queue full | Stops posting, keeps source pending |
| Buffer post error (other) | Printed, next post tried |
| `sources.json` commit conflicts | Rare; next run re-syncs on pull (manual `git pull --rebase` locally if needed) |