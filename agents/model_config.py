"""
agents/model_config.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Centralised model selection, automatic fallback, and record/replay.

1. FALLBACK
   Google's flash models intermittently return 503 UNAVAILABLE. The right
   response is to try a DIFFERENT model immediately, not wait on the busy
   one. Each model in a chain gets exactly one attempt.

2. ONE FALLBACK LOOP FOR EVERYTHING  (new)
   generate_content_with_fallback() is the single place that walks a model
   chain. It is used by:
     - invoke_with_fallback()  — the three LangGraph agents (text prompts)
     - report_extractor        — PDF extraction (file + JSON schema)
   Previously the extractor called Google directly with one hard-coded
   model, so it was the only step with no fallback — and failed outright
   whenever that model was overloaded.

3. WHY google-genai IS CALLED DIRECTLY
   langchain-google-genai wraps google-genai, which has its own retry loop.
   HttpRetryOptions(attempts=1) disables retries at the layer that does them,
   so fallback fires in seconds instead of minutes.

4. RECORD / REPLAY / DEMO
   SAMARTH_LLM_MODE in .env:
     live    (default)  Always call Gemini; save each response for replay.
     replay             Return a saved response for an identical prompt with
                        no API call; otherwise call once and save it.
     demo               Replay ONLY. Never calls Gemini and needs no API key.
                        A prompt with no recording is an error. Used by the
                        public online demo (see demo/README.md).
   Applies to the three agents AND the RAG query embeddings. PDF extraction
   has its own content cache.

5. WHY "TODAY" CAN BE FROZEN
   The drafting prompt contains real dates (meeting date, service start,
   annual review). A recording made on one day never matches a prompt built
   on another day. current_date() returns SAMARTH_FIXED_DATE when set, and in
   demo mode the date the demo was recorded, so replays keep matching.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import hashlib
import json
import logging
import os
import time
from datetime import date, datetime, timezone
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
if LLM_MODE not in ("live", "replay", "demo"):
    logger.warning(f"Unknown SAMARTH_LLM_MODE '{LLM_MODE}' — using 'live'")
    LLM_MODE = "live"

DEMO_MODE = LLM_MODE == "demo"
DEMO_DIR  = Path(os.getenv("SAMARTH_DEMO_DIR", "./demo"))

# Where recordings are read and written. The demo uses its own committed
# folder; normal use keeps them in the git-ignored .llm_recordings/.
_RECORD_DIR = Path(os.getenv(
    "SAMARTH_RECORDINGS_DIR",
    str(DEMO_DIR / "recordings") if DEMO_MODE else "./.llm_recordings",
))
if not DEMO_MODE:
    _RECORD_DIR.mkdir(parents=True, exist_ok=True)

logger.info(f"🎛️  LLM mode: {LLM_MODE.upper()}")


class DemoRecordingMissing(RuntimeError):
    """Demo mode was asked for something that was never recorded."""


def _read_demo_manifest() -> dict:
    path = DEMO_DIR / "manifest.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def current_date() -> date:
    """
    "Today" as the pipeline should see it.
      1. SAMARTH_FIXED_DATE=YYYY-MM-DD, if set
      2. demo mode: the date the demo was recorded (demo/manifest.json)
      3. otherwise the real date
    """
    fixed = os.getenv("SAMARTH_FIXED_DATE", "").strip()
    if not fixed and DEMO_MODE:
        fixed = str(_read_demo_manifest().get("recorded_on", "")).strip()
    if fixed:
        try:
            return date.fromisoformat(fixed)
        except ValueError:
            logger.warning(f"Ignoring invalid fixed date '{fixed}' (use YYYY-MM-DD)")
    return date.today()


# ─────────────────────────────────────────────────────────────────────────────
# Model chains — first entry is the primary, the rest are fallbacks in order.
#
# 3.6-flash and 3.7-flash have been returning 503 for days, so every chain
# leads with a model that has been responding. They stay later in the chains
# and are used automatically once Google recovers.
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
    # Reading a PDF needs a capable model; lite is the last resort
    "extraction": [
        "gemini-3.5-flash",
        "gemini-3.6-flash",
        "gemini-3.7-flash",
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


# No key is fine in demo mode — nothing calls Gemini. Anything that does
# try gets a clear error from get_client() instead of a crash at startup.
_client = _build_client() if _API_KEY else None


def get_client() -> genai.Client:
    if _client is None:
        raise RuntimeError(
            "GOOGLE_API_KEY is not set, so Gemini cannot be called"
            + (" (the online demo only replays recorded runs)." if DEMO_MODE else ".")
        )
    return _client


# ─────────────────────────────────────────────────────────────────────────────
# Error classification
# ─────────────────────────────────────────────────────────────────────────────

def is_capacity_error(err: Exception) -> bool:
    """
    True when the error means "this model is busy, out of quota, or gone" —
    worth trying a DIFFERENT model rather than retrying this one.

      503 UNAVAILABLE        — overloaded
      429 RESOURCE_EXHAUSTED — quota hit
      500 INTERNAL           — transient server fault
      404 NOT_FOUND          — model retired / not available to this key
    """
    text = str(err)
    return any(code in text for code in (
        "503", "UNAVAILABLE",
        "429", "RESOURCE_EXHAUSTED",
        "500", "INTERNAL",
        "404", "NOT_FOUND",
    ))


# Kept for any code still importing the old name
_is_retryable_elsewhere = is_capacity_error


# ─────────────────────────────────────────────────────────────────────────────
# The single fallback loop
# ─────────────────────────────────────────────────────────────────────────────

def generate_content_with_fallback(role: str, contents, config=None, max_chain: int = None):
    """
    Call generate_content across the model chain for `role`, one attempt per
    model, moving on at the first capacity error.

    Args:
        role     : key in MODEL_CHAINS
        contents : anything google-genai accepts (text, Parts, Contents)
        config   : optional GenerateContentConfig (schema, temperature, …)

    Returns (response, model_name).
    Raises the last error if every model fails, or immediately on an error
    that is NOT about capacity (e.g. a bad request), since another model
    would fail the same way.
    """
    chain = get_models(role)
    if max_chain:
        chain = chain[:max_chain]

    last_error = None
    for attempt, model_name in enumerate(chain, start=1):
        try:
            if attempt > 1:
                logger.warning(f"  ↩️  Falling back to '{model_name}' (model {attempt} of {len(chain)})")

            started  = time.time()
            response = get_client().models.generate_content(
                model=model_name, contents=contents, config=config,
            )
            elapsed = time.time() - started

            if not (response.text or "").strip():
                # An empty reply (e.g. a safety block) — let the next model try
                raise RuntimeError(f"503 UNAVAILABLE: empty response from {model_name}")

            if attempt > 1:
                logger.info(f"  ✅ Succeeded on fallback '{model_name}' ({elapsed:.1f}s)")
            else:
                logger.info(f"  ✅ '{model_name}' responded ({elapsed:.1f}s)")
            return response, model_name

        except Exception as e:
            last_error = e
            if is_capacity_error(e) and attempt < len(chain):
                logger.warning(f"  ⚠️  '{model_name}' unavailable ({str(e)[:80]}…) — trying next")
                time.sleep(1)
                continue
            logger.error(
                f"  ❌ '{role}' failed on '{model_name}' "
                f"(model {attempt} of {len(chain)}): {str(e)[:120]}"
            )
            raise

    raise last_error


# ─────────────────────────────────────────────────────────────────────────────
# LangChain messages → google-genai request  (used by the three agents)
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
    system_parts, contents = [], []
    for m in messages:
        role = getattr(m, "type", "human")
        text = _message_text(m)
        if not text:
            continue
        if role == "system":
            system_parts.append(text)
        elif role in ("ai", "assistant"):
            contents.append(types.Content(role="model", parts=[types.Part.from_text(text=text)]))
        else:
            contents.append(types.Content(role="user", parts=[types.Part.from_text(text=text)]))
    return ("\n\n".join(system_parts) if system_parts else None), contents


# ─────────────────────────────────────────────────────────────────────────────
# Record / replay storage
# ─────────────────────────────────────────────────────────────────────────────

def _recording_key(role: str, messages) -> str:
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
        logger.warning(f"  Could not save recording ({e})")


# ─────────────────────────────────────────────────────────────────────────────
# Agent entry point
# ─────────────────────────────────────────────────────────────────────────────

def invoke_with_fallback(role: str, messages, max_chain: int = None):
    """
    Used by the scraper, compliance and drafting agents.
    Returns an object with `.content`, matching a LangChain response.
    """
    key = _recording_key(role, messages)

    if LLM_MODE in ("replay", "demo"):
        rec = _load_recording(key)
        if rec is not None:
            logger.info(
                f"  🔁 Replayed '{role}' from recording "
                f"(originally {rec.get('model', '?')}) — no API call"
            )
            return _Response(rec["text"], rec.get("model", "replay"), replayed=True)
        if DEMO_MODE:
            raise DemoRecordingMissing(
                f"No recording for the '{role}' step. The online demo can only "
                f"replay the sample students it was recorded with."
            )
        logger.info(f"  🔁 No recording for '{role}' yet — calling live once to record it")

    system_instruction, contents = _to_genai_request(messages)
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        temperature=TEMPERATURES.get(role, 0.3),
    )
    response, model_name = generate_content_with_fallback(role, contents, config, max_chain)

    text = response.text or ""
    _save_recording(key, role, model_name, text)
    return _Response(text, model_name)


# ─────────────────────────────────────────────────────────────────────────────
# RAG query embeddings — recorded the same way
# ─────────────────────────────────────────────────────────────────────────────

def embed_with_recording(text: str, model: str, task_type: str, compute):
    """
    Return the embedding vector for `text`, using a recording when allowed.

    `compute` is a zero-argument function that calls Gemini. Recording these
    makes the compliance step (which searches the legal documents) fully
    replayable, so the demo needs no API key at all.
    """
    h = hashlib.sha256()
    for part in (model, task_type, text):
        h.update(part.encode("utf-8"))
        h.update(b"\x00")
    key = f"embed_{h.hexdigest()[:24]}"

    if LLM_MODE in ("replay", "demo"):
        rec = _load_recording(key)
        if rec is not None and isinstance(rec.get("vector"), list):
            return rec["vector"]
        if DEMO_MODE:
            raise DemoRecordingMissing(
                "No recording for this legal-document search. The online demo "
                "can only replay the sample students it was recorded with."
            )

    vector = list(compute())
    try:
        _recording_path(key).write_text(json.dumps({
            "role":        "embedding",
            "model":       model,
            "task_type":   task_type,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "text":        text,
            "vector":      vector,
        }), encoding="utf-8")
    except Exception as e:
        logger.warning(f"  Could not save embedding recording ({e})")
    return vector
