# ZenCut — Autonomous $0-Budget Social Video Automation Pipeline

![ZenCut Logo](zencut-logo.png)

ZenCut is a fully-automated, **$0-budget content generation and distribution pipeline** running on **GitHub Actions**. It discovers high-engagement viral craftsmanship, woodworking, and restoration videos from Chinese master creators (Bilibili, Douyin / TikTok China), translates titles and subtitles into fluent English, transforms the content into 9:16 vertical clips with transitions, branding, acoustic ASMR enhancement, and ambient music, and schedules them simultaneously to **TikTok**, **Instagram Reels**, and **Facebook Pages** via Buffer.

---

## 🌟 Key Capabilities

- **Curated Top-Tier Creator Sourcing**:
  - **25 Verified Master Creators**: Actively samples from elite woodworking, antique restoration, Damascus forging, and precision CNC craft masters (e.g., *才疏学浅的才浅, 手工耿, 阿木爷爷, 王小师傅1, 机械造型*).
  - **Freshness-First Priority (`order="pubdate"`)**: Sources brand new, newly-published uploads to ensure zero reuse competition on social feeds.
  - **Dynamic Random Sampling**: Randomizes the creator pool across runs for continuous content diversity.
- **Smart Narrative Arc Window Selection**:
  - **Clip 1 (The Hook)**: Initial raw material transformation & cutting process (0s to 36s).
  - **Clip 2 (The Climax & Grand Reveal)**: The final polishing, oiling, and masterpiece reveal (`duration - 38s` to `duration - 2s`).
- **100% No-Watermark Extraction**:
  - **Bilibili**: Direct Akamai CDN DASH stream extraction (`.m4s`) with 6% safe overscan margin to eliminate corner creator stamps and app logos.
  - **Douyin (TikTok China)**: Direct API extraction that dynamically swaps `playwm` to `play` for raw 1080p watermark-free MP4s.
- **Autonomous English Translation & Subtitle Engine**:
  - Real-time $0 translation of Chinese titles and subtitles into fluent English for Tier-1 audiences (US, UK, Germany, France, Canada, Australia).
  - Faster-Whisper AI speech-to-text with Voice Activity Detection (VAD) and auto ASMR detection.
  - High-retention 3.2s curiosity hook overlay: `🔨 Wait For The Result ✨\n{Craft Title}`.
- **Studio-Grade Transformative Video Engine (FFmpeg)**:
  - **Ultra-HD Video Pipeline**: 30 FPS standard with `flags=lanczos` multi-tap filtering and `-crf 18` visually lossless encoding.
  - **Organic Variable Pacing**: Replaces robotic cuts with natural human rhythms (`[0.85, 1.15, 0.95, 1.05]`).
  - **Expanded Motion Cycles**: 4 dynamic camera movements (`pan_rl`, `zoom_in`, `pan_lr`, `slow_zoom`).
  - **Cinematic Warm Color Grade**: Studio color balance curve (`colorbalance=rs=0.04:gs=0.01:bs=-0.035`) + unsharp texture enhancement.
  - **Studio ASMR Audio Layering**: Dynamic `compand` compressor + `highpass=55Hz` + 4.5kHz presence boost + calming 3-tone harmonic ambient soundscape.
- **Brand Identity & Social Footprint**:
  - Crisp transparent Z-logo (`135px`) + persistent `@zencutofficials` watermark overlay in the top-left safe zone.
  - Burned-in ASS captions in safe area (`MarginV=240`) to prevent UI overlap on TikTok, Instagram, and Facebook Reels.
- **Multi-Channel Social Distribution**:
  - Auto-posts simultaneously to **TikTok** (`jackoscar287`), **Instagram Reels** (`zencutofficials`), and **Facebook** (`ZenCut`).
  - Safe **`addToQueue`** mode distributes posts cleanly across 5 daily peak High-CPM slots without account spam triggers.
  - 30-minute early-trigger schedule ensures zero-latency publishing on exact hours.

---

## 🏗️ Architecture

```
.github/workflows/clip-and-post.yml
   │  1) Checkout, Python 3.12, FFmpeg, Pip Cache
   │  2) pytest tests/ -v                       → Run 58 automated unit tests
   │  3) python src/find_sources.py             → Creator & keyword discovery (writes sources.json)
   │  4) python src/main.py                     → Download → Translate → Clip → Cloudinary → Buffer
   │  5) Commit sources.json state & push (with rebase safety)
   │
config.json  ──────────────► Global & Active Profile Config
sources.json  ◄──────────── State Tracking & Auto-Archiving
```

---

## ⏰ High-CPM Schedule Matrix (Karachi PKT & UTC)

| Pre-load Workflow Trigger | Target Buffer Publishing Slot | Target High-CPM Audience |
|---|---|---|
| **03:30 PM PKT** (10:30 UTC) | **04:00 PM PKT** (11:00 UTC) | UK Lunch & Europe Midday Scrolling |
| **09:30 PM PKT** (16:30 UTC) | **10:00 PM PKT** (17:00 UTC) | US East Afternoon & UK Evening Prime |
| **12:30 AM PKT** (19:30 UTC) | **01:00 AM PKT** (20:00 UTC) | **US East Coast Golden Prime Time 🔥** |
| **03:30 AM PKT** (22:30 UTC) | **04:00 AM PKT** (23:00 UTC) | US West Coast Evening Prime |
| **06:30 AM PKT** (01:30 UTC) | **07:00 AM PKT** (02:00 UTC) | **US West Coast / Australia Lunch Peak 🔥** |

---

## 🧪 Testing

Run the complete 58-test suite locally:

```bash
python -m pytest tests/ -v
```

---

## 📜 License

MIT License — $0 budget autonomous software architecture.
