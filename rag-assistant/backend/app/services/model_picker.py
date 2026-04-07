"""
Dynamic Gemini model picker.

At startup, queries the Google AI models endpoint to discover which models
are accessible with the configured API key. Picks the first model from the
preference list that is available. The result is cached for the process lifetime.

If GEMINI_MODEL is explicitly set in config/env, that value is always used.
"""

from __future__ import annotations
import logging
import urllib.request
import urllib.error
import json
from functools import lru_cache

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def resolve_gemini_model() -> str:
    """
    Return the Gemini model name to use.

    Resolution order:
    1. settings.GEMINI_MODEL if explicitly set
    2. First model in settings.GEMINI_MODEL_PREFERENCE that appears in
       the /v1beta/models response for this API key
    3. Hard fallback: "gemini-2.5-flash-lite"
    """
    from app.core.config import settings

    if settings.GEMINI_MODEL:
        logger.info(f"Using explicitly configured Gemini model: {settings.GEMINI_MODEL}")
        return settings.GEMINI_MODEL

    available = _fetch_available_models(settings.GOOGLE_API_KEY)

    if not available:
        fallback = settings.GEMINI_MODEL_PREFERENCE[0]
        logger.warning(
            "Could not fetch model list — falling back to %s", fallback
        )
        return fallback

    for candidate in settings.GEMINI_MODEL_PREFERENCE:
        # API returns "models/gemini-2.5-flash-lite" — strip prefix for comparison
        short_names = {m.removeprefix("models/") for m in available}
        if candidate in short_names:
            logger.info(
                "Auto-selected Gemini model: %s  (available: %s)",
                candidate,
                ", ".join(sorted(short_names)),
            )
            return candidate

    fallback = settings.GEMINI_MODEL_PREFERENCE[0]
    logger.warning(
        "No preferred model found in available list %s — using %s",
        available,
        fallback,
    )
    return fallback


def _fetch_available_models(api_key: str) -> list[str]:
    """Return list of model names accessible with this API key, or [] on error."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read())
        models = [m["name"] for m in data.get("models", []) if "gemini" in m.get("name", "")]
        logger.info("Fetched %d Gemini models from API.", len(models))
        return models
    except Exception as exc:
        logger.warning("Failed to fetch Gemini model list: %s", exc)
        return []