"""llm/captions.py — LLM-generated clip captions with template fallback.

Generates a unique hook caption per clip from the translated title and an
optional transcript excerpt. On any LLM failure the caller's fallback
(template caption) is returned unchanged.
"""

from llm.client import llm_complete

_PROMPT = (
    "You write short-form video captions for TikTok/Instagram Reels/Facebook Reels "
    "featuring Chinese craftsmanship videos (woodworking, restoration, machining, "
    "forging, jade carving). Given a translated title and optional transcript, write "
    "ONE caption:\n"
    "- one punchy hook sentence, max 120 characters before hashtags\n"
    "- end with 2-3 relevant hashtags (e.g. #woodworking #asmr #craft)\n"
    "- at most one emoji, no quotation marks, no preamble — output the caption only"
)


def generate_caption(title, transcript_text=None, fallback="", service=None, index=1, total=1):
    """Generate a caption via LLM; return `fallback` on any failure.

    Args:
        title: Translated English title of the source video.
        transcript_text: Optional transcript excerpt for context.
        fallback: Template caption to use when LLM is unavailable.
        service: Platform name (unused for now, kept for future per-platform tone).
        index/total: Clip position — multi-part clips keep the part suffix.

    Returns:
        str: LLM caption, or `fallback` unchanged.
    """
    context = title or ""
    if transcript_text:
        context += "\nTranscript excerpt: " + str(transcript_text)[:600]
    prompt = f"{_PROMPT}\n\nVideo info:\n{context}"

    try:
        text = llm_complete(prompt, max_tokens=200)
    except Exception:
        return fallback
    if not text:
        return fallback

    # Sanitize: collapse whitespace/newlines, strip wrapping quotes
    text = " ".join(text.split()).strip('"').strip("'").strip()
    if not (15 <= len(text) <= 240):
        return fallback

    # Preserve the multi-part marker the template would have added
    if total and total > 1 and "Part" not in text:
        text = f"{text} (Part {index}/{total})"
    return text
