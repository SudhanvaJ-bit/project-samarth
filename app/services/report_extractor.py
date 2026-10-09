"""
app/services/report_extractor.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Extracts structured student data from psychoeducational report PDFs.

FIXES / FEATURES:
  [1] Structured output (response_schema) — guarantees valid JSON
  [2] _repair_json() fallback for malformed text-mode output
  [3] Age extraction — prompt forbids inferring age from grade number
  [4] Disability mapped to the correct RPwD Act 2016 Schedule category
  [5] Severity extracted explicitly, or inferred from grade gaps
  [6] Content cache — re-uploading the same PDF costs zero API calls
  [7] NEW — MODEL FALLBACK. Extraction used to call one hard-coded model
      (gemini-3.6-flash) directly, so it was the only pipeline step with no
      fallback, and failed whenever that model was overloaded. It now uses
      the shared chain in agents/model_config.py.
  [8] NEW — THE RIGHT FALLBACK FOR THE RIGHT ERROR. Structured → text mode
      helps when a model returns unparseable JSON. It does nothing when the
      model is overloaded. So:
        overloaded / quota / retired  → next MODEL (handled by the chain)
        bad JSON                      → text mode + repair
  [9] NEW — CACHE KEY NO LONGER NAMES THE MODEL. With fallback the model
      can differ between runs, so keying the cache by model would miss on
      identical PDFs. Old model-named cache files are still read, so
      existing cached reports keep working.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import hashlib
import json
import logging
import re
from pathlib import Path

from google.genai import types

from agents.model_config import generate_content_with_fallback, get_models, is_capacity_error

logger = logging.getLogger(__name__)


# ── [6][9] Extraction cache ───────────────────────────
_CACHE_DIR = Path("./.extraction_cache")
_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Bump when the prompt or schema changes, so older extractions aren't reused
_CACHE_VERSION = "v2"

# Models that older cache filenames may contain — read-only compatibility
_LEGACY_CACHE_MODELS = ["gemini-3.6-flash", "gemini-3.5-flash", "gemini-2.5-flash", "gemini-2.5-pro"]


def _digest(pdf_bytes: bytes) -> str:
    return hashlib.sha256(pdf_bytes).hexdigest()[:20]


def _cache_path(pdf_bytes: bytes) -> Path:
    return _CACHE_DIR / f"{_CACHE_VERSION}_{_digest(pdf_bytes)}.json"


def _read_cache(pdf_bytes: bytes):
    digest = _digest(pdf_bytes)
    candidates = [_cache_path(pdf_bytes)] + [
        _CACHE_DIR / f"{_CACHE_VERSION}_{m}_{digest}.json" for m in _LEGACY_CACHE_MODELS
    ]
    for path in candidates:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"  Cache file unreadable ({path.name}: {e}); trying next")
    return None


def _write_cache(pdf_bytes: bytes, data: dict) -> None:
    try:
        _cache_path(pdf_bytes).write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except Exception as e:
        logger.warning(f"  Cache write failed ({e}); continuing")


# ── [4] RPwD Act 2016 Schedule — disability category map ─
_RPWD_MAP = {
    "specific learning disorder":        "Specific Learning Disabilities",
    "specific learning disability":      "Specific Learning Disabilities",
    "learning disorder with impairment": "Specific Learning Disabilities",
    "learning disability":               "Specific Learning Disabilities",
    "learning disorder":                 "Specific Learning Disabilities",
    "dyslexia":                          "Specific Learning Disabilities",
    "dyscalculia":                       "Specific Learning Disabilities",
    "dysgraphia":                        "Specific Learning Disabilities",
    "reading disorder":                  "Specific Learning Disabilities",
    "disorder of written expression":    "Specific Learning Disabilities",
    "impairment in reading":             "Specific Learning Disabilities",
    "impairment in mathematics":         "Specific Learning Disabilities",
    "impairment in written":             "Specific Learning Disabilities",
    "sld":                               "Specific Learning Disabilities",
    "autism spectrum disorder":          "Autism Spectrum Disorder",
    "autism spectrum":                   "Autism Spectrum Disorder",
    "asperger":                          "Autism Spectrum Disorder",
    "asd":                               "Autism Spectrum Disorder",
    "intellectual disability":           "Intellectual Disability",
    "intellectual impairment":           "Intellectual Disability",
    "cognitive disability":              "Intellectual Disability",
    "cerebral palsy":                    "Cerebral Palsy",
    "speech and language disability":    "Speech and Language Disability",
    "language disorder":                 "Speech and Language Disability",
    "communication disorder":            "Speech and Language Disability",
    "speech sound disorder":             "Speech and Language Disability",
    "visual impairment":                 "Low Vision",
    "low vision":                        "Low Vision",
    "blindness":                         "Blindness",
    "hearing impairment":                "Hearing Impairment",
    "hard of hearing":                   "Hearing Impairment",
    "deaf":                              "Deaf",
}

_ADHD_TOKENS = {
    "attention deficit hyperactivity disorder",
    "attention-deficit/hyperactivity",
    "adhd", "add",
}


def _map_to_rpwd_category(raw_diagnosis: str) -> str:
    """
    Translate DSM-5 diagnostic language into the RPwD Act 2016 Schedule
    category. The two systems don't map one-to-one — ADHD, for instance, is
    not a named RPwD category.
    """
    raw = (raw_diagnosis or "").lower()
    matched = set()
    for key in sorted(_RPWD_MAP, key=len, reverse=True):
        if key in raw:
            matched.add(_RPWD_MAP[key])
    has_adhd = any(t in raw for t in _ADHD_TOKENS)

    if len(matched) > 1 and "Multiple Disabilities" in matched:
        matched.discard("Multiple Disabilities")
    if not matched:
        return "Other Specified Disability" if has_adhd else "Multiple Disabilities"
    if len(matched) == 1:
        return next(iter(matched))
    return "Multiple Disabilities"


def _infer_severity(raw_notes: str) -> str:
    """Infer severity when the report doesn't state it explicitly."""
    text = (raw_notes or "").lower()

    for word in ("severe", "moderate", "mild"):
        if re.search(rf'\bseverity\b[^.]*\b{word}\b', text):
            return word.capitalize()

    m = re.search(r'(\d+(?:\.\d+)?)\s*(?:grade\s+levels?|years?)\s+(?:below|behind)', text)
    if m:
        gap = float(m.group(1))
        if gap >= 3:
            return "Severe"
        if gap >= 1.5:
            return "Moderate"
        return "Mild"

    if any(s in text for s in ['well below average', 'extremely low', 'very low',
                               'unable to read', 'non-reader', 'severely impaired']):
        return "Severe"
    if any(s in text for s in ['below grade level', 'below average', 'low average',
                               'significant difficulties', 'marked difficulties']):
        return "Moderate"
    if any(s in text for s in ['slightly below', 'borderline', 'mild difficulties']):
        return "Mild"
    return "Moderate"


# ── [1] Structured output schema ──────────────────────
_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "student_name":         {"type": "STRING"},
        "age":                  {"type": "INTEGER"},
        "grade":                {"type": "STRING"},
        "school_name":          {"type": "STRING"},
        "disability_category":  {"type": "STRING"},
        "disability_severity":  {"type": "STRING"},
        "raw_notes":            {"type": "STRING"},
        "academic_history":     {"type": "STRING"},
        "teacher_observations": {"type": "STRING"},
        "parent_concerns":      {"type": "STRING"},
    },
    "required": [
        "student_name", "age", "grade", "school_name",
        "disability_category", "disability_severity", "raw_notes",
    ],
}


# ── [2] JSON repair ───────────────────────────────────
def _repair_json(raw: str) -> str:
    """Smart quotes → straight; strip trailing commas; escape newlines in strings."""
    raw = raw.replace("\u201c", '"').replace("\u201d", '"')
    raw = raw.replace("\u2018", "'").replace("\u2019", "'")
    raw = re.sub(r',(\s*[}\]])', r'\1', raw)

    out, in_string, escaped = [], False, False
    for ch in raw:
        if escaped:
            out.append(ch); escaped = False; continue
        if ch == "\\":
            out.append(ch); escaped = True; continue
        if ch == '"':
            in_string = not in_string; out.append(ch); continue
        if in_string and ch == "\n":
            out.append("\\n"); continue
        if in_string and ch == "\r":
            continue
        if in_string and ch == "\t":
            out.append("\\t"); continue
        out.append(ch)
    return "".join(out)


def _strip_fences(raw: str) -> str:
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = "\n".join(l for l in raw.split("\n") if not l.strip().startswith("```")).strip()
    return raw


_EXTRACTION_PROMPT = """You are extracting structured data from a psychoeducational evaluation report.

Read the PDF carefully and extract the following fields.

CRITICAL RULES:
1. "age": read the student's ACTUAL age from the "Age:" label or biographical
   details section. Do NOT infer age from the grade number. A Grade 9 student
   is typically 13-15 years old, NOT 9. Return an integer.

2. "disability_category": copy the EXACT diagnosis text from the report's
   conclusions, summary, or diagnoses section. Examples:
   "Specific Learning Disorder with impairment in Reading and Written Expression",
   "ADHD Combined Type", "Dyslexia". Do NOT paraphrase.

3. "disability_severity": look for explicit severity statements such as
   "Moderate severity" or "The level of severity is deemed to be Moderate".
   If not explicitly stated anywhere, return "Not Specified".

4. "raw_notes": a comprehensive narrative combining the Summary, Conclusion,
   Recommendations, test scores, behavioural observations, and background
   history. Minimum 300 words. Write it as flowing prose in a single string.

5. "grade": the student's current grade or year level as a string.
"""

_TEXT_MODE_SUFFIX = """

Return ONLY valid JSON with this exact structure. No markdown fences, no preamble.
Ensure all string values are properly escaped — no literal newlines inside strings.
{
  "student_name": "...", "age": 13, "grade": "9", "school_name": "...",
  "disability_category": "...", "disability_severity": "...",
  "raw_notes": "...", "academic_history": "...",
  "teacher_observations": "...", "parent_concerns": "..."
}"""


def _pdf_part(pdf_bytes: bytes):
    return types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")


def _extract_structured(pdf_bytes: bytes) -> dict:
    """Attempt 1: schema-enforced JSON, across the model chain."""
    response, model = generate_content_with_fallback(
        "extraction",
        [_pdf_part(pdf_bytes), types.Part.from_text(text=_EXTRACTION_PROMPT)],
        types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=_RESPONSE_SCHEMA,
            temperature=0.1,
        ),
    )
    data = json.loads(response.text)   # JSONDecodeError → caller tries text mode
    logger.info(f"  ✅ Structured output parsed ({model})")
    return data


def _extract_text_mode(pdf_bytes: bytes) -> dict:
    """Attempt 2: plain text + JSON repair, for when structured output misbehaves."""
    response, model = generate_content_with_fallback(
        "extraction",
        [_pdf_part(pdf_bytes), types.Part.from_text(text=_EXTRACTION_PROMPT + _TEXT_MODE_SUFFIX)],
        types.GenerateContentConfig(temperature=0.1),
    )
    raw_text = _strip_fences(response.text)
    try:
        data = json.loads(raw_text)
        logger.info(f"  ✅ Text mode parsed ({model})")
        return data
    except json.JSONDecodeError as parse_err:
        logger.warning(f"  JSON invalid ({parse_err}); attempting repair...")
        try:
            data = json.loads(_repair_json(raw_text))
            logger.info(f"  ✅ JSON repaired and parsed ({model})")
            return data
        except json.JSONDecodeError as final_err:
            logger.error(f"  ❌ JSON repair failed: {final_err}\n  Raw (first 1000 chars): {raw_text[:1000]}")
            raise ValueError(f"PDF extraction produced invalid JSON that could not be repaired: {final_err}")


def extract_student_data_from_pdf(pdf_bytes: bytes, use_cache: bool = True) -> dict:
    """
    Extract structured student data from a psychoeducational report PDF.

    Returns a dict ready for the IEP pipeline. Raises a readable error if
    every model is unavailable or the report can't be parsed.
    """
    # ── [6] Cache hit — no API call ───────────────────
    if use_cache:
        cached = _read_cache(pdf_bytes)
        if cached is not None:
            logger.info(
                f"  📦 Cache hit — no API call. "
                f"name: {cached.get('student_name')}, age: {cached.get('age')}"
            )
            return cached

    logger.info(f"📄 report_extractor: extracting PDF (models: {', '.join(get_models('extraction'))})")

    # ── [7][8] Right fallback for the right error ─────
    try:
        extracted = _extract_structured(pdf_bytes)
    except Exception as e:
        if is_capacity_error(e):
            # Every model in the chain was busy or out of quota. Text mode
            # would call the same models again and fail the same way.
            raise RuntimeError(
                "All Gemini models are currently unavailable (Google reports high demand). "
                "Please try again in a few minutes."
            ) from e
        logger.warning(f"  Structured output unusable ({str(e)[:100]}); trying text mode")
        extracted = _extract_text_mode(pdf_bytes)

    if not extracted:
        raise ValueError("PDF extraction returned no data.")

    # ── Validate critical fields ──────────────────────
    for field in ("student_name", "age", "disability_category", "raw_notes"):
        if not extracted.get(field):
            raise ValueError(f"PDF extraction missing required field: '{field}'")

    # ── [3] Age must be a plausible integer ───────────
    try:
        age_val = int(extracted["age"])
        if not (4 <= age_val <= 25):
            logger.warning(f"Extracted age {age_val} outside 4-25 for {extracted.get('student_name')}")
        extracted["age"] = age_val
    except (TypeError, ValueError):
        raise ValueError(f"Could not parse age as integer: {extracted['age']!r}")

    # ── [4] Map diagnosis to RPwD Schedule category ───
    raw_diagnosis = extracted.get("disability_category", "")
    rpwd_category = _map_to_rpwd_category(raw_diagnosis)
    logger.info(f"  Disability mapping: '{raw_diagnosis[:80]}' → '{rpwd_category}'")
    extracted["disability_category_raw"] = raw_diagnosis
    extracted["disability_category"]     = rpwd_category

    # ── [5] Severity — infer if unstated ──────────────
    severity = str(extracted.get("disability_severity", "")).strip()
    if not severity or severity.lower() in ("not specified", "n/a", "unknown", ""):
        severity = _infer_severity(extracted.get("raw_notes", ""))
        logger.info(f"  Severity inferred from notes: '{severity}'")
    extracted["disability_severity"] = severity

    if extracted.get("grade") is not None:
        extracted["grade"] = str(extracted["grade"])

    logger.info(
        f"  ✅ Extracted — name: {extracted['student_name']}, age: {extracted['age']}, "
        f"grade: {extracted.get('grade')}, disability: {extracted['disability_category']}, "
        f"severity: {extracted['disability_severity']}"
    )

    if use_cache:
        _write_cache(pdf_bytes, extracted)
        logger.info("  📦 Extraction cached — future uploads of this PDF are free")

    return extracted