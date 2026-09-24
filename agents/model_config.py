"""
agents/model_config.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Centralised model selection, automatic fallback, and record/replay.

1. FALLBACK
   Google's flash models intermittently return 503 UNAVAILABLE. The right
   response is to try a DIFFERENT model immediately, not wait on the busy
   one. Each model in a chain gets exactly one attempt.

2. WHY google-genai IS CALLED DIRECTLY
   langchain-google-genai wraps google-genai, which has its OWN retry loop
   (logs: "google_genai._api_client | Retrying ..."). max_retries=0 on the
   LangChain wrapper never reached it. Setting HttpRetryOptions(attempts=1)
   on the google-genai client disables retries at the layer that does them.

3. RECORD / REPLAY  (new)
   Most development work — PDF layout, the review editor, frontend tables —
   does not need a fresh AI response. Calling Gemini for it wastes quota and
   minutes per run.

   Set SAMARTH_LLM_MODE in .env:

     live    (default)  Always call Gemini. Every successful response is also
                        saved to ./.llm_recordings/ so it can be replayed.
     replay             If a recording exists for this exact prompt, return
                        it instantly with NO API call. If not, call Gemini
                        once and record it — so the first run fills the cache.

   Recordings are keyed by a hash of (role + full prompt). Change a prompt
   and the key changes, so you automatically get a fresh response rather
   than a stale one. Delete ./.llm_recordings/ to clear everything.

   Because scraper → compliance → drafting feed each other, replaying the
   scraper produces an identical compliance prompt, which then replays too.
   A whole IEP replays end to end with zero Gemini generation calls.

   Note: RAG embedding calls (gemini-embedding-2) are not recorded — they
   run on a separate, much more generous quota.

COMPATIBILITY
invoke_with_fallback() accepts LangChain messages and returns an object with
`.content`, so the three agents need NO changes.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
logger = logging.getLogger(__name__)

_API_KEY = os.getenv("GOOGLE_API_KEY")


# ─────────────────────────────────────────────────────────────────────────────
# Record / replay configuration
# ─────────────────────────────────────────────────────────────────────────────

LLM_MODE = os.getenv("SAMARTH_LLM_MODE", "live").strip().lower()
if LLM_MODE not in ("live", "replay"):
    logger.warning(f"Unknown SAMARTH_LLM_MODE '{LLM_MODE}' — using 'live'")
    LLM_MODE = "live"

_RECORD_DIR = Path("./.llm_recordings")
_RECORD_DIR.mkdir(parents=True, exist_ok=True)

logger.info(f"🎛️  LLM mode: {LLM_MODE.upper()}")


# ─────────────────────────────────────────────────────────────────────────────
# Model chains — first entry is the primary, the rest are fallbacks in order.
#
# Ordered around a live probe: gemini-3.5-flash-lite and gemini-3.5-flash were
# responding; 3.1-flash-lite, 3.6-flash and 3.7-flash returned 503.
# When the 503s clear, move 3.6-flash / 3.7-flash back to the front of
# compliance, drafting and extraction for better output quality.
# ─────────────────────────────────────────────────────────────────────────────

MODEL_CHAINS = {
    "scraper": [
        "gemini-3.5-flash-lite",
        "gemini-3.5-flash",
        "gemini-3.1-flash-lite",
    ],
    "compliance": [
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.6-flash",
        "gemini-3.7-flash",
    ],
    "drafting": [
        "gemini-3.5-flash",
        "gemini-3.7-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash-lite",
    ],
    "extraction": [
        "gemini-3.5-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash-lite",
    ],
}

TEMPERATURES = {
    "scraper":    0.2,
    "compliance": 0.1,
    "drafting":   0.4,
    "extraction": 0.1,
}


def get_models(role: str) -> list:
    return MODEL_CHAINS.get(role, ["gemini-3.5-flash"])


def primary_model(role: str) -> str:
    return get_models(role)[0]


# ─────────────────────────────────────────────────────────────────────────────
# Client with SDK-level retries disabled
# ─────────────────────────────────────────────────────────────────────────────

def _build_client() -> genai.Client:
    """
    One attempt per request — HttpRetryOptions(attempts=1) switches off the
    SDK's internal backoff. If the installed SDK predates the option, fall
    back to a default client and warn rather than crash on import.
    """
    try:
        client = genai.Client(
            api_key=_API_KEY,
            http_options=types.HttpOptions(
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )
        logger.info("  google-genai client: SDK retries disabled (fast fallback)")
        return client
    except (AttributeError, TypeError) as e:
        logger.warning(
            f"google-genai does not support HttpRetryOptions ({e}). "
            f"SDK retries remain enabled, so fallback will be slower."
        )
        return genai.Client(api_key=_API_KEY)


_client = _build_client()


# ─────────────────────────────────────────────────────────────────────────────
# LangChain message → google-genai request translation
# ─────────────────────────────────────────────────────────────────────────────

class _Response:
    """Minimal stand-in for a LangChain AIMessage — agents read `.content`."""
    def __init__(self, text: str, model: str, replayed: bool = False):
        self.content  = text
        self.model    = model
        self.replayed = replayed


def _message_text(message) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                parts.append(block.get("text", "") or "")
            else:
                parts.append(str(block))
        return "".join(parts)
    return str(content)


def _to_genai_request(messages):
    """SystemMessage → system_instruction; Human/AI → user/model turns."""
    system_parts = []
    contents     = []
    for m in messages:
        role = getattr(m, "type", "human")
        text = _message_text(m)
        if not text:
            continue
        if role == "system":
            system_parts.append(text)
        elif role in ("ai", "assistant"):
            contents.append(types.Content(
                role="model", parts=[types.Part.from_text(text=text)]))
        else:
            contents.append(types.Content(
                role="user", parts=[types.Part.from_text(text=text)]))
    system_instruction = "\n\n".join(system_parts) if system_parts else None
    return system_instruction, contents


# ─────────────────────────────────────────────────────────────────────────────
# Record / replay storage
# ─────────────────────────────────────────────────────────────────────────────

def _recording_key(role: str, messages) -> str:
    """
    Stable hash of the role plus the full prompt text.
    Any prompt change produces a new key, so edited prompts never replay
    an out-of-date response.
    """
    h = hashlib.sha256()
    h.update(role.encode("utf-8"))
    for m in messages:
        h.update(b"\x00")
        h.update(str(getattr(m, "type", "")).encode("utf-8"))
        h.update(b"\x00")
        h.update(_message_text(m).encode("utf-8"))
    return f"{role}_{h.hexdigest()[:24]}"


def _recording_path(key: str) -> Path:
    return _RECORD_DIR / f"{key}.json"


def _load_recording(key: str):
    path = _recording_path(key)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"  Recording unreadable ({e}) — calling live instead")
        return None


def _save_recording(key: str, role: str, model: str, text: str) -> None:
    try:
        _recording_path(key).write_text(json.dumps({
            "role":        role,
            "model":       model,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "text":        text,
        }, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        # Recording is a convenience — never let it break a live run
        logger.warning(f"  Could not save recording ({e})")


# ─────────────────────────────────────────────────────────────────────────────
# Fallback logic
# ─────────────────────────────────────────────────────────────────────────────

def _is_retryable_elsewhere(err: Exception) -> bool:
    """
    503 UNAVAILABLE / 429 RESOURCE_EXHAUSTED / 500 INTERNAL / 404 NOT_FOUND —
    all mean "try a different model", not "wait on this one".
    """
    text = str(err)
    return any(code in text for code in (
        "503", "UNAVAILABLE",
        "429", "RESOURCE_EXHAUSTED",
        "500", "INTERNAL",
        "404", "NOT_FOUND",
    ))


def _call_live(role: str, messages, max_chain: int = None) -> _Response:
    """Walk the model chain once, one attempt per model."""
    chain = get_models(role)
    if max_chain:
        chain = chain[:max_chain]

    system_instruction, contents = _to_genai_request(messages)
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        temperature=TEMPERATURES.get(role, 0.3),
    )

    last_error = None
    for attempt, model_name in enumerate(chain, start=1):
        try:
            if attempt > 1:
                logger.warning(
                    f"  ↩️  Falling back to '{model_name}' "
                    f"(model {attempt} of {len(chain)})"
                )
            started  = time.time()
            response = _client.models.generate_content(
                model=model_name, contents=contents, config=config,
            )
            elapsed = time.time() - started

            text = response.text or ""
            if not text.strip():
                raise RuntimeError(
                    f"503 UNAVAILABLE: empty response from {model_name}"
                )

            if attempt > 1:
                logger.info(f"  ✅ Succeeded on fallback '{model_name}' ({elapsed:.1f}s)")
            else:
                logger.info(f"  ✅ '{model_name}' responded ({elapsed:.1f}s)")
            return _Response(text, model_name)

        except Exception as e:
            last_error = e
            if _is_retryable_elsewhere(e) and attempt < len(chain):
                logger.warning(
                    f"  ⚠️  '{model_name}' unavailable ({str(e)[:80]}…) — trying next"
                )
                time.sleep(1)
                continue
            logger.error(
                f"  ❌ All {len(chain)} model(s) for '{role}' failed. "
                f"Last error: {str(e)[:120]}"
            )
            raise

    raise last_error


def invoke_with_fallback(role: str, messages, max_chain: int = None):
    """
    Entry point used by all three agents.

    replay mode: return a saved response if one exists for this exact prompt;
                 otherwise call live and record it.
    live mode:   always call live, and record the result for future replay.

    Returns an object with `.content`, matching a LangChain response.
    """
    key = _recording_key(role, messages)

    if LLM_MODE == "replay":
        rec = _load_recording(key)
        if rec is not None:
            logger.info(
                f"  🔁 Replayed '{role}' from recording "
                f"(originally {rec.get('model', '?')}) — no API call"
            )
            return _Response(rec["text"], rec.get("model", "replay"), replayed=True)
        logger.info(f"  🔁 No recording for '{role}' yet — calling live once to record it")

    response = _call_live(role, messages, max_chain=max_chain)
    _save_recording(key, role, response.model, response.content)
    return response