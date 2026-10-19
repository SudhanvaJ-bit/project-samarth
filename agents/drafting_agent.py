"""
agents/drafting_agent.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 6 — DRAFTING AGENT

FIXES IN THIS VERSION:
  [1] annual_goals coerced to string before .lower()
  [2] ComplianceStatus enum normalised before prompt injection
  [3] Transition-dependent strings pre-computed before the f-string
  [4] STO enforcement — placeholder text forbidden
  [5] mandatory_accommodations injected as a checklist
  [6] Gemini 3.x list-of-blocks response handled in clean_json()
  [7] JSON repair fallback (trailing commas, smart quotes, newlines)
  [8] Calls go through invoke_with_fallback() — model chain + replay
  [9] NEW — REAL DATES. The model was inventing service dates in the
      past ("April 16, 2025 – March 31, 2026" on a September 2026 IEP)
      because nothing told it what today is. The prompt now supplies the
      meeting date, a service start date inside the 15-day window, the
      Indian academic year end (31 March), and the annual review date.
 [10] NEW — SECTION 5 LAYOUT. Subsections A–F must each start on a new
      line, so the PDF renders them as separate paragraphs instead of one
      block of text.
 [11] NEW — INTERNAL CONSISTENCY. A draft said "no second language
      exemption" in Section 6 and "second language waiver" in Section 9.
      The prompt now requires exemptions to be stated identically wherever
      they appear.
 [12] NEW — CITATION DISCIPLINE. Legal citations must come from the
      provisions the compliance agent retrieved, not from the model's
      memory. Section numbers it cannot ground are to be omitted rather
      than guessed.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import json
import logging
import re
from datetime import date, timedelta

from dotenv import load_dotenv
from langchain_core.messages import SystemMessage, HumanMessage

from agents.state import IEPState, DraftedIEP, WorkflowStatus
from agents.model_config import current_date, invoke_with_fallback

load_dotenv()
logger = logging.getLogger(__name__)


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
- Use \\n inside a string value to start a new line.

DATES:
- Use ONLY the dates supplied in the SCHEDULE block of the request.
- Never invent a date, and never write a date earlier than the IEP meeting.

LEGAL CITATIONS:
- Cite a statute section ONLY if it appears in the RETRIEVED LEGAL PROVISIONS
  supplied in the request.
- If you are not certain of a section number, describe the entitlement in words
  and omit the number. A missing citation is acceptable; a wrong one is not.

INTERNAL CONSISTENCY:
- Any exemption, waiver or placement decision must be stated the SAME way in
  every section that mentions it. If a second-language exemption is granted,
  Sections 6, 9 and 10 must all say so. If it is not, none of them may.

ANNUAL GOALS:
- Each annual goal must target ONE skill area (e.g. reading OR mathematics OR
  writing OR self-regulation). Never combine two skill areas in one goal.

SHORT-TERM OBJECTIVES (STOs) — MANDATORY REQUIREMENT:
- Every annual goal MUST include exactly 3 short-term objectives, one per term.
- NEVER write "Short-term objectives to be developed by the IEP team." — this is FORBIDDEN.
- NEVER leave objectives as a placeholder or note for later.
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

- Each objective must have a NUMERIC criterion (e.g. "80% accuracy", "4 out of 5 trials").
- Do NOT embed evaluation info inside objective text using | separators.
- Term 1 is foundational; Term 2 builds on it; Term 3 approaches the annual goal."""


# ── [9] Real dates ────────────────────────────────────

def _fmt(d: date) -> str:
    """'21 September 2026' — cross-platform (no %-d)."""
    return f"{d.day} {d.strftime('%B')} {d.year}"


def _schedule(today: date = None) -> dict:
    """
    Dates the model must use instead of inventing its own.

    - Service start: within the 15-day preparation window.
    - Academic year end: 31 March (Indian school calendar). If the meeting is
      between April and December, the year ends next March; if January to
      March, it ends this March.
    - Annual review: one year after the meeting.
    """
    today = today or current_date()   # frozen in demo mode — see model_config
    start = today + timedelta(days=14)
    ay_end_year = today.year + 1 if today.month >= 4 else today.year
    try:
        review = today.replace(year=today.year + 1)
    except ValueError:                      # 29 February
        review = today + timedelta(days=365)
    return {
        "meeting":   _fmt(today),
        "start":     _fmt(start),
        "ay_end":    _fmt(date(ay_end_year, 3, 31)),
        "review":    _fmt(review),
    }


# ── Helpers ───────────────────────────────────────────

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
    return str(value).split(".")[-1].lower().replace("_", " ")


def _as_lines(items) -> str:
    if not isinstance(items, list):
        items = [items] if items else []
    return "\n".join(f"  - {i}" for i in items if str(i).strip()) or "  (none retrieved)"


def build_prompt(profile: dict, insights: dict, compliance: dict) -> str:
    age              = int(profile.get("age", 0))
    needs_transition = age >= 14
    sched            = _schedule()

    long_term_outcomes_instruction = (
        "Post-secondary education/training plans, employment goals, community living goals. "
        "Transition service needs. Include guidance/career counseling, course requirements. "
        "Do not start this field with a section heading."
        if needs_transition else
        "N/A — Student is below 14 years. Long-term adult outcomes and transition planning "
        "will be developed at age 14 per RPwD Act 2016 and NCTE Guidelines. "
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

    mandatory_items = compliance.get("mandatory_accommodations", [])
    if not isinstance(mandatory_items, list):
        mandatory_items = [mandatory_items] if mandatory_items else []

    if mandatory_items:
        accommodations_instruction = (
            "MANDATORY ACCOMMODATIONS — YOU MUST INCLUDE ALL OF THESE:\n"
            + "\n".join(f"  \u2713 {item}" for item in mandatory_items)
            + "\n\nEvery item above must appear explicitly in 'special_education_services'.\n"
              "Do not omit any. The compliance agent has verified these are legally required."
        )
    else:
        accommodations_instruction = (
            "No specific mandatory accommodations flagged — use standard IEP services "
            "appropriate for the disability category and RPwD Act 2016."
        )

    compliance_status_str = _status_str(compliance.get("status", "partial"))

    # [12] Only these provisions may be cited
    retrieved_provisions = (
        "RPwD Act:\n"  + _as_lines(compliance.get("rpwd_relevant_sections", [])) +
        "\nNCTE/NCERT:\n" + _as_lines(compliance.get("ncte_relevant_sections", []))
    )

    return f"""Draft a complete IEP in the standard NASET format for Indian schools.

=== STUDENT ===
Name        : {profile.get('student_name')}
Age / Grade : {profile.get('age')} years / {profile.get('grade', 'N/A')}
School      : {profile.get('school_name', 'N/A')}
Disability  : {profile.get('disability_category')} ({profile.get('disability_severity', 'N/A')})

=== SCHEDULE — use these dates exactly, never invent others ===
IEP meeting date          : {sched['meeting']}
Services begin            : {sched['start']}
Services continue through : {sched['ay_end']} (end of the academic year)
Annual IEP review         : {sched['review']}

=== INSIGHTS ===
Strengths           : {json.dumps(insights.get('strengths', []))}
Challenges          : {json.dumps(insights.get('challenges', []))}
Learning Style      : {insights.get('learning_style', 'N/A')}
Academic Performance: {json.dumps(insights.get('academic_performance', {}))}
Behavioural Notes   : {json.dumps(insights.get('behavioural_notes', []))}
Assistive Tech Needs: {json.dumps(insights.get('assistive_tech_needs', []))}
Recommended Supports: {json.dumps(insights.get('recommended_supports', []))}

=== LEGAL REQUIREMENTS ===
{accommodations_instruction}
Compliance Status: {compliance_status_str}
Compliance Notes : {compliance.get('compliance_notes', '')}

=== RETRIEVED LEGAL PROVISIONS — the ONLY sections you may cite ===
{retrieved_provisions}

=== GOALS ===
Short-term Goals: {json.dumps(insights.get('short_term_goals', []))}
Long-term Goals : {json.dumps(insights.get('long_term_goals', []))}

Return EXACTLY this JSON. Every value MUST be a plain string, not a list or object.
Do NOT put a comma after the last field.
{{
  "background_info": "Student name, school, grade, date of IEP meeting ({sched['meeting']}), disability classification per RPwD Act 2016, dominant language, date services begin ({sched['start']}). Parent/guardian names and contact if known. Medical alerts if any. Put each item on its own line using \\\\n.",

  "academic_performance": "Present levels for: Academic/Educational Achievement, Cognitive Ability, Language Ability, Learning Style, Rate of Progress. Use format: Present Level: [area] - [student name] is currently functioning [above/at/below] grade level in [area]. Start each 'Present Level:' on a new line using \\\\n. Do not start this field with a section heading.",

  "social_development": "Relationships with peers and adults, self-concept, social adjustment, behaviours that may impede learning. Start each 'Present Level:' on a new line. Do not start this field with a section heading.",

  "physical_development": "Motor and sensory development, health, vitality, physical skills or limitations. Reference the disability diagnosis. Do not start this field with a section heading.",

  "management_needs": "Nature and degree of environmental modifications and human/material resources required. State the management needs level (minimal/moderate/significant). Do not start this field with a section heading.",

  "long_term_outcomes": "{long_term_outcomes_instruction}",

  "annual_goals": "Write 3-4 measurable annual goals, each targeting ONE skill area. Every goal MUST have 3 fully written Short-term Objectives, one per term, with numeric criteria. Use the exact format from the system prompt. Do not start this field with a section heading.",

  "special_education_services": "Write six subsections, EACH STARTING ON A NEW LINE (separate them with \\\\n\\\\n): A. Special education programs with frequency and duration, beginning {sched['start']} and continuing through {sched['ay_end']}. B. Extended school year services (Yes/No). C. Supplementary aids and modifications. D. Assistive technology devices/services. E. Program modifications for school personnel. F. Individual testing modifications including extended time (minimum 25%). All mandatory accommodations listed above must appear. Do not start this field with a section heading.",

  "general_education_participation": "Extent of participation in general education classes, non-academic and extracurricular activities including physical education. State clearly whether any exemption (e.g. second language) is granted — this decision must match Sections 9 and 10 exactly. Do not start this field with a section heading.",

  "participating_agencies": "{participating_agencies_instruction}",

  "coordinated_activities": "Address each on its own line: 1. Instruction, 2. Related Services, 3. Employment/Post-secondary Education, 4. Community Experience, 5. Activities of Daily Living, 6. Functional Vocational Assessment. Mark N/A for items not applicable at this age. Do not start this field with a section heading.",

  "graduation_info": "Certificate sought (CBSE / ICSE / State Board Certificate). Expected year of school completion. Board examination provisions under RPwD Act accommodations — any language exemption must match Section 6 exactly. Do not start this field with a section heading.",

  "recommendations_summary": "Disability classification per RPwD Act 2016 Schedule (cite a section only if it appears in the retrieved provisions). Recommended placement. Extended school year services. Transportation needs. Annual review on {sched['review']}. Do not start this field with a section heading.",

  "progress_reporting": "Manner and frequency of progress reporting to parents: frequency (same as non-disabled peers), methods, criteria for measuring progress, parent meeting schedule. Do not start this field with a section heading."
}}"""


# ── JSON cleaning / repair ────────────────────────────

def clean_json(raw) -> str:
    """Strip markdown fences; coerce list-of-blocks responses to a string."""
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
        raw = "\n".join(l for l in raw.split("\n") if not l.strip().startswith("```"))
    return raw.strip()


def _repair_json(raw: str) -> str:
    """Smart quotes → straight; strip trailing commas; escape newlines inside strings."""
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


def _parse_with_repair(raw_text: str) -> dict:
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as first_err:
        logger.warning(f"  JSON invalid ({first_err}); attempting repair...")
        parsed = json.loads(_repair_json(raw_text))
        logger.info("  ✅ JSON repaired and parsed successfully")
        return parsed


# ═══════════════════════════════════════════════════════
# DRAFTING AGENT NODE
# ═══════════════════════════════════════════════════════

REQUIRED_SECTIONS = [
    "background_info", "academic_performance", "social_development",
    "physical_development", "management_needs", "long_term_outcomes",
    "annual_goals", "special_education_services",
    "general_education_participation", "participating_agencies",
    "coordinated_activities", "graduation_info",
    "recommendations_summary", "progress_reporting",
]


def drafting_agent(state: IEPState) -> IEPState:
    """LangGraph node: insights + compliance report → 14 NASET sections."""
    logger.info("✍️  Drafting Agent: Composing IEP sections...")

    profile    = state.get("student_profile", {})
    insights   = state.get("extracted_insights", {})
    compliance = state.get("compliance_report", {})
    errors     = list(state.get("error_log", []))

    if not insights:
        errors.append("Drafting: No extracted insights found.")
        return {**state, "workflow_status": WorkflowStatus.FAILED, "error_log": errors}
    if not compliance:
        errors.append("Drafting: No compliance report found.")
        return {**state, "workflow_status": WorkflowStatus.FAILED, "error_log": errors}

    raw_text = ""
    try:
        logger.info(f"  Drafting IEP for: {profile.get('student_name')}")
        mandatory = compliance.get("mandatory_accommodations", [])
        logger.info(
            f"  Injecting {len(mandatory) if isinstance(mandatory, list) else 0} "
            f"mandatory accommodations into prompt"
        )

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=build_prompt(profile, insights, compliance)),
        ]
        response = invoke_with_fallback("drafting", messages)
        raw_text = clean_json(response.content)
        parsed: DraftedIEP = _parse_with_repair(raw_text)

        missing = [s for s in REQUIRED_SECTIONS if not parsed.get(s)]
        if missing:
            errors.append(f"Drafting: Missing IEP sections: {missing}")
            logger.error(f"  ❌ Missing sections: {missing}")
            return {**state, "workflow_status": WorkflowStatus.FAILED, "error_log": errors}

        # Coerce every section to a string before any string operation
        for key in REQUIRED_SECTIONS:
            val = parsed.get(key)
            if isinstance(val, list):
                parsed[key] = "\n".join(str(x) for x in val)
            elif isinstance(val, dict):
                parsed[key] = "\n".join(f"{k}: {v}" for k, v in val.items())
            elif not isinstance(val, str):
                parsed[key] = str(val)

        if "to be developed by the iep team" in parsed.get("annual_goals", "").lower():
            logger.warning("⚠️  Drafting Agent: STO placeholder text detected.")
            errors.append("Drafting warning: STO placeholder detected in annual_goals.")

        logger.info(f"  ✅ All {len(REQUIRED_SECTIONS)} IEP sections drafted")
        return {
            **state,
            "drafted_iep":     parsed,
            "workflow_status": WorkflowStatus.REVIEWING,
            "current_node":    "drafting_agent",
            "error_log":       errors,
        }

    except json.JSONDecodeError as e:
        errors.append(f"Drafting: JSON parse error (repair failed): {e}")
        logger.error(f"  ❌ JSON parse error after repair attempt: {e}")
        if raw_text:
            logger.error(f"  Raw output (first 600 chars): {raw_text[:600]}")
        return {**state, "workflow_status": WorkflowStatus.FAILED, "error_log": errors}

    except Exception as e:
        errors.append(f"Drafting: Unexpected error: {e}")
        logger.error(f"  ❌ Unexpected error: {e}")
        return {**state, "workflow_status": WorkflowStatus.FAILED, "error_log": errors}