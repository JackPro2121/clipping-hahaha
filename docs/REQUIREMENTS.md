# Requirements & Vision — What We Are Actually Building

This file is the user's own specification: **what he wants, what instructions he has given, and what
the project is really trying to build.** It is the "why" behind `AGENTS.md` (operations) and
`docs/ARCHITECTURE.md` (how). Read this before making product decisions.

> Operator language: Roman Urdu / Hindi. Code and docs stay in English, but the intent below is the
> user's own words, translated only where needed.

---

## 1. The vision — what the user actually wants to build

An **autonomous short-video factory** that runs itself on GitHub Actions for **$0**:

1. **Finds** the latest / trending videos from **Chinese apps** (bilibili right now) — no manual
   picking.
2. **Cuts** each into **30–90 second vertical (9:16) TikTok-style clips** that are
   **high-quality and watchable**, with:
   - **a transition every 4 seconds** that does **not** hurt visibility,
   - **well-styled burned-in captions** (the top quality priority),
   - motion (pan/zoom) so it doesn't feel static,
   - a soft synthesized background music track.
3. **Uploads** to Cloudinary, then **queues to Buffer** → TikTok channel.
4. The operator only has to **confirm each post in the Buffer app** (TikTok blocks third-party
   auto-publish — that limitation is accepted).

Net result the user wants: a TikTok channel that produces fresh, engaging short videos from
Chinese content **on autopilot, every few hours, without cost, without a personal machine**.

---

## 2. The instructions the user has given (verbatim intent)

| # | User's instruction | What it means for the build |
|---|---|---|
| 1 | **"30 to 90s ki video, har 4 sec k bd 1 transition jo visibility kharab na kare"** | Do NOT make 4-second clips. Make 30–90s videos. Inside each video, every 4 seconds there should be a transition — but it must be subtle, it must NOT hurt visibility. → drives the `clip_length_s=45 / transition_every_s=4 / transition_duration_s=0.15` concat+fade design. |
| 2 | **"abhi k liye aap chinese apps sy latest recent videos pick kr k tiktok pr post kro"** | For now: pull the latest/recent videos from Chinese apps (bilibili active) and post them to TikTok. → bilibili `popular` discovery + API downloader, Buffer→TikTok channel. |
| 3 | **"bilkul bkaar captions — styless, fonts, cropt"** (complaint about an earlier version) | The captions were bad: no style, bad fonts, cropped off-screen. Captions are a **top-quality bar**, not an afterthought. → styled ASS captions (Arial 82, bold, outline, bottom-margin, wrapped, non-cropped). **This is the #1 focus going forward.** |
| 4 | **"next time video captions pr focus krna"** | Next iteration must **focus on captions** — make them appear on the actual posted videos and look good. Today bilibili clips post **without any captions** (no transcript source) — that gap must close. |
| 5 | **"mai actually kya chhata hu / mny kya instructions de hai / kya build krna chahta hu — sb .md file mai likhna"** | Document the true requirements in one markdown file. → this file. |

---

## 3. Non-negotiable constraints (from the user + reality)

- **$0.** No paid service, no trial quota that runs out, no residential machine involved. Everything on
  the free GitHub Actions runner.
- **Fully automated.** Discovery → download → clip → upload → queue should need zero human input per run.
- **Chinese apps are the source** (bilibili). YouTube is effectively dead from the runner (Google
  bot-checks datacenter IPs) — see `PROBLEM.md`. Any YouTube support is legacy/fallback only.
- **TikTok = manual confirm.** Buffer queues posts as `scheduled`; the user confirms them in the Buffer
  app. Accept this — it cannot be automated by third parties.
- **Public repo, no secrets.** Everything committed must be safe to publish.

---

## 4. Captions — the current state and the #1 priority

### The user's requirement (in one line)
> Styled, readable, well-placed captions burned into the video — never ugly fonts, never cropped.

### What exists already (`src/clip.py`)
- ASS subtitle engine (`build_subtitles`): Arial, size 82, white text, black outline 4, semi-transparent
  back colour, bold, **Alignment 2 (bottom-center)**, `MarginV 150` (clear of the TikTok UI), wrapped to
  **3 lines × 20 chars** so nothing is cut off, timed to the video window.
- Rendered via ffmpeg `subtitles=filename='…'` inside the clip graph (`_filter_path` escaping for
  Windows drive colons).
- Already designed so caption text is **never cropped** (margin + wrap + 1080x1920 layout).

### Why captions still don't show on posted videos
- Captions are only burned when a **transcript** exists, and transcripts come from **ChocoData (YouTube
  only)**. bilibili has no transcript in this pipeline today → every bilibili clip posts **without
  captions**.
- So the styled caption engine is **built but unverified on real output**. This is the gap to close.

### The path forward (options to implement next)
1. **bilibili's own subtitle tracks.** bilibili stores AI-generated / uploader subtitles per video;
   the JSON subtitle list is exposed by the player API (e.g. `x/player/v2` or `wbi/v2`, returns
   `subtitle.subtitles[]` with a JSON `subtitle_url`). If reachable without `wbi` from the runner, this
   gives real caption text for Chinese videos. **Test first.**
2. **Fallback caption text** if no subtitle track: use the source title and a repeating short branded
   caption, or a fixed tagline — better than nothing, keeps the styled layout exercised.
3. **Keep the styled engine**, only change the *text source*. Do not regress fonts/placement.

### Acceptance criteria for captions (next iteration)
- Every posted clip has visible captions (or an intentional, documented exception).
- Text is fully on-screen: wrapped, bottom margin ≥ 100px, never clipped.
- Readable over any background: strong outline/shadow, high contrast.
- Timing syncs to the video window (no captions floating in wrong time).
- No encoding failures from the `subtitles` filter (Windows + Linux both).

---

## 5. What "done" looks like (product level)

A scheduled run (every 6h) should:
1. Discover 3 fresh bilibili videos.
2. Produce up to 3 clips each (30–90s, 9:16, transition every 4s, motion, bgm, **captions**).
3. Upload to Cloudinary, queue to Buffer → TikTok.
4. Log `Posted clip_01.mp4 -> tiktok (jackoscar287) id=…` for each.
5. Mark sources `processed`, commit state, and the user confirms posts in the Buffer app.

The user should never have to: run anything locally, choose videos, edit clips, or touch code for a
normal cycle.

---

## 6. Open questions for the user (to confirm next time)

- **Caption language for Chinese content:** Chinese AI-subtitles burned in as-is? Translate to English?
  Or captions in Roman-Urdu/Hindi? (Affects which subtitle source to use.)
- **Caption style preference:** minimal (small, subtle) vs. bold (YouTube-style thick outline)? Show a
  sample before mass-producing.
- **Queue volume:** keep 3 sources × 3 clips per 6h (9/day-ish), or reduce to avoid piling up?
- **Source appetite:** stick to bilibili `popular` (trending), or also rotate categories/regions?

---

*This file complements `AGENTS.md` (what/how to operate) and `docs/ARCHITECTURE.md` (how it works).*
*Keep it updated whenever the user states a new requirement — it is the spec, not a history log.*