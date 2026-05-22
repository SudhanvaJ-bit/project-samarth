"""
agents/drafting_agent.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 6 — DRAFTING AGENT

Synthesizes all prior outputs into a structured,
professional IEP document — section by section.

Input  : state["extracted_insights"]
         state["compliance_report"]
         state["student_profile"]
Output : state["drafted_iep"]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import json
import logging
import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from agents.state import IEPState, DraftedIEP, WorkflowStatus

load_dotenv()
logger = logging.getLogger(__name__)

# ── Gemini Client ─────────────────────────────────────
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0.4,    # Slightly higher for professional writing
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
5. Return ONLY valid JSON — no markdown, no preamble"""


def build_prompt(profile: dict, insights: dict, compliance: dict) -> str:
    age              = int(profile.get("age", 0))
    needs_transition = age >= 14

    return f"""Draft a complete, professional IEP.
You MUST incorporate ALL mandatory accommodations from the compliance report.

━━━ STUDENT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Name        : {profile.get('student_name')}
Age / Grade : {profile.get('age')} years / {profile.get('grade', 'N/A')}
School      : {profile.get('school_name', 'N/A')}
Disability  : {profile.get('disability_category')} ({profile.get('disability_severity', 'N/A')})

━━━ INSIGHTS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Strengths           : {json.dumps(insights.get('strengths', []))}
Challenges          : {json.dumps(insights.get('challenges', []))}
Learning Style      : {insights.get('learning_style', 'N/A')}
Academic Performance: {json.dumps(insights.get('academic_performance', {}))}
Behavioural Notes   : {json.dumps(insights.get('behavioural_notes', []))}
Assistive Tech Needs: {json.dumps(insights.get('assistive_tech_needs', []))}

━━━ LEGAL REQUIREMENTS — MUST INCLUDE ALL ━━━━━━━━━━━━
Mandatory Accommodations:
{json.dumps(compliance.get('mandatory_accommodations', []), indent=2)}

Identified Gaps to Address:
{json.dumps(compliance.get('identified_gaps', []), indent=2)}

Compliance Status: {compliance.get('status', 'partial')}

━━━ GOALS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Short-term Goals: {json.dumps(insights.get('short_term_goals', []))}
Long-term Goals : {json.dumps(insights.get('long_term_goals', []))}

Return EXACTLY this JSON with all 10 sections fully written:
{{
  "student_profile_summary": "2-paragraph narrative introducing the student, their disability, learning profile, and strengths-based framing. Must mention school name, grade, and disability category.",

  "present_levels": "Detailed description of current academic and functional performance. What the student CAN do (baseline) and where support is needed. Include specific subjects and skill areas.",

  "annual_goals": "3-5 numbered SMART annual goals. Format each as: Goal N: By [date], [student name] will [measurable action] as measured by [method].",

  "short_term_objectives": "Quarterly milestones for each annual goal. Format: Goal 1 Objectives: Q1: [milestone], Q2: [milestone], Q3: [milestone]",

  "special_education_services": "All special education services with: type of service, frequency (sessions per week), duration (minutes per session), service provider, and setting (in-class / pull-out).",

  "accommodations": "Comprehensive list grouped by category: Instructional Accommodations, Environmental Accommodations, Material Accommodations. Must include all legally mandated items.",

  "assessment_modifications": "Specific exam modifications. Must include extended time (minimum 25% extra as per RPwD Act). List each modification with justification.",

  "transition_planning": "{('Detailed transition plan for post-secondary education, vocational training, employment, and independent living. Include specific steps and timelines.' if needs_transition else 'N/A — Student is below 14 years. Transition planning will be introduced at age 14 as required by NCTE Guidelines Section 2.1(h).')}",

  "parental_involvement": "Plan for parental engagement: communication frequency, how parents receive progress updates, their role in IEP review, and consent documentation requirements.",

  "review_schedule": "Specific review schedule: monthly progress checks, quarterly goal reviews, and annual IEP meeting date. Include who is responsible for each review."
}}"""


def clean_json(raw: str) -> str:
    """Strip markdown fences if Gemini adds them."""
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        raw = "\n".join(lines)
    return raw.strip()


# ═══════════════════════════════════════════════════════
# DRAFTING AGENT NODE
# ═══════════════════════════════════════════════════════

def drafting_agent(state: IEPState) -> IEPState:
    """
    LangGraph node: Drafting Agent

    Takes insights + compliance report →
    calls Gemini → writes 10 IEP sections →
    returns DraftedIEP in state.
    """
    logger.info("✍️  Drafting Agent: Composing IEP sections...")

    profile    = state.get("student_profile", {})
    insights   = state.get("extracted_insights", {})
    compliance = state.get("compliance_report", {})
    errors     = list(state.get("error_log", []))

    # Validate prerequisites
    if not insights:
        errors.append("Drafting: No extracted insights found.")
        return {**state, "workflow_status": WorkflowStatus.FAILED,
                "error_log": errors}

    if not compliance:
        errors.append("Drafting: No compliance report found.")
        return {**state, "workflow_status": WorkflowStatus.FAILED,
                "error_log": errors}

    try:
        # ── Call Gemini ───────────────────────────────
        logger.info(f"  Drafting IEP for: {profile.get('student_name')}")

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=build_prompt(profile, insights, compliance)),
        ]
        response = llm.invoke(messages)
        raw_text = clean_json(response.content)

        # ── Parse JSON ────────────────────────────────
        parsed: DraftedIEP = json.loads(raw_text)

        # ── Validate all 10 sections present ─────────
        required_sections = [
            "student_profile_summary",
            "present_levels",
            "annual_goals",
            "short_term_objectives",
            "special_education_services",
            "accommodations",
            "assessment_modifications",
            "transition_planning",
            "parental_involvement",
            "review_schedule",
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

        logger.info(
            f"  ✅ All {len(required_sections)} IEP sections drafted"
        )

        return {
            **state,
            "drafted_iep":     parsed,
            "workflow_status": WorkflowStatus.REVIEWING,
            "current_node":    "drafting_agent",
            "error_log":       errors,
        }

    except json.JSONDecodeError as e:
        errors.append(f"Drafting: JSON parse error: {e}")
        logger.error(f"  ❌ JSON parse error: {e}")
        return {**state, "workflow_status": WorkflowStatus.FAILED,
                "error_log": errors}

    except Exception as e:
        errors.append(f"Drafting: Unexpected error: {e}")
        logger.error(f"  ❌ Unexpected error: {e}")
        return {**state, "workflow_status": WorkflowStatus.FAILED,
                "error_log": errors}