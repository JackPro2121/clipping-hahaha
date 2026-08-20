"""config.py — Profile-aware configuration loader.

Merges the active profile (e.g. V1 satisfying_crafts, V2 future_tech_gadgets)
into the global configuration cleanly.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def load_config(path=None, profile_override=None):
    """Load config.json and merge active profile settings.

    Args:
        path: Path to config.json (defaults to repo root).
        profile_override: Optional profile key to activate (e.g., 'satisfying_crafts').

    Returns:
        dict: Merged configuration dictionary.
    """
    config_path = Path(path) if path else (ROOT / "config.json")
    with open(config_path, encoding="utf-8") as f:
        cfg = json.load(f)

    profiles = cfg.get("profiles", {})
    active_key = profile_override or cfg.get("active_profile")

    if active_key and active_key in profiles:
        prof = profiles[active_key]
        prof_name = prof.get("name", active_key)

        # Merge discovery settings
        if "discovery" in prof:
            cfg.setdefault("discovery", {})
            cfg["discovery"].update(prof["discovery"])

        # Merge buffer settings (hashtags, templates, etc.)
        if "buffer" in prof:
            cfg.setdefault("buffer", {})
            cfg["buffer"].update(prof["buffer"])

        # Merge brand / effects if specified in profile
        if "brand" in prof:
            cfg.setdefault("brand", {})
            cfg["brand"].update(prof["brand"])

        cfg["_active_profile_key"] = active_key
        cfg["_active_profile_name"] = prof_name

    return cfg
