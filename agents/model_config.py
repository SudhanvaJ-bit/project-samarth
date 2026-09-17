"""
agents/model_config.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Centralised model selection + automatic fallback.

WHY THIS EXISTS
Google's flash models intermittently return 503 UNAVAILABLE ("high
demand"). The SDK retries the SAME model with exponential backoff,
which is the wrong strategy for an overload — it just waits while an
equally good alternative sits idle. This module tries the primary
model, and on a server-side failure switches to the next model in the
chain instead of waiting.

It also keeps every model name in ONE file, so the next time Google
deprecates a model you edit here rather than hunting through 4 agents.

USAGE
    from agents.model_config import make_llm, invoke_with_fallback

    llm = make_llm("drafting")          # returns the primary client
    response = invoke_with_fallback("drafting", messages)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import logging
import os
import time

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()
logger = logging.getLogger(__name__)

_API_KEY = os.getenv("GOOGLE_API_KEY")


# ─────────────────────────────────────────────────────────────────────────────
# Model chains — first entry is the primary, the rest are fallbacks in order.
#
# Agents are deliberately spread across DIFFERENT primary models so they do
# not compete for the same per-minute quota bucket (free tier is 5 req/min
# PER MODEL, so four agents on one model = instant 429).
# ─────────────────────────────────────────────────────────────────────────────

MODEL_CHAINS = {
    # Simple structured extraction — cheapest model is enough
    "scraper": [
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-3.5-flash",
    ],
    # Legal cross-referencing — needs reasoning quality
    "compliance": [
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-3.7-flash",
    ],
    # Professional long-form writing — needs the most capability
    "drafting": [
        "gemini-3.7-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
    ],
    # PDF document understanding
    "extraction": [
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-3.7-flash",
    ],
}

# Per-agent sampling temperature
TEMPERATURES = {
    "scraper":    0.2,
    "compliance": 0.1,
    "drafting":   0.4,
    "extraction": 0.1,
}


def get_models(role: str) -> list:
    """Return the ordered model chain for an agent role."""
    return MODEL_CHAINS.get(role, ["gemini-3.5-flash"])


def primary_model(role: str) -> str:
    """Return just the primary model name for a role."""
    return get_models(role)[0]


def make_llm(role: str, model: str = None) -> ChatGoogleGenerativeAI:
    """
    Build a LangChain client for an agent role.
    Pass `model` to override (used internally by the fallback loop).
    """
    return ChatGoogleGenerativeAI(
        model=model or primary_model(role),
        temperature=TEMPERATURES.get(role, 0.3),
        google_api_key=_API_KEY,
    )


def _is_retryable_elsewhere(err: Exception) -> bool:
    """
    True when the error means "this model is busy/exhausted" — i.e. worth
    trying a DIFFERENT model rather than waiting on this one.

    Covers:
      503 UNAVAILABLE      — model overloaded (Google-side)
      429 RESOURCE_EXHAUSTED — per-minute or per-day quota hit
      500 INTERNAL         — transient server fault
    """
    text = str(err)
    return any(code in text for code in ("503", "UNAVAILABLE", "429",
                                         "RESOURCE_EXHAUSTED", "500", "INTERNAL"))


def invoke_with_fallback(role: str, messages, max_chain: int = None):
    """
    Invoke the model chain for `role`, moving to the next model whenever the
    current one is overloaded or quota-exhausted.

    Args:
        role      : "scraper" | "compliance" | "drafting" | "extraction"
        messages  : list of LangChain messages
        max_chain : optionally limit how many models to try

    Returns the LangChain response object.
    Raises the LAST error if every model in the chain fails.
    """
    chain = get_models(role)
    if max_chain:
        chain = chain[:max_chain]

    last_error = None

    for attempt, model_name in enumerate(chain, start=1):
        try:
            if attempt > 1:
                logger.warning(
                    f"  ↩️  Falling back to '{model_name}' "
                    f"(model {attempt} of {len(chain)})"
                )
            llm = make_llm(role, model=model_name)
            response = llm.invoke(messages)

            if attempt > 1:
                logger.info(f"  ✅ Succeeded on fallback model '{model_name}'")
            return response

        except Exception as e:
            last_error = e
            if _is_retryable_elsewhere(e) and attempt < len(chain):
                logger.warning(
                    f"  ⚠️  '{model_name}' unavailable ({str(e)[:120]}…) — "
                    f"trying next model immediately"
                )
                time.sleep(1)   # brief pause so we don't hammer the API
                continue
            # Not a capacity problem, or no models left — give up
            raise

    raise last_error