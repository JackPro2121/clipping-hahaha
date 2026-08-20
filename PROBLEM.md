# Problem Statement: YouTube Download Bot-Check on GitHub Actions

## Project
Fully-automated $0 pipeline on GitHub Actions: auto-discover YouTube videos → download raw video → auto-clip (scene detection, 9:16 vertical, burned-in captions) → upload to Cloudinary → auto-post to social media via Buffer API (TikTok/Instagram/Twitter).

Repo: https://github.com/JackPro2121/clipping-hahaha (public, branch `main`)
Workflow: `.github/workflows/clip-and-post.yml`
Downloader: `src/download.py` (yt-dlp wrapper)

## The Exact Issue
On GitHub Actions runners (ubuntu-latest), yt-dlp fails to download YouTube videos with:

```
ERROR: [youtube] <VIDEO_ID>: Sign in to confirm you're not a bot.
Use --cookies-from-browser or --cookies for the authentication.
```

Same code works perfectly on a residential IP (developer's home machine).
The failure is inconsistent: one run succeeds, next run fails (probabilistic IP-based bot detection).

## Environment Facts
- Runner IP is a datacenter IP (GitHub Actions) — YouTube flags these.
- We pass valid browser cookies (`--cookies cookies.txt`) exported from a logged-in YouTube session (SID, __Secure-1PSID, SAPISID, etc.). Cookies validate OK from residential IP.
- With cookies, we use: `--extractor-args "youtube:player_client=web_embedded,web,mweb,web_safari"`, `--js-runtime node`, `--remote-components ejs:github` (for the n-challenge).
- Without cookies we use `player_client=android`.
- We already retry 5 rounds with 60-240s backoff. Still intermittently fails with the bot-check.
- We DO NOT want to run downloads on a residential machine — everything must stay on GitHub Actions (free, $0).

## What Has Been Tried (and failed)
1. **Free datacenter proxies** (WebShare 10 free proxies, ~100 free SOCKS5 proxies) → YouTube blocks datacenter IPs, all fail.
2. **Cookies on runner** → works sometimes, fails other times (intermittent). Current session may be flagged after cookies file was accidentally exposed in the public repo.
3. **Piped API / Invidious instances** → most instances down or 403.
4. **cobalt.tools** → v7 API shut down.

## Requirements
- $0 cost (free tier only, no paid subscriptions).
- Fully automated on GitHub Actions (no human machine required).
- Reliable: should not fail intermittently.
- Must download the actual video file (not just metadata).

## What Might Work (please investigate)
1. **Residential IP proxy** (Bright Data/Oxylabs/IPRoyal free trials ~1GB) — reliable but one-time free quota; not sustainable long-term.
2. **yt-dlp OAuth2 plugin** (`coletdjnz/yt-dlp-youtube-oauth2`) — signs in yt-dlp directly with a YouTube account OAuth token; more robust than cookies, but needs setup + a secondary throwaway account.
3. **PO tokens / GVS PO token** — `--extractor-args "youtube:po_token=..."`; newer yt-dlp challenge system, harder to set up.
4. **Fresh cookies from an incognito session** (export then immediately close window, never logout) — freeze a fresh session; best free bet.
5. **A different free video-hosting source** (TikTok, Instagram, Facebook reels) instead of YouTube — avoid YouTube's bot-check entirely.
6. **ChocoData/Apify-style API that returns a direct download URL** for the video.

## Files to Look At
- `src/download.py` — the yt-dlp wrapper with cookies/proxy/retry logic.
- `.github/workflows/clip-and-post.yml` — the workflow.
- `cookies-extension/` — a Brave/Chrome extension we built to export YouTube cookies.txt.
- `config.json` — pipeline settings.

## Goal
Give us the most reliable, free, fully-automated way to download YouTube videos from a GitHub Actions runner (datacenter IP), accepting that the developer can re-export cookies once every few weeks/months if needed.