# ZenCut — Autonomous $0-Budget Social Video Automation Pipeline

![ZenCut Logo](zencut-logo.png)

ZenCut is a fully-automated, **$0-budget content generation and distribution pipeline** running on **GitHub Actions**. It discovers high-engagement viral craftsmanship, woodworking, and tech videos from Chinese platforms (Bilibili, Douyin / TikTok China), translates titles and subtitles into fluent English, transforms the content into 9:16 vertical clips with transitions, branding, audio frequency variations, and ambient music, and schedules them to **TikTok** and **Instagram Reels** via Buffer.

---

## 🌟 Key Capabilities

- **100% No-Watermark Extraction**:
  - **Bilibili**: Direct Akamai CDN DASH stream extraction (`.m4s`) with 6% safe overscan margin to eliminate corner creator stamps and app logos.
  - **Douyin (TikTok China)**: Direct API extraction that dynamically swaps `playwm` to `play` for raw 1080p watermark-free MP4s.
- **Autonomous English Translation Engine**:
  - Real-time $0 translation of Chinese titles and subtitles into fluent English for Tier-1 audiences (US, UK, Germany, France).
  - Automatically strips Chinese hashtags and generates high-converting English hooks.
- **Modular Pipeline Profiles**:
  - **V1 (`satisfying_crafts`)**: Woodworking, antique restoration, satisfying crafts, precision machine art.
  - **V2 (`future_tech_gadgets`)**: Smart gadgets, future tech inventions, novel tools.
  - **V3 (`street_food_asmr`)**: High-speed cooking, ASMR street food.
- **Smart Vertical Clip Engine (FFmpeg)**:
  - 1080x1920 9:16 vertical center-crop with 4-second motion cycles (pan-left, pan-right, smooth zoom).
  - Keyframe every 1s (`-force_key_frames expr:gte(t,n_forced*1)`) for clean social seeking and cutting.
  - Subtle acoustic EQ & frequency variation to change digital audio fingerprints safely without degrading natural ASMR sound.
  - Synthesized ambient chill background soundscape (lowpass 950Hz, volume `0.18`).
- **Brand Watermarking**:
  - Crisp transparent Z-logo (`135px`) + persistent `@ZenCut` text watermark with drop shadow.
  - Burned-in ASS captions in safe area (`MarginV=240`) to prevent UI overlap on TikTok & Instagram Reels.
- **Multi-Channel Social Distribution**:
  - Auto-posts to **TikTok** and **Instagram Reels** (`shouldShareToFeed: True`).
  - Respects Buffer free-tier 10-slot queue limits with automatic schedule spacing.

---

## 🏗️ Architecture

```
.github/workflows/clip-and-post.yml
   │  1) Checkout, Python 3.12, FFmpeg, Pip Cache
   │  2) pytest tests/ -v                       → Run 49 automated unit tests
   │  3) python src/find_sources.py             → Profile keyword discovery (writes sources.json)
   │  4) python src/main.py                     → Download → Translate → Clip → Cloudinary → Buffer
   │  5) Commit sources.json state & push
   │
config.json  ──────────────► Global & Active Profile Config
sources.json  ◄──────────── State Tracking & Auto-Archiving
```

---

## ⚙️ Configuration (`config.json`)

```json
{
  "active_profile": "satisfying_crafts",
  "profiles": {
    "satisfying_crafts": {
      "name": "Satisfying Crafts & Restoration",
      "discovery": {
        "keywords": ["木工", "修复", "解压", "手工", "机械制造"],
        "min_views": 50000,
        "max_new_sources": 3
      },
      "buffer": {
        "hashtags": "#satisfying #woodworking #restoration #craftsmanship #handmade #diy #oddlysatisfying #fyp #foryou",
        "per_platform_captions": {
          "tiktok": "{title} 🔨✨ Wait for the end result! {hashtags}",
          "instagram": "Satisfying {title} 🔨 Follow @ZenCut for daily satisfying craft videos! {hashtags}"
        }
      }
    }
  }
}
```

---

## 🔒 Secrets & Environment Variables

| Variable | Service | Purpose |
|---|---|---|
| `BUFFER_API_KEY` | Buffer GraphQL API | Authenticates post scheduling to TikTok & Instagram |
| `CLOUDINARY_CLOUD_NAME` | Cloudinary | Video hosting cloud name |
| `CLOUDINARY_API_KEY` | Cloudinary | Upload authorization |
| `CLOUDINARY_API_SECRET` | Cloudinary | Upload signing |
| `SLACK_WEBHOOK_URL` | Slack *(Optional)* | Run summaries & queue alerts |

---

## 🧪 Testing

Run the complete 49-test suite locally:

```bash
python -m pytest tests/ -v
```

---

## 📜 License
MIT License. Built for autonomous social video automation.
