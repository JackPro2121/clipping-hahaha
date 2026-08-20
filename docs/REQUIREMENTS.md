# Requirements & Vision — What We Are Actually Building

This file is the single source of truth for user specifications, strategic decisions, and product requirements.

---

## 1. The Core Vision

An **autonomous, $0-budget short-video production and distribution factory** that runs on **GitHub Actions**:

1. **Finds** high-engagement viral videos from **Chinese apps (Bilibili & Douyin)** targeting specific high-RPM niches (Woodworking, Antique Restoration, Precision Craftsmanship, Tech Inventions).
2. **Translates** Chinese titles & subtitles into fluent English for Tier-1 audiences (US, UK, Germany, France).
3. **Cuts** each video into **30–90 second vertical (9:16) clips** with:
   - A transition every 4 seconds,
   - Polished burned-in English captions with safe UI margins,
   - Subtle acoustic EQ & frequency shift to safely change digital audio fingerprints,
   - Soothing, low-volume ambient background music (`0.18`),
   - Crisp transparent Z-logo (`135px`) + persistent `@ZenCut` text watermark.
4. **Uploads** to Cloudinary and **queues to Buffer** for both **TikTok** and **Instagram Reels**.
5. **No-Watermark Guarantee**: 6% safe overscan margin and direct clean stream extraction ensure zero source watermarks.

---

## 2. Requirements & Implementation Matrix

| Requirement | User's Instruction | Status | Implementation Details |
|---|---|---|---|
| **Tier-1 Target CPM** | *"target audience US, UK, Germany, France... high CPM countries"* | ✅ Complete | English translation engine (`src/captions/translator.py`), high-RPM hashtags (`#satisfying #woodworking #craftsmanship`). |
| **No-Watermark Extraction** | *"bilibili ke watermark ke baghir download ho jaye... without watermark"* | ✅ Complete | Bilibili 6% overscan corner crop + Douyin direct `playwm`➔`play` clean stream extractor (`src/douyin.py`). |
| **Niche Consistency** | *"1 main category or aus ki sub categories ko target kry... v1, v2, v3"* | ✅ Complete | Profile-based pipeline architecture (`config.json` & `src/utils/config.py`). V1 locked to Satisfying Crafts & Restoration. |
| **Clean Video Captions** | *"video captions english mai likhy hony chahiye... clip 1/3 remove"* | ✅ Complete | Removed `clip 1/3` template. Dynamic engaging craft hook rotation (`MarginV=240` safe zone). |
| **Audio Transformation** | *"original audio ko thora sa change krdo... background mai slow sa music"* | ✅ Complete | Acoustic EQ + frequency variation alters digital fingerprint. Synthesized ambient lowpass chill BGM at volume `0.18`. |
| **Brand Identity** | *"z logo little bit size increase kro and @zencut ka watermark add kro"* | ✅ Complete | Z-logo enlarged to `135px` + persistent `@ZenCut` text watermark with drop shadow (`src/pipeline/brand.py`). |
| **Multi-Platform Posting** | *"buffer mai instagram account bhi attach kr diya hai... spaced gap upload"* | ✅ Complete | Automated posting to TikTok + Instagram Reels (`shouldShareToFeed: True`). Buffer schedule handles spacing. |

---

## 3. Non-Negotiable Constraints

- **$0 Budget**: Everything executes on free GitHub Actions runners without paid APIs.
- **Zero Secrets in Repo**: All API tokens and credentials sourced securely via environment variables / GitHub Secrets.
- **Automated Verification**: Full pytest test suite (49 unit tests) runs in CI before executing media downloads.