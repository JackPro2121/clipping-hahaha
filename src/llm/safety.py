"""llm/safety.py — Meta-moderation safety gate for candidate content.

Facebook restricted the ZenCut page after accident/injury videos ("血的教训"
angle-grinder accidents, workplace-safety PSAs) passed the craft keyword
filter. This module classifies titles/transcripts against Meta's
age-appropriate and dangerous-acts policies BEFORE a source enters the
pipeline.

Two tiers:
1. Keyword fast-path (zero cost, catches obvious Chinese/English signals).
2. LLM classification via the existing provider chain (Groq -> Gemini ->
   OpenRouter). Any LLM failure degrades to the keyword verdict — the
   pipeline must never depend on LLM availability (same contract as
   captions/windows).
"""

import json
import re

from llm.client import llm_complete

# ── Tier 1: deterministic keyword signals ────────────────────────────────
# Titles containing ANY of these are rejected without an LLM call.
_DANGEROUS_KW = [
    # Blood / injury / accidents (Chinese)
    "血", "事故", "受伤", "伤亡", "死亡", "死人", "惨", "急救", "伤口",
    "教训", "警示", "危险动作", "禁止", "不要模仿", "请勿模仿",
    # Explicit weapon violence
    "砍人", "杀人", "自杀",
    # Safety-PSA framing (these videos show accidents/injuries)
    "安全第一", "安全知识", "拒绝侥幸", "拿生命赌", "生命只有一次",
    # English equivalents
    "accident", "injur", "blood", "injur", "warning", "caught on camera",
    "gone wrong", "instant regret", "safety fail", "osha",
]

# Words that look dangerous but are safe in craft context (whitelist wins).
_SAFE_OVERRIDES = [
    # 锋利/刀 are core craft vocabulary; 教训 alone is ambiguous but
    # 血的教训-style titles are already caught above via 血.
    "锋利", "打磨", "抛光",
]


def _keyword_verdict(text):
    """Return (unsafe, matched_signals) from the keyword fast-path."""
    t = (text or "").lower()
    hits = [kw for kw in _DANGEROUS_KW if kw in t]
    if hits and any(ov in t for ov in _SAFE_OVERRIDES):
        # Whitelist context — only reject on the strongest signals.
        strong = [h for h in hits if h in ("血", "事故", "受伤", "死亡", "accident", "injur", "blood", "gone wrong")]
        hits = strong
    return (bool(hits), hits)


_PROMPT = """You are a content-safety classifier for a social media automation pipeline that posts short craft/woodworking/restoration clips to Facebook Reels, Instagram Reels and TikTok.

Classify the following content against Meta's content policies, especially:
- Dangerous acts / serious injury (real accidents, blood, near-misses shown graphically)
- Age-inappropriate content (would be unsuitable for under-18 recommendation)
- Violence, gore, self-harm
- Safety-PSA footage built around accident imagery

Content title: {title}
Transcript excerpt (may be empty): {transcript}

Reply with ONLY a JSON object, no other text:
{{"safe": true/false, "reason": "short reason", "severity": "none|low|medium|high"}}

Content is UNSAFE if it depicts real accidents, injuries, blood, dangerous tool
misuse presented as cautionary/shock content, or anything not age-appropriate.
Normal woodworking, carving, restoration, machining, ASMR crafting is SAFE even
when sharp tools, sparks or fire are used skillfully."""


def classify_content_safety(title, transcript=None, use_llm=True):
    """Return a verdict dict for a candidate source.

    Returns:
        {
          "safe": bool,
          "reason": str,
          "source": "keyword" | "llm" | "keyword+llm",
        }
    Never raises; on total failure defaults to safe=True (fail-open) with a
    printed warning — a missed clip is better than a broken pipeline, while
    the deterministic gate still catches known-bad patterns.
    """
    text = f"{title or ''} {transcript or ''}"
    kw_unsafe, kw_hits = _keyword_verdict(text)
    if kw_unsafe:
        return {
            "safe": False,
            "reason": f"dangerous-content keywords: {', '.join(kw_hits[:5])}",
            "source": "keyword",
        }

    if not use_llm:
        return {"safe": True, "reason": "keyword fast-path clean", "source": "keyword"}

    prompt = _PROMPT.format(
        title=(title or "")[:300],
        transcript=(transcript or "none")[:800],
    )
    try:
        raw = llm_complete(prompt, max_tokens=120, temperature=0.1)
        if raw:
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                verdict = json.loads(m.group(0))
                safe = bool(verdict.get("safe", True))
                reason = str(verdict.get("reason", ""))[:120]
                severity = str(verdict.get("severity", "none"))[:20]
                if not safe:
                    return {
                        "safe": False,
                        "reason": f"llm[{severity}]: {reason}",
                        "source": "llm",
                    }
                return {"safe": True, "reason": f"llm ok: {reason}", "source": "llm"}
    except Exception as exc:
        print(f"safety LLM check failed (fail-open): {str(exc)[:80]}")

    return {"safe": True, "reason": "keyword fast-path clean (llm unavailable)", "source": "keyword"}


# ── Niche relevance tier ─────────────────────────────────────────────────
# A palace-park calisthenics video titled "宫廷盘杠传承人…非遗正青春" passed the
# craft keyword gate because 非遗/传承 appear in the title, and reached the
# Buffer queue as "craft". Keyword lists cannot judge MEANING, so the LLM
# gets a veto on every candidate that survives the deterministic gates.
_DEFAULT_NICHE = (
    "Satisfying crafts & restoration: woodworking, wood carving, antique "
    "restoration/repair of old objects, forging & metalwork, stone/jade/clay "
    "craft, bamboo weaving, heritage handicrafts (embroidery, lacquer, "
    "paper-cut), precision machining, and hands-on making/ASMR build videos."
)

_RELEVANCE_PROMPT = """You are a niche-relevance classifier for a short-video channel that posts ONLY satisfying craft content.

Channel niche: {niche}

Content title: {title}

Reply with ONLY a JSON object, no other text:
{{"relevant": true/false, "reason": "short reason"}}

NOT relevant (reject): fitness/workout/street exercise, food/cooking/eating,
vlogs, daily life, gaming, anime, music, dance, travel, product reviews,
equipment reselling — even when the title claims 非遗/传承/传统技艺/文化 heritage
words. A culture CLAIM does not make exercise or food content a craft.
Relevant (accept): skillfully making, building, carving, forging, repairing or
restoring a physical object, or precision machine work."""


def classify_relevance(title, niche=None, use_llm=True):
    """Return a relevance verdict dict for a candidate source.

    Returns:
        {"relevant": bool, "reason": str, "source": "llm" | "disabled" | "failopen"}
    Never raises; on LLM failure fails OPEN (a missed clip is better than a
    broken pipeline) — the deterministic keyword gates still run first.
    """
    if not use_llm:
        return {"relevant": True, "reason": "llm disabled", "source": "disabled"}

    prompt = _RELEVANCE_PROMPT.format(
        niche=(niche or _DEFAULT_NICHE)[:400],
        title=(title or "")[:300],
    )
    try:
        raw = llm_complete(prompt, max_tokens=100, temperature=0.1)
        if raw:
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                verdict = json.loads(m.group(0))
                relevant = bool(verdict.get("relevant", True))
                reason = str(verdict.get("reason", ""))[:120]
                if not relevant:
                    return {"relevant": False, "reason": reason, "source": "llm"}
                return {"relevant": True, "reason": reason, "source": "llm"}
    except Exception as exc:
        print(f"relevance LLM check failed (fail-open): {str(exc)[:80]}")

    return {"relevant": True, "reason": "llm unavailable (fail-open)", "source": "failopen"}
