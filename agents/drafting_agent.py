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
    dob_estimate     = f"approximately {2026 - age}"

    return f"""Draft a complete IEP in the standard NASET format for Indian schools.
MUST incorporate ALL mandatory accommodations from the compliance report.

━━━ STUDENT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Name        : {profile.get('student_name')}
Age / Grade : {profile.get('age')} years / {profile.get('grade', 'N/A')}
School      : {profile.get('school_name', 'N/A')}
Disability  : {profile.get('disability_category')} ({profile.get('disability_severity', 'N/A')})
DOB (approx): {dob_estimate}

━━━ INSIGHTS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Strengths           : {json.dumps(insights.get('strengths', []))}
Challenges          : {json.dumps(insights.get('challenges', []))}
Learning Style      : {insights.get('learning_style', 'N/A')}
Academic Performance: {json.dumps(insights.get('academic_performance', {}))}
Behavioural Notes   : {json.dumps(insights.get('behavioural_notes', []))}
Assistive Tech Needs: {json.dumps(insights.get('assistive_tech_needs', []))}
Recommended Supports: {json.dumps(insights.get('recommended_supports', []))}

━━━ LEGAL REQUIREMENTS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Mandatory Accommodations:
{json.dumps(compliance.get('mandatory_accommodations', []), indent=2)}
Compliance Status: {compliance.get('status', 'partial')}
Compliance Notes : {compliance.get('compliance_notes', '')}

━━━ GOALS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Short-term Goals: {json.dumps(insights.get('short_term_goals', []))}
Long-term Goals : {json.dumps(insights.get('long_term_goals', []))}

Return EXACTLY this JSON (write complete professional content, no placeholders):
{{
  "background_info": "Student name, school, grade, date of IEP meeting, disability classification per RPwD Act 2016, student ID format, dominant language, date of initiation of services. Parent/guardian names and contact. Medical alerts if any.",

  "academic_performance": "Section 2A: Current academic achievement levels across all subjects. State present levels for: Academic/Educational Achievement, Cognitive Ability, Language Ability, Learning Style, Rate of Progress. Use format: Present Level: [area] - [student name] is currently functioning [above/at/below] grade level in [area]. Include specific abilities and needs.",

  "social_development": "Section 2B: Quality of relationships with peers and adults, feelings about self, social adjustment, behaviors that may impede learning. Present levels of social interaction, self-concept, school/community adjustment. State specific abilities and needs.",

  "physical_development": "Section 2C: Motor and sensory development, health, vitality, physical skills or limitations. Reference the disability diagnosis. State abilities and needs related to physical participation in school.",

  "management_needs": "Section 2D: Nature and degree of environmental modifications and human/material resources required. State management needs level (minimal/moderate/significant) for academic, social, and physical goals. Describe abilities and support needed.",

  "long_term_outcomes": "{('Section 3: Post-secondary education/training plans, employment goals, community living goals. Transition service needs. Include guidance/career counseling, course requirements.' if needs_transition else 'Section 3: N/A — Student is below 14 years. Long-term adult outcomes and transition planning will be developed at age 14 per RPwD Act 2016 Section 17 and NCTE Guidelines.')}",

  "annual_goals": "Section 4: 3-4 measurable annual goals with short-term instructional objectives. Format each as: Annual Goal: [goal statement]. Short-term Objectives: 1. [objective] | Evaluation Procedures: [method] | Evaluation Schedule: [quarterly/monthly]. Cover academic, social, and functional areas.",

  "special_education_services": "Section 5: A. Special education programs with initiation date, frequency, duration. B. Extended school year services (Yes/No). C. Supplementary aids and modifications with initiation dates. D. Assistive technology devices/services needed (reference RPwD Act Section 17 for mandatory items). E. Program modifications for school personnel. F. Individual testing modifications including extended time (minimum 25% per RPwD Act).",

  "general_education_participation": "Section 6: Extent of participation in general education classes, non-academic and extracurricular activities including physical education. Explain any exemptions (e.g. second language). Describe support personnel required for inclusion.",

  "participating_agencies": "Section 7: {'Government agencies, NGOs, rehabilitation centres supporting transition services. Include DDRC, district resource centres, vocational training institutes.' if needs_transition else 'N/A — Transition services not yet applicable. Will be identified at age 14.'}",

  "coordinated_activities": "Section 8: Coordinated set of activities for long-term outcomes. Address: 1. Instruction, 2. Related Services, 3. Employment/Post-secondary Education, 4. Community Experience, 5. Activities of Daily Living, 6. Functional Vocational Assessment. Mark N/A for items not applicable at this age.",

  "graduation_info": "Section 9: Type of certificate/credential sought (e.g. CBSE/ICSE/State Board Certificate). Expected year of school completion. Any special provisions for board examinations under RPwD Act accommodations.",

  "recommendations_summary": "Section 10: Classification of disability per RPwD Act 2016 Schedule. Recommended placement (Inclusive/Resource Room/Special Class). Extended school year services. Transportation needs. Any additional recommendations from the IEP committee.",

  "progress_reporting": "Section 11: Manner and frequency of progress reporting to parents. Must include: frequency of reports (same as non-disabled peers), methods (report cards, teacher contact, progress reports), criteria for measuring progress toward annual goals, parent meeting schedule."
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