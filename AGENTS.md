# AGENTS.md

Comprehensive reference for the **Clipping-or-Posting** automation pipeline. Read this before
touching the codebase. It is the single source of truth for architecture, config, secrets,
known issues, and operating procedures.

---

## 1. Project Overview

Fully-automated, **$0-budget** pipeline that runs on **GitHub Actions**:

1. Discovers the latest / most popular videos from **Chinese apps (bilibili)** matching the **Active Profile** (e.g. V1: Woodworking, Restoration, Machine Art).
2. Auto-translates Chinese titles and subtitle segments into fluent English via $0 translation engine.
3. Downloads the raw video (via bilibili's public API, no login, no yt-dlp).
4. Clips it into **30–90s vertical TikTok-style videos** with **a transition every 4 seconds**, styled
   burned-in English captions, brand watermark (@ZenCut), motion variation, and synthesized ambient music.
5. Uploads clips to **Cloudinary**.
6. Queues tailored posts to **Buffer** for **TikTok**, **Instagram Reels**, and **Facebook Pages**.

- Repo: `https://github.com/JackPro2121/clipping-hahaha` (public, branch `main`)
- Owner: JackPro2121
- User language: Roman Urdu / Hindi (the pipeline's operator speaks these; code/comments stay in English).
- Cost: $0. No paid services. Everything must keep working on the free GitHub Actions runner.
- A **Chinese-app source** was chosen deliberately: YouTube download from the runner's datacenter IP is
  blocked by Google's bot-check (see `PROBLEM.md` and §9).

### Non-negotiable constraints
- Must stay $0 and fully automated on GitHub Actions (no residential machine involved).
- TikTok cannot be posted to directly by third parties → posts are queued as **scheduled** in Buffer and
  the user confirms/publishes them manually in the Buffer app.
- **Never commit secrets.** This repo is public. Cookies/tokens that are ever exposed must be rotated.

---

## 2. Stack

| Concern | Choice |
|---|---|
| Language | Python 3.12 |
| CI | GitHub Actions (`ubuntu-latest`) |
| Media engine | `ffmpeg` / `ffprobe` (installed in workflow) |
| YouTube downloader | `yt-dlp` (+ `curl_cffi` for impersonation) |
| bilibili downloader | Pure `requests` against bilibili's public JSON APIs |
| douyin downloader | Direct `requests` resolving aweme_id & clean `play` CDN URLs |
| Image/audio synthesis | `ffmpeg` lavfi filters (sine tones → chill ambient bgm) |
| Translation engine | Autonomous $0 Google web translation (Chinese → English) |
| Subtitle burn-in | `ffmpeg` `subtitles` filter with generated ASS files |
| Video hosting | `cloudinary` (official Python SDK) |
| Posting queue | Buffer GraphQL API (`api.buffer.com`) for TikTok, Instagram & Facebook |
| Transcripts | ChocoData API (YouTube only) / Bilibili player subtitle API |

`requirements.txt`:
```
yt-dlp
requests
cloudinary
curl_cffi>=0.10,<0.16        # yt-dlp requires 0.5.10 or 0.10–0.15.x; 0.16 is REJECTED by yt-dlp
pytest
```

Workflow ffmpeg install: `apt-get install ffmpeg`, falling back to the johnvansickle static build.
Runner has ffmpeg 6.1.1 (Ubuntu). **Local dev uses ffmpeg 8.1.2 gyan.dev** — see §9 gotchas
(xfade is broken there).

---

## 3. Architecture at a Glance

```
.github/workflows/clip-and-post.yml
   │  1) checkout, python, ffmpeg, pip install (with pip cache)
   │  2) pytest tests/ -v                → automated test suite validation
   │  3) python src/find_sources.py      → category discovery + quality scoring (writes sources.json)
   │  4) python src/main.py              → download → clip → upload → Buffer queue → Slack summary
   │  5) git commit sources.json (mark processed) + push
   │
config.json  ──────────────► read by find_sources.py and main.py
sources.json  ◄──────────── state: active sources, archived_urls, retry backoff, _meta metrics
src/
  find_sources.py       discovery entrypoint (creator-sourcing + quality scoring + category rotation)
  main.py               pipeline orchestrator (retry intelligence + cleanup + Slack summary)
  health_check.py       daily health check & queue monitoring
  bilibili.py           bilibili multi-category discovery & keyword search
  douyin.py             douyin no-watermark video extraction & topic discovery
  chocodata.py          ChocoData wrapper (YouTube discovery + transcripts)
  download.py           video download (bilibili API path + YouTube yt-dlp strategies + Douyin)
  clip.py               clipping engine (variable pacing, motion, captions, brand watermark, bgm)
  media.py              Cloudinary upload
  buffer_api.py         Buffer GraphQL client (_request helper + QueueFullError)
  captions/
    bilibili_subtitles.py   Bilibili subtitle API & title fallback caption builder
    translator.py           Autonomous $0 Chinese -> English translation
    whisper_transcriber.py  Local Whisper AI audio transcription & translation
  pipeline/
    creator_discovery.py    25 verified Chinese craft master scrapers & dynamic pool rotation
    quality.py          source video quality scorer (0-100 pts)
    cleanup.py          Cloudinary storage GC (14-day auto-purge)
    queue_manager.py    Buffer queue depth limiter
    brand.py            channel watermark & branding filter generator
  notifications/
    slack.py            Slack incoming webhook summaries and alerts
  utils/
    config.py           Active profile loader and configuration manager
    errors.py           custom exception hierarchy (QueueFullError, DownloadError, etc.)
    state.py            state management, auto-archiving (>30d), and exponential backoff
```

Flow for one source:
`find_sources.py` → appends new URLs to `sources.json` with `"status": "pending"` →
`main.py` iterates pending sources → for each: (optional) transcript → download →
`build_clips()` → Cloudinary upload each clip → `create_post()` to each Buffer channel →
mark `"processed"` and save `sources.json` → workflow commits the state change.

---

## 4. Module Reference

### `src/find_sources.py`
Discovery entrypoint. Reads `config.json → discovery`; if disabled, prints
`Discovery disabled in config` and exits 0. Dispatches on `discovery.strategy`:
- `"bilibili"` → `bilibili.discover(cfg)` (no API key needed).
- `"search"` / `"channel"` → `chocodata.discover(cfg)` (requires `CHOCODATA_API_KEY` env).

Dedupes against URLs already in `sources.json`, filters by `min_views`, appends up to
`discovery.max_new_sources` new sources with `"status": "pending"`, and saves.

### `src/bilibili.py`
Discovery for bilibili. `discover(cfg)`:
- Calls `GET https://api.bilibili.com/x/web-interface/popular?ps=30&pn={1..N}` (paginated) with a browser
  User-Agent. **No auth, no wbi signing, no cookies needed for this endpoint.**
- Filters by `discovery.max_duration_s` (900) and `discovery.min_source_duration_s` (40).
- Returns sources `{url: https://www.bilibili.com/video/{bvid}, title, views, length}`.
- Titles are Chinese (UTF-8). Be careful printing them on Windows consoles (cp1252) — use `json.dumps`
  escaping instead of raw `print`.

### `src/chocodata.py`
Wrapper for `https://api.chocodata.com/api/v1/youtube`. Used for **YouTube** discovery
(`/channel`, `/search`, `/suggest`) and **transcripts** (`/transcript`). Implements 429/5xx retries.
`parse_views`, `parse_length`, `extract_video_id`, `fetch_transcript`, `discover` are the main helpers.

### `src/main.py`
Orchestrator. `process_source(src, cfg)`:
1. Transcript: only if `captions.enabled` **and** the URL is YouTube (bilibili URLs are skipped — the
   transcript API is YouTube-specific; a bilibili URL would just waste an API call).
2. `download_video(url, work, max_duration_s=clipper.max_source_duration_s)` into a temp dir.
3. `build_clips(raw, work/"clips", {**clipper, "motion": cfg.motion}, transcript, burn_in)`.
4. If no clips → return `False` (source stays pending, retried next run).
5. For each clip: `media.upload_video(clip, folder="clips")` → Cloudinary URL → `create_post(...)`
   for every Buffer channel → print `Posted {clip.name} -> {service} ({channel}) id={post_id}`.
6. On Buffer "queue full" errors it stops posting and returns `False` (keeps source pending).
7. Success → source marked `"processed"`.

`build_caption(cfg, title, index, total)` formats `buffer.caption_template` with
`{title}`, `{index}`, `{total}`, `{hashtags}`.

### `src/download.py`
Dispatch logic in `download_video(url, out_dir, max_duration_s=None)`:
- **bilibili URL** (matches `_BILI_RE`) → `_bili_download(...)`: **API-only, no yt-dlp, no www scraping**
  (see §5 "bilibili downloader" for the exact flow and the 412 saga).
- **YouTube URL** → `_video_id()` then tries `STRATEGIES` in order:
  1. `embedded` (`player_client=web_embedded`, no cookies)
  2. `cookies-default` (`player_client=default`, with `--cookies`)
  3. `cookies-safari` (`player_client=web_safari`, with `--cookies`)
  4. `apify` (`_apify_download` — Apify actor `scraperoka/youtube-video-downloader`, uses
     `APIFY_TOKEN`; downloads the **storage file**, which is hardcoded 360p).
  Each attempt runs into its own `attempt-{i}-{name}/` dir; failures are cleaned up; retries with 5s
  sleep. The whole thing raises if all strategies fail.
- `YT_COOKIES` env (base64) is decoded to a `cookies.txt` for the cookie strategies.
- `_locate_output(dir, video_id)` finds the merged `{id}.mp4`.

### `src/clip.py`
The clipping engine. Detailed design in `docs/ARCHITECTURE.md` §"Clip engine". Key facts:
- `MOTIONS = ["pan_rl", "pan_lr", "zoom_in"]`, cycled per 4s chunk.
- `probe()` reads width/height/duration/has_audio via ffprobe.
- `_select_windows()`: windows at `t = 0, 45, 90, …`, each `clip_length_s=45`, dropped if
  `< min_clip_s=30`.
- `_chunks()` splits a window into `transition_every_s=4` chunks.
- Per chunk: absolute `trim` (no input `-ss`), `setpts=PTS-STARTPTS`, crop/pan/zoom, `setsar=1`,
  fade-in/out transitions (`transition_duration_s=0.15`), `fps=25`.
- Concatenates all chunks via the `concat` filter (video + audio separately).
- Then scale to 1080x1920 + `setsar=1`, optional `effects.subtle_filter`, optional
  `subtitles=filename='...'` (path escaped via `_filter_path` for Windows colons).
- Audio: optional synthesized bgm (`_make_bgm` — three sine tones, tremolo, lowpass, fades, mixed at
  `effects.bgm_volume`) + original audio via `amix`.
- Encodes `libx264 veryfast crf 21 yuv420p`, `-force_key_frames expr:gte(t,n_forced*1)` (keyframe every
  1s so social platforms can seek/cut), `-c:a aac -b:a 128k`, `-movflags +faststart`.
- On failure, retries once with effects/bgm/subtitles disabled.

### `src/media.py`
`upload_video(path, folder="clips")` → `cloudinary.upload(resource_type="video")` → returns
`result["secure_url"]`. Reads `CLOUDINARY_CLOUD_NAME/API_KEY/API_SECRET` from env.

### `src/buffer_api.py`
Buffer GraphQL client (`POST https://api.buffer.com`):
- `get_org_id()` → first org under the account.
- `get_channels(services)` → channels under that org, optionally filtered by service (e.g. `["tiktok"]`).
- `create_post(channel_id, text, video_url, thumbnail_offset=2000)` → mutation `createPost` with
  `mode: "addToQueue"`, `schedulingType: "automatic"`, assets video URL → returns post `id`.

---

## 5. The bilibili Downloader (API-only) — how and why

The runner's datacenter IP triggers bilibili's WAF **`HTTP 412 Precondition Failed`** on
`www.bilibili.com/video/{bvid}` (the page yt-dlp must scrape). We verified that even a residential IP
now gets 412 on `x/web-interface/view`, and that `x/player/playurl` without `wbi` signing returns
nothing useful. **The working path uses API endpoints that do NOT hit the www edge and do NOT need wbi
signing:**

1. **Fingerprint cookies** (`_bili_headers`): `GET https://api.bilibili.com/x/frontend/finger/spi`
   returns `b_3`/`b_4` (buvid3/buvid4 values). Build `Cookie` header:
   `buvid3; buvid4; b_nut=<ts>; _uuid=<uuid4>` plus browser UA, `Referer: https://www.bilibili.com/`,
   `Origin: https://www.bilibili.com`. Also writes a Netscape `bili_cookies.txt` (kept for diagnostics).
   This endpoint is reachable from the runner (verified).
2. **Page list** (`_bili_api_get`): `GET https://api.bilibili.com/x/player/pagelist?bvid={bvid}` →
   take `data[0].cid` (first part of a multi-part video, matching yt-dlp `--no-playlist` behavior).
   Works without wbi (verified).
3. **Stream URLs**: `GET https://api.bilibili.com/x/player/playurl?bvid={bvid}&cid={cid}&qn={qn}&fnval=16&fourk=1`
   with `qn` tried in order `80, 64, 48, 32` (720p→360p) until `data.dash` is present. Returns DASH
   `video[]` + `audio[]` m4s URLs on bilibili's CDN (Akamai `upos-*-mirror*`).
4. **Pick best**: video by max `width*height`; audio by max `bandwidth`. Uses `baseUrl`, falling back to
   `backupUrl[0]`.
5. **Stream download** (`_bili_stream_download`): `requests.get(..., stream=True)` in 1 MiB chunks,
   3 retries, honors the cookie/referer headers (CDN requires Referer).
6. **Merge**: `ffmpeg -c copy -movflags +faststart v.m4s a.m4s → {bvid}.mp4`. No trim here — the clip
   engine trims to windows later.

Quality ceiling: **up to 480p free** for many videos (720p/1080p premium-locked); still better than the
Apify 360p path. Vertical bilibili videos come through as e.g. `480x852`.

---

## 6. Configuration (`config.json`)

| Section | Field | Default | Meaning |
|---|---|---|---|
| `clipper` | `max_clips_per_video` | 3 | Max windows per source |
| | `clip_length_s` | 45 | Window length (30–90s target) |
| | `transition_every_s` | 4 | A transition every N seconds inside each clip |
| | `transition_duration_s` | 0.15 | Fade in/out duration at each boundary |
| | `min_clip_s` | 30 | Drop windows shorter than this |
| | `scene_threshold` | 0.3 | (reserved) scene detection |
| | `aspect` | `vertical` | `vertical` = 9:16 center crop |
| | `width` / `height` | 1080 / 1920 | Output resolution |
| | `max_source_duration_s` | 900 | Hard cap for downloads |
| `motion` | `enabled` | true | Motion applied (pan/zoom cycle) |
| | `zoom_factor` | 1.1 | Zoom strength |
| `effects` | `enabled` | true | Subtle color filter + bgm |
| | `bgm` | true | Synthesized background music |
| | `bgm_volume` | 0.35 | BGM mix level |
| | `subtle_filter` | eq+vignette string | ffmpeg filter chain |
| `captions` | `enabled` | true | Fetch transcript (YouTube only) |
| | `burn_in` | true | Burn captions into video |
| | `lang` | `en` | Transcript language |
| `discovery` | `enabled` | true | Turn on/off discovery |
| | `strategy` | `bilibili` | `bilibili` \| `search` \| `channel` |
| | `targets` / `search_terms` | [] | For YouTube strategies |
| | `min_views` | 10000 | Drop lower-view sources |
| | `max_duration_s` | 900 | Source duration cap |
| | `min_source_duration_s` | 40 | Source must be ≥40s for a good window |
| | `max_new_sources` | 3 | New sources added per run |
| `buffer` | `caption_template` | `{title} - clip {index}/{total} {hashtags}` | Post text |
| | `hashtags` | `#shorts` | Appended to caption |
| | `max_posts_per_channel` | 8 | Cap clips posted per channel |
| | `services` | [] | Channel service filter ([] = all) |

---

## 7. Secrets & Environment

### GitHub Actions secrets (repo → Settings → Secrets and variables → Actions)
| Secret | Used by | Purpose |
|---|---|---|
| `BUFFER_API_KEY` | `main.py → buffer_api.py` | Buffer auth (43-char token) |
| `CLOUDINARY_CLOUD_NAME` / `CLOUDINARY_API_KEY` / `CLOUDINARY_API_SECRET` | `media.py` | Cloudinary upload |
| `CHOCODATA_API_KEY` | `find_sources.py` / `main.py` | ChocoData discovery + transcripts |
| `YT_COOKIES` | `download.py` | Base64 Netscape cookies for YouTube |
| `APIFY_TOKEN` | `download.py` | Apify actor (YouTube fallback) |

### Local `.env` (gitignored)
Not read by the Python code directly — `main.py` reads env vars. If you run locally, export them.
Note the file uses **spaced/hyphenated keys**: `Buffer api key` and `CHOCODATA-API-KEY`. The real Buffer
key is the 43-char `Buffer api key` value (org `6a85a8289189f6da59a63fb7`, TikTok channel
`6a85c601ccaf649a67d74968`). A stale `BUFFER_API_KEY` value in the shell points at a *different* Buffer
org (a Twitter-only org) — always source Buffer creds from `Buffer api key` in `.env`.

---

## 8. State file — `sources.json`

```json
{
  "sources": [
    { "url": "https://www.bilibili.com/video/BV1bM8E6yEYd", "title": "...", "status": "processed" }
  ]
}
```
- `status` starts `pending`, becomes `processed` after a successful run (committed by the workflow).
- Pending entries that fail are kept pending and retried next run.
- Discovery dedupes by `url`, so processed URLs are never re-added.

---

## 9. Workflow & Automation

`.github/workflows/clip-and-post.yml`:
- Triggers: `workflow_dispatch` (manual) + `schedule: "0 */6 * * *"` (every 6 hours).
- Job steps: checkout → setup-python 3.12 → install ffmpeg (apt → static fallback) → `pip install -r
  requirements.txt` → `python src/find_sources.py` → `python src/main.py` → commit+push `sources.json`.
- `permissions: contents: write`; `concurrency: clip-post` (no parallel runs).

Manual trigger (no `gh` auth on some machines — can use REST API):
```powershell
$t = "GITHUB_TOKEN"
$body = '{"ref":"main"}' | ConvertTo-Json
Invoke-RestMethod -Uri "https://api.github.com/repos/JackPro2121/clipping-hahaha/actions/workflows/clip-and-post.yml/dispatches" `
  -Method Post -Headers @{ Authorization="Bearer $t"; "X-GitHub-Api-Version"="2022-11-28" } -ContentType "application/json" -Body $body
```

Watch a run:
```powershell
Invoke-RestMethod -Uri "https://api.github.com/repos/JackPro2121/clipping-hahaha/actions/runs" `
  -Headers @{ Authorization="Bearer $t"; "X-GitHub-Api-Version"="2022-11-28" }
```
Grab a run's job logs at `/actions/runs/{id}/jobs` → `/actions/jobs/{id}/logs`.

---

## 10. Known Issues & Hard-Won Lessons (READ THIS)

1. **YouTube is effectively dead from the runner.** Google bot-checks GitHub Actions datacenter IPs
   (`Sign in to confirm you're not a bot`). Cookies help intermittently but are unreliable, and an
   exposed session got flagged. The Apify storage path works but is **hardcoded 360p** and its CDN
   links are IP-bound. → **bilibili is now the primary source** (see `PROBLEM.md`).
2. **bilibili `www` → 412 on datacenter IPs.** Never try to scrape the video page from the runner.
   Use the API-only downloader (§5). This was verified end-to-end on the runner: `Download OK via
   'bilibili' -> BV….mp4` then clips posted to TikTok.
3. **`xfade` is BROKEN in ffmpeg 8.1.2 gyan.dev builds** (duplicate PTS `n/2` pattern → muxer truncates
   video at ~4s, "invalid DTS: PTS is less than DTS"). **Do not reintroduce `xfade`.** We use
   `concat` + per-chunk fade-in/out instead. The runner's ffmpeg 6.1.1 is fine, but keep the concat
   design portable.
4. **`setsar=1` on every chunk is required.** `scale` forces SAR 1:1 while `crop` keeps the source SAR;
   without `setsar=1` concat produces inconsistent SAR warnings and broken output.
5. **Windows subtitles path quoting.** Use `subtitles=filename='...'` with `_filter_path()`
   (`\` → `/`, `:` → `\:`) or the filter graph parser eats the drive letter.
6. **No `-ss`/`-t` input seek for clips.** Use absolute `trim=start=..:end=..` inside the filter graph;
   input seek + trims conflict and cause wrong windows.
7. **`-force_key_frames expr:gte(t,n_forced*1)`** = a keyframe every 1s → clean seeking/cutting for
   social platforms.
8. **Windows console (cp1252) cannot print Chinese bilibili titles.** Use `json.dumps(..., ensure_ascii=True)`
   when debugging; don't crash on `UnicodeEncodeError`.
9. **curl_cffi version**: yt-dlp accepts `0.5.10` or `0.10 ≤ x < 0.16`; **0.16 is rejected**
   (`Impersonate target "chrome" is not available`). `requirements.txt` pins `<0.16`.
10. **TikTok blocks third-party auto-publish.** Buffer queues posts as `scheduled`; the user must
    confirm/publish them in the Buffer app. Old queued posts can pile up — check the queue regularly.
11. **GitHub token exposure**: `ghp_31Ack…` was committed/used in plaintext. **It must be rotated**
    (GitHub → Settings → Developer settings → Personal access tokens → revoke). Don't put tokens in
    `.md` files in this repo (it's public).

---

## 11. Running Locally

```powershell
# 1. install deps (Python 3.12)
pip install -r requirements.txt
# ffmpeg on PATH (Windows: gyan.dev build OK, but remember xfade is broken there)

# 2. export env vars (load from .env: 'Buffer api key', 'CHOCODATA-API-KEY', CLOUDINARY_*, APIFY_TOKEN, YT_COOKIES)
#    NOTE: local .env uses 'Buffer api key' (spaces) — that is the correct Buffer key.

# 3. discovery (optional, writes sources.json)
python src/find_sources.py

# 4. pipeline (processes pending sources.json entries)
python src/main.py
```

---

## 12. Current Status & Open Tasks

- [x] Clip engine rewrite: 45s windows, transition every 4s, styled ASS captions, motion cycle, bgm
- [x] bilibili discovery (popular API) + API-only downloader (bypasses www 412) — verified on runner
- [x] End-to-end run: 3 videos → 9 clips posted to TikTok (scheduled in Buffer)
- [ ] **Rotate the exposed GitHub token** (`ghp_31Ack…`)
- [ ] Decide Buffer queue policy (older test clips may still be scheduled; TikTok queue fills each 6h run)
- [ ] Optional: restore per-source captions for non-Chinese content (bilibili has no transcript API here)
- [ ] Optional: explore a Chinese text-to-caption path or a fixed local source list

Docs:
- `docs/REQUIREMENTS.md` — **the user's spec**: what he actually wants, the instructions he gave, and
  the captions-focused vision. Read this before any product decision.
- `docs/PIPELINE.md`, `docs/ARCHITECTURE.md`, `docs/OPERATIONS.md`.
- Legacy problem statement: `PROBLEM.md`.