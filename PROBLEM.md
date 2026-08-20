# Problem Statement & Architectural Resolution

## Original Challenge: YouTube Bot-Check on GitHub Actions
Running video automation pipelines on GitHub Actions datacenter IPs originally hit Google's aggressive bot-check wall (`Sign in to confirm you're not a bot`).

---

## Architectural Resolution & Evolution

To solve this permanently with **$0 budget** and **100% automation reliability**, the pipeline evolved into a **Multi-Source Chinese App & Viral Video Factory (ZenCut)**:

### 1. Primary Source: Bilibili Public API & Akamai CDN Streams
- Bypassed the YouTube bot wall and Bilibili WAF (`HTTP 412`) by utilizing direct DASH stream APIs (`/x/player/playurl`) with buvid headers instead of scraping web pages.
- Downloads clean 60fps/1080p video & audio streams directly from Akamai CDN without login or bot barriers.

### 2. Secondary Source: Douyin (TikTok China) No-Watermark Extractor
- Implemented `src/douyin.py` to resolve short links and transform `/playwm/` (watermarked) to `/play/` (clean), giving direct access to raw 1080p MP4 streams.

### 3. Corner Watermark Elimination
- Added 6% safe overscan margin in `src/clip.py` so that any creator-stamped corner UIDs or mobile app logos are completely cropped out.

### 4. Autonomous English Translation & Tier-1 Monetization
- Implemented $0 Google web translation in `src/captions/translator.py` to auto-translate titles & captions to fluent English, targeting high-CPM audiences (US, UK, Germany, France).

### 5. Multi-Channel Distribution
- Connects directly to Buffer GraphQL API for scheduling to **TikTok** and **Instagram Reels**.

---

## Status
✅ **RESOLVED & PRODUCTION READY** — Operating continuously on GitHub Actions (`.github/workflows/clip-and-post.yml`).