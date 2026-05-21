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
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import json
import logging
import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from agents.state import (
    IEPState, ComplianceReport,
    ComplianceStatus, WorkflowStatus
)
from rag.retriever import retriever

load_dotenv()
logger = logging.getLogger(__name__)

# ── Gemini Client ─────────────────────────────────────
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0.1,    # Very low — legal analysis must be precise
    google_api_key=os.getenv("GOOGLE_API_KEY"),
)

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

Return ONLY valid JSON. No markdown, no explanation, no preamble."""


def build_prompt(profile: dict, insights: dict, legal_text: str) -> str:
    age = int(profile.get("age", 0))
    needs_transition = age >= 14

    return f"""Conduct a legal compliance audit of this student's IEP plan.

━━━ STUDENT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Name             : {profile.get('student_name', 'N/A')}
Age              : {profile.get('age', 'N/A')} years
Disability       : {profile.get('disability_category', 'N/A')}
Severity         : {profile.get('disability_severity', 'N/A')}
Transition Needed: {'YES — age 14+ requires transition plan' if needs_transition else 'NO — below 14'}

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

Return EXACTLY this JSON:
{{
  "status": "compliant | partial | violation",
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
    "Legally required item 1 (RPwD Section X)",
    "Legally required item 2 (NCTE Guideline X.X)"
  ],
  "compliance_notes": "Concise legal reasoning for the verdict."
}}

Status definitions:
- compliant  : All legal requirements addressed
- partial    : Some gaps found but fixable in drafting
- violation  : Fundamental legal right being violated"""


def clean_json(raw: str) -> str:
    """Strip markdown fences if present."""
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        raw = "\n".join(lines)
    return raw.strip()


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

    try:
        # ══════════════════════════════════════════════
        # STEP 1 — Multi-Query RAG Retrieval
        # 4 targeted queries capture different legal angles
        # ══════════════════════════════════════════════

        logger.info(f"  📚 RAG Query 1: disability-specific law for {disability}")
        q1 = retriever.query_for_disability(disability, top_k=3)

        logger.info("  📚 RAG Query 2: mandatory IEP components")
        q2 = retriever.query_mandatory_iep_components()

        logger.info(f"  📚 RAG Query 3: assessment accommodations")
        q3 = retriever.query_assessment_accommodations(disability)

        q4 = []
        if age >= 14:
            logger.info("  📚 RAG Query 4: transition planning (age 14+)")
            q4 = retriever.query_transition_planning()

        # ── Deduplicate results ───────────────────────
        seen    = set()
        all_results = []
        for result in q1 + q2 + q3 + q4:
            key = result.text[:50]
            if key not in seen:
                seen.add(key)
                all_results.append(result)

        # Sort by score, keep top 8
        all_results.sort(key=lambda r: r.score, reverse=True)
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
        response = llm.invoke(messages)
        raw_text = clean_json(response.content)

        # ══════════════════════════════════════════════
        # STEP 4 — Parse and validate report
        # ══════════════════════════════════════════════

        parsed = json.loads(raw_text)

        # Validate status value
        raw_status = parsed.get("status", "partial").lower()
        try:
            status = ComplianceStatus(raw_status)
        except ValueError:
            status = ComplianceStatus.PARTIAL

        # Build compliance report
        compliance_report: ComplianceReport = {
            "status":                   status,
            "rpwd_relevant_sections":   parsed.get("rpwd_relevant_sections", []),
            "ncte_relevant_sections":   parsed.get("ncte_relevant_sections", []),
            "identified_gaps":          parsed.get("identified_gaps", []),
            "mandatory_accommodations": parsed.get("mandatory_accommodations", []),
            "compliance_notes":         parsed.get("compliance_notes", ""),
            "retrieval_sources": [
                {"source": r.source, "section": r.section, "score": r.score}
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
        errors.append(f"Compliance: JSON parse error: {e}")
        logger.error(f"  ❌ JSON parse error: {e}")
        return {
            **state,
            "workflow_status": WorkflowStatus.FAILED,
            "error_log":       errors,
        }

    except Exception as e:
        errors.append(f"Compliance: Unexpected error: {e}")
        logger.error(f"  ❌ Unexpected error: {e}")
        return {
            **state,
            "workflow_status": WorkflowStatus.FAILED,
            "error_log":       errors,
        }