# Architecture — Deep Dive

This document goes module-by-module into **how** the pipeline works and **why** it is built this way.
It is the companion to `AGENTS.md` (operational reference). Read `AGENTS.md` first.

---

## 1. Data flow

```
 discovery ──► sources.json ──► download ──► translator ──► clip engine ──► Cloudinary ──► Buffer ──► TikTok / IG Reels
 (bilibili     {url,title,    (bilibili      (Google web    (ffmpeg         (SDK          (GraphQL     (scheduled queue
  keywords/     status,        CDN /          $0 engine)     filters &       upload)       mutation)    per-platform)
  douyin)       score}         douyin)                       branding)
```

Two entrypoints, both invoked by the GitHub Action:

| Entrypoint | Command | Responsibility |
|---|---|---|
| `find_sources.py` | `python src/find_sources.py` | Profile keyword discovery & quality scoring, writes `sources.json` |
| `main.py` | `python src/main.py` | Full orchestrator: Download ➔ Translate ➔ Clip ➔ Cloudinary ➔ Buffer |

---

## 2. Profile-Based Configuration Architecture (`src/utils/config.py`)

The pipeline supports **Modular Pipeline Profiles** to operate dedicated accounts per niche:
- **V1 (`satisfying_crafts`)**: Woodworking, antique restoration, satisfying crafts, precision machine art.
- **V2 (`future_tech_gadgets`)**: Smart gadgets, future tech inventions, novel tools.
- **V3 (`street_food_asmr`)**: High-speed cooking, ASMR street food.

`load_config(path, profile_override=None)` merges the active profile's `discovery`, `buffer`, and `brand` settings into the global config seamlessly.

---

## 3. Discovery Engine

### 3.1 Bilibili Discovery (`src/bilibili.py`)
- **Keyword Search Mode**: Calls `GET https://api.bilibili.com/x/web-interface/search/type` with `search_type=video`, `order=click`, and profile-specific keywords (`木工`, `修复`, `解压`, etc.).
- **Category Ranking Mode**: Calls `GET https://api.bilibili.com/x/web-interface/ranking/v2` with category `rid` (e.g. food=76, tech=188).
- Uses `_bili_headers` for buvid3/buvid4 cookie injection to bypass WAF.
- Quality score (0–100 pts) filters out candidate videos below `min_views` (50,000+).

### 3.2 YouTube Discovery (`src/chocodata.py`) — Legacy
- Uses ChocoData API (`/search`, `/channel`) for YouTube keyword/channel discovery.

---

## 4. 100% No-Watermark Video Extraction (`src/download.py` & `src/douyin.py`)

### 4.1 Bilibili (CDN m4s Stream)
- Bilibili's Akamai CDN streams (`upos-*-mirror*.bilivideo.com`) do **not** carry platform watermarks.
- Requests DASH stream (`qn=80/64/48`), downloads video and audio `.m4s`, and merges with `ffmpeg -c copy`.
- To eliminate any creator-stamped corner UIDs or mobile app logos, a **6% safe-zone overscan margin** is applied in `_center_crop`.

### 4.2 Douyin / TikTok China (`src/douyin.py`)
- Resolves short share URLs (`v.douyin.com/...`) by following redirects to extract `aweme_id`.
- Queries Douyin item endpoint `https://www.iesdouyin.com/web/api/v2/aweme/iteminfo/?item_ids={aweme_id}`.
- Replaces `/playwm/` with `/play/` in the CDN URL to obtain the **100% watermark-free original 1080p MP4**.
- Stream downloads directly into the workspace.

---

## 5. Autonomous English Translation Engine (`src/captions/translator.py`)

- **$0 Free Translation Engine**: Uses Google Translate web endpoint with automatic fallback.
- **Title Translation**: Chinese titles are translated to fluent English for Buffer & social captions. Automatically strips embedded Chinese hashtags (`#高空伐木` etc.).
- **Subtitle Translation**: Subtitle tracks and title fallback segments are translated to English before rendering into ASS subtitle files for video burn-in.

---

## 6. Clip Engine (`src/clip.py`)

Everything runs in a single `ffmpeg -filter_complex` graph per clip.

### 6.1 Safe-Zone Overscan & Center-Crop (`_center_crop`)
- **Portrait/Vertical (9:16)**: Applies 6% overscan crop (`w = src_w * 0.94, h = w * 16/9`) to completely eliminate corner logos and UIDs.
- **Landscape/Horizontal (16:9)**: Center 9:16 crop (`h = src_h * 0.97, w = h * 9/16`) cuts 40% off each side.

### 6.2 Motion Cycle
- Chunks split into 4s intervals with fade transitions (`0.15s`).
- Cycles through `pan_rl`, `pan_lr`, and `zoom_in` (1.12x factor).

### 6.3 Burned-In Captions
- Formatted as ASS subtitles (`Fontsize=72, Bold, Outline 4, Alignment 2, MarginV=240`) placed in the safe lower-third above TikTok/Instagram UI controls.
- Dynamic hook rotation: `{Clean Title}` ➔ `"Satisfying Craftsmanship ✨"` ➔ `"Wait for the final result 🔨"` ➔ `"Follow @ZenCut for daily craft 🔥"`.

### 6.4 Audio Fingerprint Variation & Ambient BGM
- **Acoustic Variation**: `equalizer=f=280:t=q:w=1.2:g=1.0,equalizer=f=3200:t=q:w=1.0:g=-0.5,asetrate=44100*1.015,aresample=44100,atempo=1/1.015`. Alters digital audio frequencies to bypass automated copyright matching while preserving natural, crisp ASMR sounds.
- **Ambient BGM (`_make_bgm`)**: Synthesizes a warm, soothing ambient chord (C3/E3/G3, lowpass 950Hz, volume `0.18`).

### 6.5 Branding Overlay (`src/pipeline/brand.py`)
- Overlays transparent Z-logo (`135px`, `opacity: 0.92`) at `50:130`.
- Overlays persistent `@ZenCut` text watermark with drop shadow directly beneath the logo.

---

## 7. Multi-Channel Distribution (`src/buffer_api.py`)

- **TikTok (`jackoscar287`)**: Video queued with `{title} 🔨✨ Wait for the end result! {hashtags}`.
- **Instagram Reels (`zencutofficials`)**: Queued with `metadata: { instagram: { type: "reel", shouldShareToFeed: True } }` and tailored engagement captions.
- **Buffer Queue Spacing**: Uses Buffer's posting schedule to space out posts over the day.