"""
agents/scraper_agent.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 4 — SCRAPER AGENT

Transforms raw teacher notes + student data into
clean structured ExtractedInsights.

Input  : state["student_profile"]   (raw text)
Output : state["extracted_insights"] (structured dict)

FIXES IN THIS VERSION:
  [1] 'list' object has no attribute 'strip' — Gemini 3.x returns
      response.content as a list of content blocks rather than a plain
      string. clean_json_response() coerces any shape to a string.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import json
import logging
import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from agents.state import IEPState, ExtractedInsights, WorkflowStatus
from agents.model_config import invoke_with_fallback

load_dotenv()
logger = logging.getLogger(__name__)

# ── Gemini Client ─────────────────────────────────────
#llm = ChatGoogleGenerativeAI(
    #model="gemini-3.5-flash-lite",
    #temperature=0.2,
    #google_api_key=os.getenv("GOOGLE_API_KEY"),
#)

# ── System Prompt ─────────────────────────────────────
SYSTEM_PROMPT = """You are a specialist educational psychologist AI 
working within India's inclusive education system under the RPwD Act 2016.

Your role is to analyze raw student data and extract structured, 
clinically-informed insights to support IEP development.

Rules:
1. Extract CONCRETE, SPECIFIC strengths — never vague terms
2. Identify PRECISE challenges linked to the disability type
3. Set SMART goals (Specific, Measurable, Achievable, Relevant, Time-bound)
4. All goals must follow format: "By [time], student will [action] as measured by [method]"
5. Return ONLY valid JSON — no markdown, no explanation, no preamble"""


def build_prompt(profile: dict) -> str:
    return f"""Analyze this student profile and extract structured IEP insights.

STUDENT PROFILE:
━━━━━━━━━━━━━━━
Name             : {profile.get('student_name', 'N/A')}
Age              : {profile.get('age', 'N/A')} years
Grade            : {profile.get('grade', 'N/A')}
School           : {profile.get('school_name', 'N/A')}
Disability       : {profile.get('disability_category', 'N/A')}
Severity         : {profile.get('disability_severity', 'N/A')}

RAW TEACHER NOTES:
{profile.get('raw_notes', 'Not provided')}

ACADEMIC HISTORY:
{profile.get('academic_history', 'Not provided')}

TEACHER OBSERVATIONS:
{profile.get('teacher_observations', 'Not provided')}

PARENT CONCERNS:
{profile.get('parent_concerns', 'Not provided')}

Return EXACTLY this JSON structure:
{{
  "strengths": [
    "Specific strength 1",
    "Specific strength 2",
    "Specific strength 3"
  ],
  "challenges": [
    "Specific challenge 1",
    "Specific challenge 2",
    "Specific challenge 3"
  ],
  "learning_style": "Primary learning style with brief rationale",
  "recommended_supports": [
    "Support 1",
    "Support 2",
    "Support 3"
  ],
  "short_term_goals": [
    "By end of Term 1, student will [action] as measured by [method]",
    "By end of Term 2, student will [action] as measured by [method]"
  ],
  "long_term_goals": [
    "By end of academic year, student will [action] as measured by [method]"
  ],
  "academic_performance": {{
    "overall_level": "below_grade",
    "strong_subjects": ["subject1"],
    "weak_subjects": ["subject1"],
    "grade_trajectory": "improving"
  }},
  "behavioural_notes": [
    "Observation 1",
    "Observation 2"
  ],
  "assistive_tech_needs": [
    "Technology 1"
  ]
}}"""


# ── [FIX 1] Gemini 3.x returns content as a list of blocks ──
def clean_json_response(raw) -> str:
    """
    Strip markdown fences if Gemini adds them.

    FIX: Gemini 3.x returns response.content as a list of content blocks
    rather than a plain string. Coerce any shape to a string first.
    """
    # Handle list-of-blocks response format (Gemini 3.x)
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


# ═══════════════════════════════════════════════════════
# SCRAPER AGENT NODE
# ═══════════════════════════════════════════════════════

def scraper_agent(state: IEPState) -> IEPState:
    """
    LangGraph node: Scraper Agent

    Reads student_profile from state →
    calls Gemini → parses JSON →
    writes extracted_insights back to state.
    """
    logger.info("🔍 Scraper Agent: Starting extraction...")

    profile = state.get("student_profile", {})
    errors  = list(state.get("error_log", []))

    # ── Validate minimum required input ───────────────
    required = ["student_name", "disability_category", "raw_notes"]
    missing  = [f for f in required if not profile.get(f)]

    if missing:
        errors.append(f"Scraper: Missing required fields: {missing}")
        logger.error(f"  ❌ Missing fields: {missing}")
        return {
            **state,
            "workflow_status": WorkflowStatus.FAILED,
            "error_log":       errors,
        }

    try:
        # ── Call Gemini ───────────────────────────────
        logger.info(f"  Calling Gemini for: {profile.get('student_name')}")
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=build_prompt(profile)),
        ]
        response = invoke_with_fallback("scraper", messages)
        raw_text = clean_json_response(response.content)   # [FIX 1]

        # ── Parse JSON ────────────────────────────────
        parsed: ExtractedInsights = json.loads(raw_text)

        # ── Validate required fields extracted ────────
        required_keys = [
            "strengths", "challenges",
            "short_term_goals", "long_term_goals",
            "recommended_supports",
        ]
        missing_keys = [k for k in required_keys if not parsed.get(k)]

        if missing_keys:
            errors.append(f"Scraper: LLM missing fields: {missing_keys}")
            logger.error(f"  ❌ Missing keys in response: {missing_keys}")
            return {
                **state,
                "workflow_status": WorkflowStatus.FAILED,
                "error_log":       errors,
            }

        # ── Coerce list fields to lists of strings ────
        for key in required_keys:
            val = parsed.get(key)
            if isinstance(val, str):
                parsed[key] = [val]
            elif isinstance(val, list):
                parsed[key] = [str(v) for v in val]

        logger.info(
            f"  ✅ Extracted: "
            f"{len(parsed.get('strengths', []))} strengths | "
            f"{len(parsed.get('challenges', []))} challenges | "
            f"{len(parsed.get('short_term_goals', []))} goals"
        )

        return {
            **state,
            "extracted_insights": parsed,
            "workflow_status":    WorkflowStatus.COMPLIANCE,
            "current_node":       "scraper_agent",
            "error_log":          errors,
        }

    except json.JSONDecodeError as e:
        errors.append(f"Scraper: JSON parse error: {e}")
        logger.error(f"  ❌ JSON parse error: {e}")
        return {
            **state,
            "workflow_status": WorkflowStatus.FAILED,
            "error_log":       errors,
        }

    except Exception as e:
        errors.append(f"Scraper: Unexpected error: {e}")
        logger.error(f"  ❌ Unexpected error: {e}")
        return {
            **state,
            "workflow_status": WorkflowStatus.FAILED,
            "error_log":       errors,
        }