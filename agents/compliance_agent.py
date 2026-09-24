"""
agents/compliance_agent.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 5 — COMPLIANCE AGENT

The legal gatekeeper of Project SAMARTH.

How it works:
  1. Takes ExtractedInsights + StudentProfile from state
  2. Runs 4 targeted RAG queries against legal documents
  3. Injects retrieved law into Gemini prompt
  4. Gemini cross-references student needs vs law
  5. Returns ComplianceReport with verdict + citations

Input  : state["extracted_insights"] + state["student_profile"]
Output : state["compliance_report"]

FIXES IN THIS VERSION:
  [1] Bug 3 — compliance_report always contains a well-formed
      "mandatory_accommodations" list even when Gemini returns an
      empty or malformed one. A disability-specific baseline list is
      merged in so the drafting agent always has something to work with.
  [2] Gemini 3.x list response — response.content is now returned as a
      list of content blocks rather than a plain string. clean_json()
      coerces any shape to a string before calling .strip().
  [3] status field coercion — parsed["status"] may come back as a list;
      coerced to string before .lower().
  [4] NEW — JSON repair fallback. Gemini intermittently emits a trailing
      comma before a closing brace. _repair_json() fixes trailing commas,
      smart quotes, and unescaped newlines inside string values before
      the fallback report is used.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import json
import logging
import os
import re
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from agents.state import (
    IEPState, ComplianceReport,
    ComplianceStatus, WorkflowStatus
)
from rag.retriever import retriever
from agents.model_config import invoke_with_fallback

load_dotenv()
logger = logging.getLogger(__name__)

# ── Gemini Client ─────────────────────────────────────
#llm = ChatGoogleGenerativeAI(
#    model="gemini-3.6-flash",
#    temperature=0.1,
#    google_api_key=os.getenv("GOOGLE_API_KEY"),
#)

# ── System Prompt ─────────────────────────────────────
SYSTEM_PROMPT = """You are a strict legal compliance officer specializing 
in Indian disability education law. Your role is to audit IEP plans 
against the Rights of Persons with Disabilities (RPwD) Act 2016 
and NCTE/NCERT Guidelines.

Your mandate:
1. Be thorough — missing a legal obligation harms a vulnerable child
2. Cite SPECIFIC sections from the retrieved legal text
3. Distinguish MUST-HAVE (legal obligation) vs SHOULD-HAVE (best practice)
4. If in doubt, return "partial" not "compliant"

CRITICAL JSON RULES:
- Return a single JSON object. No trailing comma after the final field.
- No trailing comma before any closing brace or bracket.
- Use straight double quotes only. Never use smart/curly quotes.

Return ONLY valid JSON. No markdown, no explanation, no preamble."""


# ── [FIX 1] Baseline mandatory accommodations by disability ──
_BASELINE_ACCOMMODATIONS = {
    "Specific Learning Disabilities": [
        "Extended time (minimum 25% additional) on all tests and examinations (RPwD Act Section 17)",
        "Separate, quiet, distraction-free room for all assessments (RPwD Act Section 17)",
        "Use of assistive technology: text-to-speech and speech-to-text software",
        "Specialised reading instruction using explicit, multi-sensory methods",
        "Written language support including graphic organisers and structured writing frameworks",
        "Counselling or social-emotional support services",
        "General education teacher consultation / training on disability accommodations",
    ],
    "Autism Spectrum Disorder": [
        "Structured, predictable classroom environment with visual schedules",
        "Speech and language therapy",
        "Social skills training (individual or group)",
        "Sensory accommodation plan",
        "Extended time on assessments (RPwD Act Section 17)",
        "Separate room for assessments (RPwD Act Section 17)",
        "Behavioural support plan",
    ],
    "Intellectual Disability": [
        "Functional academic instruction adapted to cognitive level",
        "Life skills / daily living skills training",
        "Extended time on assessments (RPwD Act Section 17)",
        "Modified curriculum with simplified language and visual supports",
        "Speech and language therapy (if communication needs present)",
        "Occupational therapy evaluation",
        "Transition planning (if age 14+, RPwD Act Section 17)",
    ],
    "Speech and Language Disability": [
        "Direct speech and language therapy (minimum 2 sessions per week)",
        "AAC (Augmentative and Alternative Communication) evaluation",
        "Extended time on oral and written assessments (RPwD Act Section 17)",
        "Access to quiet space for verbal assessments",
        "General education classroom language support",
    ],
    "Other Specified Disability": [
        "Extended time (minimum 25%) on all assessments (RPwD Act Section 17)",
        "Separate, quiet testing environment (RPwD Act Section 17)",
        "Assistive technology as assessed",
        "Counselling or social-emotional support",
        "Specialised instruction matched to disability profile",
    ],
}

_DEFAULT_BASELINE = [
    "Extended time (minimum 25%) on all assessments (RPwD Act Section 17)",
    "Separate, quiet testing environment (RPwD Act Section 17)",
    "Assistive technology as appropriate to disability",
    "Specialised instruction by trained special educator",
    "Counselling or social-emotional support",
]


def _get_baseline_accommodations(disability_category: str, age: int) -> list:
    """Return baseline mandatory accommodations for a disability category."""
    baseline = list(
        _BASELINE_ACCOMMODATIONS.get(disability_category, _DEFAULT_BASELINE)
    )
    if age >= 14:
        transition = (
            "Transition planning: vocational guidance, post-secondary education, "
            "community living (RPwD Act Section 17)"
        )
        if transition not in baseline:
            baseline.append(transition)
    return baseline


def _merge_accommodations(gemini_list, baseline: list) -> list:
    """
    Merge Gemini-returned accommodations with the baseline list.
    Deduplicates by lowercased prefix match (first 30 chars).
    Baseline items win on conflict — they're legally anchored.
    """
    merged = list(baseline)
    baseline_keys = {item[:30].lower() for item in baseline}

    if not isinstance(gemini_list, list):
        gemini_list = [gemini_list] if gemini_list else []

    for item in gemini_list:
        if not isinstance(item, str):
            item = str(item) if item else ""
        item = item.strip()
        if not item:
            continue
        key = item[:30].lower()
        if key not in baseline_keys:
            merged.append(item)
            baseline_keys.add(key)

    return merged


def build_prompt(profile: dict, insights: dict, legal_text: str) -> str:
    age = int(profile.get("age", 0))
    needs_transition = age >= 14
    transition_note = (
        "YES — age 14+ requires transition plan" if needs_transition
        else "NO — below 14"
    )

    return f"""Conduct a legal compliance audit of this student's IEP plan.

━━━ STUDENT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Name             : {profile.get('student_name', 'N/A')}
Age              : {profile.get('age', 'N/A')} years
Disability       : {profile.get('disability_category', 'N/A')}
Severity         : {profile.get('disability_severity', 'N/A')}
Transition Needed: {transition_note}

━━━ EXTRACTED INSIGHTS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Strengths           : {json.dumps(insights.get('strengths', []))}
Challenges          : {json.dumps(insights.get('challenges', []))}
Recommended Supports: {json.dumps(insights.get('recommended_supports', []))}
Short-term Goals    : {json.dumps(insights.get('short_term_goals', []))}
Long-term Goals     : {json.dumps(insights.get('long_term_goals', []))}
Assistive Tech Needs: {json.dumps(insights.get('assistive_tech_needs', []))}

━━━ RETRIEVED LEGAL PROVISIONS ━━━━━━━━━━━━━━━━━━━━━━━
{legal_text}

━━━ YOUR TASK ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Cross-reference the student profile against the legal provisions.
Identify what MUST be in the IEP by law.

Return EXACTLY this JSON. All values must be plain strings or arrays of strings.
Do NOT put a comma after the last field.
{{
  "status": "compliant",
  "rpwd_relevant_sections": [
    "Section X: key legal obligation for this student"
  ],
  "ncte_relevant_sections": [
    "Guideline X.X: key standard for this student"
  ],
  "identified_gaps": [
    "Gap 1: specific missing element required by law"
  ],
  "mandatory_accommodations": [
    "Legally required item 1 with RPwD section reference",
    "Legally required item 2 with NCTE guideline reference"
  ],
  "compliance_notes": "Concise legal reasoning for the verdict."
}}

The "status" field must be exactly one of these three strings:
- "compliant"  : All legal requirements addressed
- "partial"    : Some gaps found but fixable in drafting
- "violation"  : Fundamental legal right being violated

IMPORTANT: mandatory_accommodations must be a non-empty array of strings.
Include every accommodation this student is legally entitled to."""


# ── [FIX 2] Gemini 3.x returns content as a list of blocks ──
def clean_json(raw) -> str:
    """
    Strip markdown fences if present.

    FIX: Gemini 3.x returns response.content as a list of content blocks
    rather than a plain string. Coerce any shape to a string first.
    """
    if isinstance(raw, list):
        parts = []
        for block in raw:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                parts.append(block.get("text", "") or block.get("content", ""))
            else:
                parts.append(str(block))
        raw = "".join(parts)
    elif not isinstance(raw, str):
        raw = str(raw)

    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        raw = "\n".join(lines)
    return raw.strip()


# ── [FIX 4] JSON repair fallback ──────────────────────
def _repair_json(raw: str) -> str:
    """
    Fix common LLM JSON breakages before giving up on the response.

      1. Smart/curly quotes  →  straight quotes
      2. Trailing commas before } or ]  (the observed failure mode)
      3. Literal newlines/tabs inside string values  →  escaped

    The newline pass tracks whether it is inside a JSON string literal,
    so structural whitespace between fields is left untouched.
    """
    raw = raw.replace("\u201c", '"').replace("\u201d", '"')
    raw = raw.replace("\u2018", "'").replace("\u2019", "'")
    raw = re.sub(r',(\s*[}\]])', r'\1', raw)

    out, in_string, escaped = [], False, False
    for ch in raw:
        if escaped:
            out.append(ch)
            escaped = False
            continue
        if ch == "\\":
            out.append(ch)
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            out.append(ch)
            continue
        if in_string and ch == "\n":
            out.append("\\n")
            continue
        if in_string and ch == "\r":
            continue
        if in_string and ch == "\t":
            out.append("\\t")
            continue
        out.append(ch)

    return "".join(out)


def _parse_with_repair(raw_text: str) -> dict:
    """
    Parse JSON, falling back to a repair pass if the first attempt fails.
    Raises json.JSONDecodeError only if repair also fails.
    """
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as first_err:
        logger.warning(f"  JSON invalid ({first_err}); attempting repair...")
        parsed = json.loads(_repair_json(raw_text))
        logger.info("  ✅ JSON repaired and parsed successfully")
        return parsed


# ── [FIX 3] Coerce any value to a plain lowercase string ──
def _to_status_string(value) -> str:
    """
    Convert a status value of any shape to a lowercase string.
    Handles: "partial", ["partial"], {"status": "partial"}, enum, None.
    """
    if value is None:
        return "partial"
    if isinstance(value, list):
        value = value[0] if value else "partial"
    if isinstance(value, dict):
        value = value.get("status", "partial")
    if hasattr(value, "value"):
        value = value.value
    elif hasattr(value, "name"):
        value = value.name
    s = str(value).strip()
    if "." in s:
        s = s.split(".")[-1]
    return s.lower()


# ═══════════════════════════════════════════════════════
# COMPLIANCE AGENT NODE
# ═══════════════════════════════════════════════════════

def compliance_agent(state: IEPState) -> IEPState:
    """
    LangGraph node: Compliance Agent

    Runs 4 RAG queries → builds legal context →
    calls Gemini → returns ComplianceReport.
    """
    logger.info("⚖️  Compliance Agent: Starting legal audit...")

    profile  = state.get("student_profile", {})
    insights = state.get("extracted_insights", {})
    errors   = list(state.get("error_log", []))

    if not insights:
        errors.append("Compliance: No extracted insights found.")
        return {
            **state,
            "workflow_status": WorkflowStatus.FAILED,
            "error_log":       errors,
        }

    disability = profile.get("disability_category", "disability")
    age        = int(profile.get("age", 0))

    # [FIX 1] Build baseline BEFORE calling Gemini so it's always available
    baseline_accommodations = _get_baseline_accommodations(disability, age)
    logger.info(
        f"  Baseline accommodations for '{disability}': "
        f"{len(baseline_accommodations)} items"
    )

    raw_text = ""   # kept in scope for error logging

    try:
        # ══════════════════════════════════════════════
        # STEP 1 — Multi-Query RAG Retrieval
        # ══════════════════════════════════════════════

        logger.info(f"  📚 RAG Query 1: disability-specific law for {disability}")
        q1 = retriever.query_for_disability(disability, top_k=3)

        logger.info("  📚 RAG Query 2: mandatory IEP components")
        q2 = retriever.query_mandatory_iep_components()

        logger.info("  📚 RAG Query 3: assessment accommodations")
        q3 = retriever.query_assessment_accommodations(disability)

        q4 = []
        if age >= 14:
            logger.info("  📚 RAG Query 4: transition planning (age 14+)")
            q4 = retriever.query_transition_planning()

        # ── Deduplicate + rank results ────────────────
        seen        = set()
        all_results = []
        for result in q1 + q2 + q3 + q4:
            key = result.text[:50]
            if key not in seen:
                seen.add(key)
                all_results.append(result)

        all_results.sort(key=lambda r: r.relevance_score, reverse=True)
        top_results = all_results[:8]

        logger.info(f"  Retrieved {len(top_results)} unique legal passages")

        # ══════════════════════════════════════════════
        # STEP 2 — Format legal context for Gemini
        # ══════════════════════════════════════════════

        legal_context = retriever.format_for_prompt(top_results)

        # ══════════════════════════════════════════════
        # STEP 3 — Call Gemini for legal analysis
        # ══════════════════════════════════════════════

        logger.info("  🤖 Calling Gemini for compliance analysis...")

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=build_prompt(profile, insights, legal_context)),
        ]
        response = invoke_with_fallback("compliance", messages)
        raw_text = clean_json(response.content)   # [FIX 2] handles list shape

        # ══════════════════════════════════════════════
        # STEP 4 — Parse and validate report
        # ══════════════════════════════════════════════

        # [FIX 4] Parse with repair fallback instead of failing outright
        parsed = _parse_with_repair(raw_text)

        # [FIX 3] Validate status value — may arrive as list/dict/enum
        raw_status = _to_status_string(parsed.get("status", "partial"))
        try:
            status = ComplianceStatus(raw_status)
        except ValueError:
            logger.warning(
                f"  Unrecognised compliance status '{raw_status}' — defaulting to PARTIAL"
            )
            status = ComplianceStatus.PARTIAL

        # [FIX 1] Merge Gemini's list with baseline — drafting agent gets both
        gemini_accommodations = parsed.get("mandatory_accommodations", [])
        final_accommodations  = _merge_accommodations(
            gemini_accommodations, baseline_accommodations
        )

        gemini_count = (
            len(gemini_accommodations)
            if isinstance(gemini_accommodations, list) else 0
        )
        logger.info(
            f"  Accommodations: {gemini_count} from Gemini + "
            f"baseline → {len(final_accommodations)} total"
        )

        # Helper to coerce list fields safely
        def _as_list(value) -> list:
            if isinstance(value, list):
                return [str(v) for v in value]
            if value:
                return [str(value)]
            return []

        # Build compliance report
        compliance_report: ComplianceReport = {
            "status":                   status,
            "rpwd_relevant_sections":   _as_list(parsed.get("rpwd_relevant_sections", [])),
            "ncte_relevant_sections":   _as_list(parsed.get("ncte_relevant_sections", [])),
            "identified_gaps":          _as_list(parsed.get("identified_gaps", [])),
            "mandatory_accommodations": final_accommodations,
            "compliance_notes":         str(parsed.get("compliance_notes", "")),
            "retrieval_sources": [
                {
                    "source":  r.source,
                    "section": getattr(r, "section", r.doc_type),
                    "score":   r.relevance_score,
                }
                for r in top_results
            ],
        }

        logger.info(f"  ✅ Verdict         : {status.value.upper()}")
        logger.info(f"     Gaps found      : {len(compliance_report['identified_gaps'])}")
        logger.info(f"     Mandatory items : {len(compliance_report['mandatory_accommodations'])}")

        # Hard stop on VIOLATION
        next_status = (
            WorkflowStatus.FAILED
            if status == ComplianceStatus.VIOLATION
            else WorkflowStatus.DRAFTING
        )

        if status == ComplianceStatus.VIOLATION:
            errors.append(
                f"COMPLIANCE VIOLATION: {compliance_report['compliance_notes']}"
            )

        return {
            **state,
            "compliance_report": compliance_report,
            "workflow_status":   next_status,
            "current_node":      "compliance_agent",
            "error_log":         errors,
        }

    except json.JSONDecodeError as e:
        # Reached only when repair also failed
        errors.append(f"Compliance: JSON parse error (repair failed): {e}")
        logger.error(f"  ❌ JSON parse error after repair attempt: {e}")
        if raw_text:
            logger.error(f"  Raw output (first 600 chars): {raw_text[:600]}")

        # [FIX 1] Even on parse error, provide baseline so drafting can proceed
        fallback_report: ComplianceReport = {
            "status":                   ComplianceStatus.PARTIAL,
            "rpwd_relevant_sections":   [],
            "ncte_relevant_sections":   [],
            "identified_gaps":          ["Compliance audit failed — manual review required"],
            "mandatory_accommodations": baseline_accommodations,
            "compliance_notes":         f"Compliance audit JSON parse error: {e}",
            "retrieval_sources":        [],
        }
        return {
            **state,
            "compliance_report": fallback_report,
            "workflow_status":   WorkflowStatus.DRAFTING,   # continue anyway
            "current_node":      "compliance_agent",
            "error_log":         errors,
        }

    except Exception as e:
        errors.append(f"Compliance: Unexpected error: {e}")
        logger.error(f"  ❌ Unexpected error: {e}")
        return {
            **state,
            "workflow_status": WorkflowStatus.FAILED,
            "error_log":       errors,
        }