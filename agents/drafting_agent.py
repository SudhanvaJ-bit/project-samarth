"""
agents/drafting_agent.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 6 — DRAFTING AGENT

FIXES IN THIS VERSION:
  [1] 'list' object has no attribute 'lower' — annual_goals coerced
      to string before .lower() check
  [2] ComplianceStatus enum crash — _status_str() normalises any enum
      or raw string before injecting into f-string prompt
  [3] Unevaluated ternary expressions — long_term_outcomes and
      participating_agencies pre-computed as variables before f-string
  [4] STO enforcement — system prompt explicitly forbids placeholder text
  [5] mandatory_accommodations injected into prompt (Bug 3 fix)
  [6] Gemini 3.x list response — response.content is now returned as a
      list of content blocks rather than a plain string. clean_json()
      coerces any shape to a string before calling .strip().
  [7] NEW — JSON repair fallback. Gemini intermittently emits a trailing
      comma before a closing brace, which crashed the whole pipeline and
      wasted 3 API calls per failure. _repair_json() fixes trailing
      commas, smart quotes, and unescaped newlines inside string values
      before giving up.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import json
import logging
import os
import re
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from agents.state import IEPState, DraftedIEP, WorkflowStatus

load_dotenv()
logger = logging.getLogger(__name__)

# ── Gemini Client ─────────────────────────────────────
llm = ChatGoogleGenerativeAI(
    model="gemini-3.7-flash",
    temperature=0.4,
    google_api_key=os.getenv("GOOGLE_API_KEY"),
)

# ── System Prompt ─────────────────────────────────────
SYSTEM_PROMPT = """You are a Senior Special Education Coordinator in India
with 15 years of experience writing Individualized Education Programs (IEPs).

You write with:
- Clarity: Simple, jargon-free language parents can understand
- Empathy: Strength-based, never deficit-focused
- Precision: Specific, measurable, actionable goals
- Legal accuracy: Every mandatory accommodation included

Rules:
1. MUST incorporate ALL mandatory accommodations from compliance report
2. Goals must follow SMART format
3. Each section must be 2-4 well-written paragraphs or structured lists
4. Never use placeholders — write real, complete content
5. Return ONLY valid JSON — no markdown, no preamble

CRITICAL JSON RULES:
- Return a single JSON object. No trailing comma after the final field.
- No trailing comma before any closing brace or bracket.
- Use straight double quotes only. Never use smart/curly quotes.
- The value of every JSON field must be a STRING, not a list or object.
- Never start any field with "Section N:" or "Section N -" — the PDF
  generator adds section headers automatically.

SHORT-TERM OBJECTIVES (STOs) — MANDATORY REQUIREMENT:
- Every annual goal MUST include exactly 3 short-term objectives, one per term.
- NEVER write "Short-term objectives to be developed by the IEP team." — this is FORBIDDEN.
- NEVER leave objectives as a placeholder or note for later.
- Write all 3 objectives NOW with specific measurable criteria.
- Use this exact structure for EVERY goal:

  Annual Goal: [goal statement]
  Short-term Objectives:
  1. By the end of Term 1, [student name] will [specific measurable action with numeric criterion]
     as measured by [specific assessment method].
  2. By the end of Term 2, [student name] will [specific measurable action with numeric criterion]
     as measured by [specific assessment method].
  3. By the end of Term 3, [student name] will [specific measurable action with numeric criterion]
     as measured by [specific assessment method].
  Evaluation Procedures: [comma-separated list of methods]
  Evaluation Schedule: Quarterly

- Each objective must have a NUMERIC criterion (e.g. "80% accuracy", "4 out of 5 trials",
  "70 words per minute", "3 out of 4 attempts").
- Do NOT embed evaluation info inside objective text using | separators.
- Term 1 objective should be foundational; Term 2 builds on it; Term 3 approaches annual goal."""


# ── [FIX 2] Safe enum → string converter ─────────────
def _status_str(value) -> str:
    """Safely convert a ComplianceStatus enum (or any value) to a plain string."""
    if value is None:
        return "partial"
    if isinstance(value, list):
        value = value[0] if value else "partial"
    if hasattr(value, "value"):
        return str(value.value)
    if hasattr(value, "name"):
        return str(value.name).lower()
    s = str(value)
    return s.split(".")[-1].lower().replace("_", " ")


def build_prompt(profile: dict, insights: dict, compliance: dict) -> str:
    age              = int(profile.get("age", 0))
    needs_transition = age >= 14
    dob_estimate     = f"approximately {2026 - age}"

    # [FIX 3] Pre-compute transition-dependent strings BEFORE the f-string
    long_term_outcomes_instruction = (
        "Post-secondary education/training plans, employment goals, community living goals. "
        "Transition service needs. Include guidance/career counseling, course requirements. "
        "Do not start this field with a section heading."
        if needs_transition else
        "N/A — Student is below 14 years. Long-term adult outcomes and transition planning "
        "will be developed at age 14 per RPwD Act 2016 Section 17 and NCTE Guidelines. "
        "Do not start this field with a section heading."
    )
    participating_agencies_instruction = (
        "Government agencies, NGOs, rehabilitation centres supporting transition services. "
        "Include DDRC, district resource centres, vocational training institutes. "
        "Do not start this field with a section heading."
        if needs_transition else
        "N/A — Transition services not yet applicable. Will be identified at age 14. "
        "Do not start this field with a section heading."
    )

    # [FIX 5] Format mandatory accommodations as explicit checklist
    mandatory_items = compliance.get("mandatory_accommodations", [])
    if not isinstance(mandatory_items, list):
        mandatory_items = [mandatory_items] if mandatory_items else []

    if mandatory_items:
        accommodations_block = "\n".join(
            f"  \u2713 {item}" for item in mandatory_items
        )
        accommodations_instruction = (
            f"MANDATORY ACCOMMODATIONS — YOU MUST INCLUDE ALL OF THESE:\n"
            f"{accommodations_block}\n\n"
            f"Every item above must appear explicitly in 'special_education_services'.\n"
            f"Do not omit any. The compliance agent has verified these are legally required."
        )
    else:
        accommodations_instruction = (
            "No specific mandatory accommodations flagged — use standard IEP services "
            "appropriate for the disability category and RPwD Act 2016."
        )

    # [FIX 2] Normalise compliance status before injecting into prompt
    compliance_status_str = _status_str(compliance.get("status", "partial"))

    return f"""Draft a complete IEP in the standard NASET format for Indian schools.

\u2501\u2501\u2501 STUDENT \u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501
Name        : {profile.get('student_name')}
Age / Grade : {profile.get('age')} years / {profile.get('grade', 'N/A')}
School      : {profile.get('school_name', 'N/A')}
Disability  : {profile.get('disability_category')} ({profile.get('disability_severity', 'N/A')})
DOB (approx): {dob_estimate}

\u2501\u2501\u2501 INSIGHTS \u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501
Strengths           : {json.dumps(insights.get('strengths', []))}
Challenges          : {json.dumps(insights.get('challenges', []))}
Learning Style      : {insights.get('learning_style', 'N/A')}
Academic Performance: {json.dumps(insights.get('academic_performance', {}))}
Behavioural Notes   : {json.dumps(insights.get('behavioural_notes', []))}
Assistive Tech Needs: {json.dumps(insights.get('assistive_tech_needs', []))}
Recommended Supports: {json.dumps(insights.get('recommended_supports', []))}

\u2501\u2501\u2501 LEGAL REQUIREMENTS \u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501
{accommodations_instruction}
Compliance Status: {compliance_status_str}
Compliance Notes : {compliance.get('compliance_notes', '')}

\u2501\u2501\u2501 GOALS \u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501
Short-term Goals: {json.dumps(insights.get('short_term_goals', []))}
Long-term Goals : {json.dumps(insights.get('long_term_goals', []))}

Return EXACTLY this JSON. Every value MUST be a plain string, not a list or object.
Do NOT put a comma after the last field.
{{
  "background_info": "Student name, school, grade, date of IEP meeting, disability classification per RPwD Act 2016, student ID format, dominant language, date of initiation of services. Parent/guardian names and contact. Medical alerts if any.",

  "academic_performance": "Current academic achievement levels across all subjects. State present levels for: Academic/Educational Achievement, Cognitive Ability, Language Ability, Learning Style, Rate of Progress. Use format: Present Level: [area] - [student name] is currently functioning [above/at/below] grade level in [area]. Include specific abilities and needs. Do not start this field with a section heading.",

  "social_development": "Quality of relationships with peers and adults, feelings about self, social adjustment, behaviors that may impede learning. Present levels of social interaction, self-concept, school/community adjustment. State specific abilities and needs. Do not start this field with a section heading.",

  "physical_development": "Motor and sensory development, health, vitality, physical skills or limitations. Reference the disability diagnosis. State abilities and needs related to physical participation in school. Do not start this field with a section heading.",

  "management_needs": "Nature and degree of environmental modifications and human/material resources required. State management needs level (minimal/moderate/significant) for academic, social, and physical goals. Describe abilities and support needed. Do not start this field with a section heading.",

  "long_term_outcomes": "{long_term_outcomes_instruction}",

  "annual_goals": "Write 3-4 measurable annual goals. REMINDER: Every goal MUST have 3 fully written Short-term Objectives, one per term. NEVER write a placeholder like 'to be developed by the IEP team'. Write all objectives now with numeric criteria. Use the exact format from the system prompt. Do not start this field with a section heading.",

  "special_education_services": "A. Special education programs with initiation date, frequency, duration. B. Extended school year services (Yes/No). C. Supplementary aids and modifications with initiation dates. D. Assistive technology devices/services needed (reference RPwD Act Section 17 for mandatory items). E. Program modifications for school personnel. F. Individual testing modifications including extended time (minimum 25% per RPwD Act). IMPORTANT: All mandatory accommodations listed above must appear somewhere in this section. Do not start this field with a section heading.",

  "general_education_participation": "Extent of participation in general education classes, non-academic and extracurricular activities including physical education. Explain any exemptions (e.g. second language). Describe support personnel required for inclusion. Do not start this field with a section heading.",

  "participating_agencies": "{participating_agencies_instruction}",

  "coordinated_activities": "Coordinated set of activities for long-term outcomes. Address: 1. Instruction, 2. Related Services, 3. Employment/Post-secondary Education, 4. Community Experience, 5. Activities of Daily Living, 6. Functional Vocational Assessment. Mark N/A for items not applicable at this age. Do not start this field with a section heading.",

  "graduation_info": "Type of certificate/credential sought (e.g. CBSE/ICSE/State Board Certificate). Expected year of school completion. Any special provisions for board examinations under RPwD Act accommodations. Do not start this field with a section heading.",

  "recommendations_summary": "Classification of disability per RPwD Act 2016 Schedule. Recommended placement (Inclusive/Resource Room/Special Class). Extended school year services. Transportation needs. Any additional recommendations from the IEP committee. Do not start this field with a section heading.",

  "progress_reporting": "Manner and frequency of progress reporting to parents. Must include: frequency of reports (same as non-disabled peers), methods (report cards, teacher contact, progress reports), criteria for measuring progress toward annual goals, parent meeting schedule. Do not start this field with a section heading."
}}"""


# ── [FIX 6] Gemini 3.x returns content as a list of blocks ──
def clean_json(raw) -> str:
    """
    Strip markdown fences if Gemini adds them.

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


# ── [FIX 7] JSON repair fallback ──────────────────────
def _repair_json(raw: str) -> str:
    """
    Fix common LLM JSON breakages before giving up on the response.

    Handles, in order:
      1. Smart/curly quotes  →  straight quotes
      2. Trailing commas before } or ]  (the observed failure mode)
      3. Literal newlines/tabs inside string values  →  escaped

    The newline pass walks the string tracking whether it is inside a
    JSON string literal, so it only escapes characters that are actually
    illegal there — structural whitespace between fields is left alone.
    """
    # 1. Normalise smart quotes
    raw = raw.replace("\u201c", '"').replace("\u201d", '"')
    raw = raw.replace("\u2018", "'").replace("\u2019", "'")

    # 2. Remove trailing commas before a closing brace or bracket
    raw = re.sub(r',(\s*[}\]])', r'\1', raw)

    # 3. Escape literal newlines/tabs that appear INSIDE string values
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
        repaired = _repair_json(raw_text)
        parsed = json.loads(repaired)   # raises if still broken
        logger.info("  ✅ JSON repaired and parsed successfully")
        return parsed


# ═══════════════════════════════════════════════════════
# DRAFTING AGENT NODE
# ═══════════════════════════════════════════════════════

def drafting_agent(state: IEPState) -> IEPState:
    """
    LangGraph node: Drafting Agent

    Takes insights + compliance report →
    calls Gemini → writes 14 IEP sections →
    returns DraftedIEP in state.
    """
    logger.info("✍️  Drafting Agent: Composing IEP sections...")

    profile    = state.get("student_profile", {})
    insights   = state.get("extracted_insights", {})
    compliance = state.get("compliance_report", {})
    errors     = list(state.get("error_log", []))

    if not insights:
        errors.append("Drafting: No extracted insights found.")
        return {**state, "workflow_status": WorkflowStatus.FAILED,
                "error_log": errors}

    if not compliance:
        errors.append("Drafting: No compliance report found.")
        return {**state, "workflow_status": WorkflowStatus.FAILED,
                "error_log": errors}

    try:
        logger.info(f"  Drafting IEP for: {profile.get('student_name')}")

        mandatory = compliance.get("mandatory_accommodations", [])
        mandatory_count = len(mandatory) if isinstance(mandatory, list) else 0
        logger.info(f"  Injecting {mandatory_count} mandatory accommodations into prompt")

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=build_prompt(profile, insights, compliance)),
        ]
        response = llm.invoke(messages)
        raw_text = clean_json(response.content)   # [FIX 6] handles list shape

        # [FIX 7] Parse with repair fallback instead of failing outright
        parsed: DraftedIEP = _parse_with_repair(raw_text)

        # ── Validate all sections present ─────────────
        required_sections = [
            "background_info",
            "academic_performance",
            "social_development",
            "physical_development",
            "management_needs",
            "long_term_outcomes",
            "annual_goals",
            "special_education_services",
            "general_education_participation",
            "participating_agencies",
            "coordinated_activities",
            "graduation_info",
            "recommendations_summary",
            "progress_reporting",
        ]

        missing = [s for s in required_sections if not parsed.get(s)]
        if missing:
            errors.append(f"Drafting: Missing IEP sections: {missing}")
            logger.error(f"  ❌ Missing sections: {missing}")
            return {
                **state,
                "workflow_status": WorkflowStatus.FAILED,
                "error_log":       errors,
            }

        # ── [FIX 1] Coerce ALL section fields to strings ──────────────
        for key in required_sections:
            val = parsed.get(key)
            if isinstance(val, list):
                parsed[key] = "\n".join(str(x) for x in val)
            elif isinstance(val, dict):
                parsed[key] = "\n".join(f"{k}: {v}" for k, v in val.items())
            elif not isinstance(val, str):
                parsed[key] = str(val)

        # ── STO placeholder check (now safe — always a string) ────────
        annual_goals_text = parsed.get("annual_goals", "")
        if "to be developed by the iep team" in annual_goals_text.lower():
            logger.warning("⚠️  Drafting Agent: STO placeholder text detected.")
            errors.append(
                "Drafting warning: STO placeholder detected in annual_goals. "
                "STOs may be incomplete."
            )

        logger.info(f"  ✅ All {len(required_sections)} IEP sections drafted")

        return {
            **state,
            "drafted_iep":     parsed,
            "workflow_status": WorkflowStatus.REVIEWING,
            "current_node":    "drafting_agent",
            "error_log":       errors,
        }

    except json.JSONDecodeError as e:
        # Reached only when repair also failed — log a snippet to aid debugging
        errors.append(f"Drafting: JSON parse error (repair failed): {e}")
        logger.error(f"  ❌ JSON parse error after repair attempt: {e}")
        try:
            logger.error(f"  Raw output (first 600 chars): {raw_text[:600]}")
        except Exception:
            pass
        return {**state, "workflow_status": WorkflowStatus.FAILED,
                "error_log": errors}

    except Exception as e:
        errors.append(f"Drafting: Unexpected error: {e}")
        logger.error(f"  ❌ Unexpected error: {e}")
        return {**state, "workflow_status": WorkflowStatus.FAILED,
                "error_log": errors}