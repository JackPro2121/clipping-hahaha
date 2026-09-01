"""llm/client.py — minimal multi-provider LLM client with automatic fallback.

Providers are tried in order (Groq -> Gemini -> OpenRouter). Any failure
(missing key, timeout, rate limit, bad response) moves on to the next
provider. Returns None when every provider fails so callers can fall back
to rule-based logic — the pipeline must never depend on LLM availability.
"""

import os

import requests

_TIMEOUT_S = 25


def _providers():
    return [
        {
            "name": "groq",
            "key": os.environ.get("GROQ_API_KEY"),
            "url": "https://api.groq.com/openai/v1/chat/completions",
            "model": "llama-3.3-70b-versatile",
            "style": "openai",
        },
        {
            "name": "gemini",
            "key": os.environ.get("GEMINI_API_KEY"),
            "url": (
                "https://generativelanguage.googleapis.com/v1beta/models/"
                "gemini-1.5-flash:generateContent"
            ),
            "model": "gemini-1.5-flash",
            "style": "gemini",
        },
        {
            "name": "openrouter",
            "key": os.environ.get("OPENROUTER_API_KEY"),
            "url": "https://openrouter.ai/api/v1/chat/completions",
            "model": "meta-llama/llama-3.3-70b-instruct:free",
            "style": "openai",
        },
    ]


def llm_complete(prompt, max_tokens=250, temperature=0.8):
    """Return completion text from the first working provider, else None.

    Never raises — any provider error just moves to the next one.
    """
    for p in _providers():
        if not p["key"]:
            continue
        try:
            if p["style"] == "gemini":
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "maxOutputTokens": max_tokens,
                        "temperature": temperature,
                    },
                }
                headers = {"x-goog-api-key": p["key"], "Content-Type": "application/json"}
            else:
                payload = {
                    "model": p["model"],
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                }
                if p.get("reasoning_effort"):
                    payload["reasoning_effort"] = p["reasoning_effort"]
                headers = {
                    "Authorization": f"Bearer {p['key']}",
                    "Content-Type": "application/json",
                }
            resp = requests.post(p["url"], headers=headers, json=payload, timeout=_TIMEOUT_S)
            if resp.status_code != 200:
                print(f"llm[{p['name']}] HTTP {resp.status_code}, trying next provider")
                continue
            data = resp.json()
            if p["style"] == "gemini":
                text = data["candidates"][0]["content"]["parts"][0]["text"]
            else:
                text = data["choices"][0]["message"]["content"]
            if text and text.strip():
                # Some models emit a <think>...</think> reasoning block first — strip it
                if "<think>" in text:
                    text = text.split("</think>", 1)[-1]
                text = text.strip()
                if text:
                    return text
        except Exception as exc:
            print(f"llm[{p['name']}] failed: {str(exc)[:100]}")
    return None
