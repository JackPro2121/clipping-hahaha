# Architecture — Deep Dive

This document goes module-by-module into **how** the pipeline works and **why** it is built this way.
It is the companion to `AGENTS.md` (operational reference). Read `AGENTS.md` first.

---

## 1. Data flow

```
 discovery ──► sources.json ──► download ──► clip engine ──► Cloudinary ──► Buffer ──► TikTok
 (bilibili     {url,title,    (requests/     (ffmpeg         (SDK          (GraphQL     (scheduled;
  popular)      status}        yt-dlp)         filters)        upload)       mutation)    needs confirm)
```

Two entrypoints, both invoked by the GitHub Action:

| Entrypoint | Command | Responsibility |
|---|---|---|
| `find_sources.py` | `python src/find_sources.py` | Append new pending URLs to `sources.json` |
| `main.py` | `python src/main.py` | Process every pending source end-to-end |

They are separate so discovery can be disabled without stopping the pipeline (§ config `discovery.enabled`).

---

## 2. Discovery

### bilibili (`src/bilibili.py`)
- Single source of truth: `GET https://api.bilibili.com/x/web-interface/popular`.
- Paginated (`ps=30`, `pn` increments) until `max_new_sources * 4` candidates are collected.
- Each item yields `{url, title, views, length}`. `length` comes from `item["duration"]` (seconds).
- No authentication, no `wbi` signing, no cookies — this endpoint is deliberately low-risk-control.
- Filters applied before returning: `length >= min_source_duration_s (40)` and
  `length <= max_duration_s (900)`.
- **Do not** use `x/web-interface/view` here — it is `412`-gated now (even from residential IPs) and
  requires `wbi` signing. The popular endpoint carries everything discovery needs (`bvid`, `cid`,
  `duration`, `stat.view`).

### ChocoData (`src/chocodata.py`) — YouTube, legacy path
- API base `https://api.chocodata.com/api/v1/youtube`.
- `discover()` dispatches on `discovery.strategy`: `channel` (via `/channel`, tab `videos`) or
  `search` (via `/search`, with optional `upload_date` mapped to YouTube `sp` filter tokens).
- Retries on 429 (honors `Retry-After`) and 5xx, max 3 attempts.
- `fetch_transcript(video_id, lang)` → list of `{start, duration, text}` (seconds); returns `None` when
  the video has no transcript.

---

## 3. Downloading

`src/download.py` dispatches on the URL. Two completely different worlds.

### 3.1 bilibili (primary) — pure `requests`
Rationale: yt-dlp's BiliBili extractor **must** scrape `https://www.bilibili.com/video/{bvid}` first.
bilibili's WAF returns `HTTP 412 Precondition Failed` to the GitHub Actions datacenter IP on that page.
Cookies + `--impersonate chrome` + `Referer` did **not** fix the runner (still 412). The reliable path
uses API endpoints that never touch the `www` edge and need no `wbi` signing:

```
_bili_headers(out_dir)
   └─ GET /x/frontend/finger/spi  → b_3, b_4  (buvid3/buvid4)
        Cookie: buvid3=…; buvid4=…; b_nut=<ts>; _uuid=<uuid4>
        UA = Chrome UA; Referer & Origin = https://www.bilibili.com
        also writes bili_cookies.txt (diagnostics)

_bili_api_get(url, headers)   → JSON with 3 retries / backoff

_bili_download(url, out_dir, max_duration_s)
   ├─ GET /x/player/pagelist?bvid=…            → pages[0]["cid"]
   ├─ GET /x/player/playurl?bvid=…&cid=…&qn={80,64,48,32}&fnval=16&fourk=1
   │       until data.dash is present
   ├─ pick video = max(video[], key=w*h); audio = max(audio[], key=bandwidth)
   ├─ GET baseUrl (fallback backupUrl[0]) stream → {bvid}_video.m4s
   ├─ GET baseUrl (fallback backupUrl[0]) stream → {bvid}_audio.m4s
   └─ ffmpeg -c copy -movflags +faststart → {bvid}.mp4
```

Notes:
- `fnval=16` gives the h264 (avc) DASH set. Some 720p-only streams are av1 and appear only with
  `fnval=4048`; we keep 16 for decode-safety. Observed ceiling: **480p** on many free videos.
- Multi-part videos return multiple pages; we take **page 1** only (matches `--no-playlist`).
- Streams come from `upos-*-mirror*.bilivideo.com` (Akamai) and require the `Referer` header.
- No trimming at download time — `max_duration_s` is only used as a page filter upstream; the clip
  engine picks windows later.

### 3.2 YouTube (fallback) — yt-dlp strategy ladder
`download_video()` tries `STRATEGIES` in order, each into its own dir:

| # | Name | `player_client` | Cookies | Notes |
|---|---|---|---|---|
| 1 | `embedded` | `web_embedded` | no | first, cheapest attempt |
| 2 | `cookies-default` | `default` | yes (`YT_COOKIES`) | needs base64 cookies env |
| 3 | `cookies-safari` | `web_safari` | yes | alternative client |
| 4 | `apify` | — | — | Apify actor `scraperoka/youtube-video-downloader` |

Flags used: `--js-runtime node --remote-components ejs:github` (for YouTube's n-challenge),
`--extractor-args youtube:player_client={client}`.

Apify details:
- Actor input: `{"video_urls":[{"url": ...}], "desired_resolution": "720p", "upload_video_to_apify": true}`.
- Download the `apify_storage_url` file (the actor's default output is **hardcoded 360p**).
- CDN links are IP-bound → must fetch through the API, not the raw URL.

`YT_COOKIES` (base64) is decoded to `cookies.txt` and passed via `--cookies`. **Never commit this file.**

---

## 4. Clip engine (`src/clip.py`)

Core idea: chop a source window into 4s chunks, apply per-chunk motion + a fade transition, concat,
then do global scale/captions/audio. Everything runs in ONE `ffmpeg -filter_complex` graph per clip.

### Window selection — `_select_windows()`
```
t = 0; while t < duration-2 and windows < max_clips:
    d = min(clip_length_s, duration - t)
    if d >= min_clip_s: windows.append((t, d))
    t += clip_length_s
```
For a 59.8s source with `clip_length_s=45, min_clip_s=30`: window `(0, 45)`; the `(45, 14.8)` window is
dropped → **1 clip**. For a 100.7s source: `(0,45), (45,45), (90,10.7→dropped)` → 2 clips.

### Chunking — `_chunks()`
Splits `(start, duration)` into `transition_every_s=4` chunks; last chunk shorter, min 1s.

### Per-chunk filter chain
```
[0:v]trim=start=CS:end=CE,
      setpts=PTS-STARTPTS,
      crop=… (static | pan | zoom window),
      setsar=1,
      [fade=t=in  (all but first chunk)]
      [fade=t=out (all but last chunk)]
      fps=25[c{i}]
```
- Motion (`MOTIONS[i % 3]`):
  - `pan_rl`: `crop=w:h:x='trunc((iw-w)*(1-t/dur))*2'`
  - `pan_lr`: `crop=w:h:x='trunc((iw-w)*t/dur)*2'`
  - `zoom_in`: static center crop then progressive `crop`+`scale` back to `w:h`
- `_center_crop()`: vertical aspect → `w = round(h*9/16)`, centered; if source is narrower than 9:16,
  it crops vertically instead.
- `setsar=1` after every crop/scale (else concat chokes on SAR mismatch).
- Fade-through-black at each 4s boundary (`transition_duration_s=0.15`).

### Concat
```
[c0][c1]…concat=n=N:v=1:a=0[vcat]
[a0][a1]…concat=n=N:v=0:a=1[acat]     (only if source has audio)
```
This is the deliberate replacement for `xfade` (see AGENTS.md §10.3).

### Post-concat (global)
```
[vcat]settb=AVTB,setpts=PTS-STARTPTS,scale=1080:1920,setsar=1
      [,eq=contrast=1.05:saturation=1.12:brightness=0.015,vignette=angle=PI/7]
      [,subtitles=filename='<escaped path>']
[vout]
```
- Subtitles only when a transcript exists AND `captions.burn_in` is on.
- ASS generation: `build_subtitles()` shifts transcript segments into window-local time, clips overlaps,
  wraps text to 3 lines × 20 chars (`_wrap`), styles `Arial 82 / Bold / Outline 4 / Shadow 0 /
  Alignment 2 (bottom) / MarginV 150`.
- On Windows the `.ass` path must go through `_filter_path()` (`\`→`/`, `:`→`\:`) inside
  `subtitles=filename='…'`.

### Audio
- BGM (`_make_bgm`): `sine 110 + 164.81 + 220` Hz → `amix`, `volume=0.5`, `tremolo=f=0.15:d=0.5`,
  `lowpass=1400`, stereo, `afade in 1.5s / out 1.0s`. Written to a `.wav` then mixed in.
- If source has audio: `[orig] aformat+volume=1.0`, `[1:a] aformat+volume=bgm_volume(0.35)`,
  `amix=inputs=2:duration=first:normalize=0[aout]`.
- If source is silent: BGM alone, else `anullsrc` for a silent track.

### Encode
```
libx264 veryfast crf 21 yuv420p
-force_key_frames expr:gte(t,n_forced*1)   # keyframe every 1s
-c:a aac -b:a 128k  -movflags +faststart
```
Failure path: rerun the same clip with `effects` disabled (`{enabled:False,bgm:False}`) and no
subtitles — keeps the pipeline alive on quirky sources.

---

## 5. Upload (`src/media.py`)
- `cloudinary.upload(resource_type="video", folder="clips", public_id=<clip stem>)`.
- Returns `secure_url`; that URL is what Buffer ingests.

---

## 6. Posting (`src/buffer_api.py`)
- Auth: `Authorization: Bearer <BUFFER_API_KEY>` against `https://api.buffer.com` (GraphQL).
- `get_org_id()`: first org under the account (org `6a85a8289189f6da59a63fb7`).
- `get_channels(["tiktok"])`: returns the TikTok channel (`6a85c601ccaf649a67d74968`).
- `create_post()` mutation:
  ```graphql
  mutation CreatePost($input: CreatePostInput!) {
    createPost(input: $input) {
      ... on PostActionSuccess { post { id text } }
      ... on MutationError { message }
    }
  }
  ```
  input: `{ text, channelId, schedulingType: "automatic", mode: "addToQueue",
           assets: [{ video: { url, metadata: { thumbnailOffset: 2000 } } }] }`
- `mode: "addToQueue"` + `schedulingType: "automatic"` → Buffer picks a slot; TikTok-side posting is
  still manual-confirm in the Buffer app (third-party limitation).

---

## 7. Failure semantics
- A failed source stays `pending` and is retried next run (`main.py` returns `False`).
- A full Buffer queue (`"queue full"` / `"Scheduled posts"`) aborts posting early and keeps the source
  pending so clips aren't dropped silently.
- `download_video` cleans up failed attempt dirs; the whole download raises if every strategy fails,
  which surfaces as a caught per-source failure in `main.py`.