# Architecture — Deep Dive

This document goes module-by-module into **how** the pipeline works and **why** it is built this way.
It is the companion to `AGENTS.md` (operational reference). Read `AGENTS.md` first.

---

## 1. Data Flow

```
 discovery ──► sources.json ──► download ──► translator ──► smart windows ──► clip engine ──► LLM caption ──► Cloudinary ──► Buffer ──► TikTok / IG / FB
 (Apify douyin  {url,title,    (Douyin CDN    (Faster-Whisper (LLM transcript   (ffmpeg 6-tier  (Groq/Gemini/  (SDK          (GraphQL     (5 peak daily
  1080p + 25    status,        signed play    + Google web   OR audio-energy  Smart Narrative  OpenRouter     upload)       addToQueue   scheduled slots)
  Creators)     score}         ~1h expiry)    $0 engine)     peaks, LLM)      & ASMR audio)   fallback)                    mutation)
```

> **LLM subsystem**: provider fallback chain, captions, and smart-window tiers are documented in
> [`docs/LLM.md`](LLM.md). Every LLM step has a rule-based fallback — LLM outage degrades
> quality, never availability.

Two entrypoints, both invoked by the GitHub Action:

| Entrypoint | Command | Responsibility |
|---|---|---|
| `find_sources.py` | `python src/find_sources.py` | Creator discovery (`order="pubdate"`), quality scoring, writes `sources.json` |
| `main.py` | `python src/main.py` | Full orchestrator: Download ➔ Translate ➔ Clip ➔ Cloudinary ➔ Buffer |

---

## 2. Profile-Based Configuration Architecture (`src/utils/config.py`)

The pipeline supports **Modular Pipeline Profiles** to operate dedicated accounts per niche:
- **V1 (`satisfying_crafts`)**: Woodworking, antique restoration, satisfying crafts, precision machine art, Damascus forging.
- **V2 (`future_tech_gadgets`)**: Smart gadgets, future tech inventions, novel tools.
- **V3 (`street_food_asmr`)**: High-speed cooking, ASMR street food.

`load_config(path, profile_override=None)` merges the active profile's `discovery`, `buffer`, and `brand` settings into the global config seamlessly.

---

## 3. Discovery Engine

### 3.1 Curated Creator Discovery (`src/pipeline/creator_discovery.py`)
- **25 Verified Master Creators**: Pool of top-tier craftsmen (*才疏学浅的才浅, 手工耿, 阿木爷爷, 王小师傅1, 苏清吾, 玉师傅手工匠人, 我的修复师, 听雨剑阁, 机械造型*, etc.).
- **Freshness First (`order="pubdate"`)**: Calls `https://api.bilibili.com/x/web-interface/search/type?search_type=video&keyword={creator}&order=pubdate&page=1` to capture fresh videos within hours of release.
- **Dynamic Sampling**: Shuffles the pool on every run with `random.shuffle()` to maintain feed diversity.
- **Relaxed Threshold**: Verified creators use `creator_min_views: 1500` so newly uploaded masterpieces are captured before competitor aggregators find them.

---

## 4. 100% No-Watermark Video Extraction (`src/download.py` & `src/douyin.py`)

### 4.1 Bilibili (CDN m4s Stream)
- Bilibili's Akamai CDN streams (`upos-*-mirror*.bilivideo.com`) do **not** carry platform watermarks.
- Requests DASH stream (`qn=80/64/48`), downloads video and audio `.m4s`, and merges with `ffmpeg -c copy`.
- **Defensive Fallback**: If audio DASH stream is absent (silent/interleaved video), automatically synthesizes lossless stereo audio track without crashing.
- To eliminate any creator-stamped corner UIDs or mobile app logos, a **6% safe-zone overscan margin** is applied in `_center_crop`.

### 4.2 Douyin / TikTok China (`src/douyin.py`)
- Resolves short share URLs (`v.douyin.com/...`) by following redirects to extract `aweme_id`.
- Queries Douyin item endpoint `https://www.iesdouyin.com/web/api/v2/aweme/iteminfo/?item_ids={aweme_id}`.
- Replaces `/playwm/` with `/play/` in the CDN URL to obtain the **100% watermark-free original 1080p MP4**.

---

## 5. Autonomous Speech AI & Translation Engine (`src/captions/`)

- **Faster-Whisper AI Transcriber (`whisper_transcriber.py`)**:
  - Uses `int8` CPU quantization with Voice Activity Detection (VAD).
  - Translates spoken Chinese directly into English timestamped segments.
  - If speech probability is low (pure ASMR crafting), automatically disables subtitle burn-in for 100% clean visual immersion.
- **Google Translate Web Engine (`translator.py`)**:
  - Translates Chinese titles and subtitle segments to fluent English for Tier-1 audiences.
  - Strips Chinese hashtags (`#高空伐木` etc.) via regex cleaning.
- **3.2s Curiosity Hook (`bilibili_subtitles.py`)**:
  - Renders `🔨 Wait For The Result ✨\N{title}` during the first 3.2s to maximize 3-second scroll retention.

---

## 6. Transformative Video Engine (`src/clip.py`)

Everything runs in a single `ffmpeg -filter_complex` graph per clip.

### 6.1 Smart Narrative Arc (`_select_windows`)
- **Clip 1 (The Hook & Process)**: First 36 seconds (`0.0s` to `36.0s`) covering raw material cutting and shaping.
- **Clip 2 (The Climax & Grand Reveal)**: Final 36 seconds (`duration - 38.0s` to `duration - 2.0s`) capturing sanding, oiling, testing, and the finished masterpiece.

### 6.2 Organic Motion & Transitions
- Variable pacing chunks (`[0.85, 1.15, 0.95, 1.05]`) with `0.15s` smooth boundary transitions.
- Cycles through `pan_rl`, `pan_lr`, and `zoom_in` (1.12x Lanczos factor).

### 6.3 Studio ASMR Audio Compressor & Acoustic Variation
- `highpass=55, compand=..., equalizer=f=220:g=1.2, equalizer=f=4500:g=1.5, asetrate=44100*1.012, aresample=44100, atempo=1/1.012`.
- Boosts subtle tool carving sounds, tames harsh peaks, and shifts digital audio hash.

### 6.4 Branding Overlay (`src/pipeline/brand.py`)
- Overlays transparent Z-logo (`135px`) at top-left safe zone `50:130`.
- Overlays persistent `@zencutofficials` text watermark with drop shadow beneath the logo.

---

## 7. Multi-Channel Distribution (`src/buffer_api.py`)

- **TikTok (`jackoscar287`)**: Queued with `{title} ✨ Follow @zencutofficials for daily satisfying crafts & restoration! {hashtags}`.
- **Instagram Reels (`zencutofficials`)**: Queued with `metadata: { instagram: { type: "reel", shouldShareToFeed: True } }`.
- **Facebook Reels (`ZenCut`)**: Queued with `metadata: { facebook: { type: "reel" } }` for native Reels feed distribution.
- **Safe Mode**: Strictly **`mode: "addToQueue"`** spreading posts across 5 peak High-CPM slots without account spam triggers.
- **30-Minute Early Trigger**: GitHub Actions workflow triggers 30m prior to Buffer slots for zero-latency publishing on the exact hour.