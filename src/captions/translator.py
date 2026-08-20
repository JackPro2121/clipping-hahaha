"""translator.py — $0 Free Translation engine for translating Chinese titles and subtitles to English.

Translates Chinese text into fluent English for Tier-1 audiences (US, UK, Germany, France).
Uses Google Translate web endpoint with automatic fallback.
"""

import html
import re
import urllib.parse
import requests

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )
}


def _has_chinese(text):
    """Detect if string contains Chinese characters."""
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


def translate_to_english(text, from_lang="auto"):
    """Translate text to English using free Google Translate web API.

    Args:
        text: Source string (Chinese, etc.).
        from_lang: Source language code ('auto' or 'zh-CN').

    Returns:
        str: English translated text. Returns original text if translation fails or if already English.
    """
    if not text or not str(text).strip():
        return ""

    clean_text = str(text).strip()
    if not _has_chinese(clean_text) and from_lang == "auto":
        return clean_text

    try:
        url = (
            f"https://translate.googleapis.com/translate_a/single"
            f"?client=gtx&sl={from_lang}&tl=en&dt=t&q={urllib.parse.quote(clean_text)}"
        )
        resp = requests.get(url, headers=_HEADERS, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            # Google Translate returns list of [[translated_segment, original_segment], ...]
            translated_segments = [seg[0] for seg in data[0] if seg and seg[0]]
            translated_text = "".join(translated_segments)
            return html.unescape(translated_text).strip()
    except Exception as exc:
        print(f"Translation failed for '{clean_text[:30]}...': {exc}")

    return clean_text


def translate_segments(segments):
    """Translate a list of caption segments ({start, duration, text}) to English."""
    if not segments:
        return segments

    translated = []
    for seg in segments:
        orig_text = seg.get("text", "")
        if _has_chinese(orig_text):
            eng_text = translate_to_english(orig_text, from_lang="zh-CN")
        else:
            eng_text = orig_text

        translated.append({
            "start": seg["start"],
            "duration": seg["duration"],
            "text": eng_text or orig_text,
        })
    return translated
