# ZenCut — Autonomous $0-Budget Social Video Automation Pipeline

![ZenCut Logo](zencut-logo.png)

ZenCut is a fully-automated, **$0-budget content generation and distribution pipeline** running on **GitHub Actions**. It discovers high-engagement viral craftsmanship, woodworking, and tech videos from Chinese platforms (Bilibili, Douyin / TikTok China), translates titles and subtitles into fluent English, transforms the content into 9:16 vertical clips with transitions, branding, audio frequency variations, and ambient music, and schedules them to **TikTok** and **Instagram Reels** via Buffer.

---

## 🌟 Key Capabilities

- **Curated Top-Tier Creator Sourcing**:
  - **25 Verified Master Creators**: Actively samples from elite woodworking, antique restoration, Damascus forging, and precision CNC craft masters (e.g., *才疏学浅的才浅, 手工耿, 阿木爷爷, 王小师傅1, 机械造型*).
  - **Freshness-First Priority (`pubdate`)**: Sources brand new, newly-published uploads to ensure zero reuse competition on TikTok & Instagram Reels.
  - **Dynamic Random Sampling**: Randomizes the creator pool across runs for continuous content diversity.
- **100% No-Watermark Extraction**:
  - **Bilibili**: Direct Akamai CDN DASH stream extraction (`.m4s`) with 6% safe overscan margin to eliminate corner creator stamps and app logos.
  - **Douyin (TikTok China)**: Direct API extraction that dynamically swaps `playwm` to `play` for raw 1080p watermark-free MP4s.
- **Autonomous English Translation & Subtitle Engine**:
  - Real-time $0 translation of Chinese titles and subtitles into fluent English for Tier-1 audiences (US, UK, Germany, France).
  - High-retention 3.2s curiosity hook overlay: `🔨 Wait For The Result ✨\n{Craft Title}`.
- **Studio-Grade Transformative Video Engine (FFmpeg)**:
  - **Ultra-HD Video Pipeline**: 30 FPS standard with `flags=lanczos` multi-tap filtering and `-crf 18` visually lossless encoding.
  - **Organic Variable Pacing**: Replaces robotic cuts with natural human rhythms (`3.4s → 4.6s → 3.8s → 4.2s`).
  - **Expanded Motion Cycles**: 4 dynamic camera movements (`pan_rl`, `zoom_in`, `pan_lr`, `slow_zoom`).
  - **Cinematic Warm Color Grade**: Studio color balance curve (`colorbalance=rs=0.04:gs=0.01:bs=-0.035`) + unsharp texture enhancement.
  - **Studio ASMR Audio Layering**: Dynamic `compand` compressor + `highpass=55Hz` + 4.5kHz presence boost + calming 3-tone harmonic ambient soundscape.
- **Brand Identity & Social Footprint**:
  - Crisp transparent logo (`135px`) + persistent `@zencutofficials` watermark overlay.
  - Burned-in ASS captions in safe area (`MarginV=260`) to prevent UI overlap on TikTok & Instagram Reels.
- **Multi-Channel Social Distribution**:
  - Auto-posts to **TikTok** and **Instagram Reels** (`@zencutofficials`) via Buffer GraphQL API.
  - Respects Buffer queue limits with intelligent 71s human-like publish spacing.

---

## 🏗️ Architecture

```
.github/workflows/clip-and-post.yml
   │  1) Checkout, Python 3.12, FFmpeg, Pip Cache
   │  2) pytest tests/ -v                       → Run 57 automated unit tests
   │  3) python src/find_sources.py             → Creator & keyword discovery (writes sources.json)
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
        "strategy": "bilibili",
        "order": "pubdate",
        "bilibili_creators": [
          "才疏学浅的才浅",
          "手工耿",
          "阿木爷爷",
          "王小师傅1",
          "苏清吾",
          "玉师傅手工匠人",
          "我的修复师",
          "听雨剑阁",
          "机械造型"
        ],
        "keywords": ["木工", "木工雕刻", "老物件修复", "手工制作", "解压手工", "传统手艺", "机械制造", "刀剑锻造"],
        "min_views": 30000,
        "max_new_sources": 2
      },
      "buffer": {
        "hashtags": "#satisfying #woodworking #restoration #craftsmanship #handmade #diy #oddlysatisfying #fyp #foryou",
        "per_platform_captions": {
          "tiktok": "{title} ✨ Follow @zencutofficials for daily satisfying crafts & restoration! {hashtags}",
          "instagram": "Satisfying {title} ✨ Follow @zencutofficials for daily satisfying craft videos! {hashtags}"
        }
      }
    }
  }
}
```

---

## 🧪 Testing

Run the complete 57-test suite locally:

```bash
python -m pytest tests/ -v
```

---

## 📜 License
MIT License. Built for autonomous social video automation.
