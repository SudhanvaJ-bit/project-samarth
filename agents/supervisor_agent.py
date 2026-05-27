"""
agents/supervisor_agent.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 7 — SUPERVISOR AGENT

The orchestrator and quality gatekeeper.
NO LLM calls — pure Python logic only.
Reads WorkflowStatus and decides the next node.
Called BEFORE each agent to validate state is clean.

Key responsibilities:
  1. Validate input before scraping
  2. QA check scraper output
  3. QA check compliance output
  4. QA check drafted IEP
  5. Route to next node or retry/halt
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import logging
from typing import Literal
from agents.state import (
    IEPState, WorkflowStatus,
    ComplianceStatus, QAReport
)

logger = logging.getLogger(__name__)

MAX_RETRIES = 2

# ── Routing type ──────────────────────────────────────
NextNode = Literal[
    "scraper_agent",
    "compliance_agent",
    "drafting_agent",
    "pdf_generator",
    "end_success",
    "end_failure",
]


# ═══════════════════════════════════════════════════════
# QA CHECK FUNCTIONS
# Each returns (passed: bool, missing: list[str])
# ═══════════════════════════════════════════════════════

def _check_student_profile(state: IEPState):
    """Validates minimum required student input."""
    profile  = state.get("student_profile", {})
    required = ["student_name", "age", "disability_category", "raw_notes"]
    missing  = [f for f in required if not profile.get(f)]
    return len(missing) == 0, missing


def _check_scraper_output(state: IEPState):
    """Validates Scraper Agent produced complete output."""
    insights = state.get("extracted_insights", {})
    required = [
        "strengths", "challenges",
        "short_term_goals", "long_term_goals",
        "recommended_supports", "learning_style",
    ]
    missing = [
        f for f in required
        if not insights.get(f) or
        (isinstance(insights.get(f), list) and len(insights.get(f)) == 0)
    ]
    return len(missing) == 0, missing


def _check_compliance_output(state: IEPState):
    """Validates Compliance Agent produced a complete report."""
    report  = state.get("compliance_report", {})
    missing = []

    if not report.get("status"):
        missing.append("compliance_report.status")
    if not report.get("mandatory_accommodations"):
        missing.append("compliance_report.mandatory_accommodations")
    if not report.get("compliance_notes"):
        missing.append("compliance_report.compliance_notes")

    # Hard stop on VIOLATION
    if report.get("status") == ComplianceStatus.VIOLATION:
        return False, ["COMPLIANCE_VIOLATION — pipeline halted"]

    return len(missing) == 0, missing


def _check_drafting_output(state: IEPState):
    """Validates all 11 NASET IEP sections are present."""
    draft    = state.get("drafted_iep", {})
    required = [
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
    missing = [s for s in required if not draft.get(s)]
    return len(missing) == 0, missing


# ═══════════════════════════════════════════════════════
# SUPERVISOR AGENT NODE
# ═══════════════════════════════════════════════════════

def supervisor_agent(state: IEPState) -> IEPState:
    """
    LangGraph node: Supervisor Agent

    Called after each major agent.
    Checks output quality, decides proceed/retry/halt.
    Updates QAReport in state.
    """
    status  = state.get("workflow_status", WorkflowStatus.INITIATED)
    retries = state.get("retry_count", 0)
    errors  = list(state.get("error_log", []))

    logger.info(f"🧠 Supervisor: Reviewing stage → {status.value}")

    # Load or initialise QA report
    qa: QAReport = state.get("qa_report") or {
        "scraper_passed":    False,
        "compliance_passed": False,
        "drafting_passed":   False,
        "missing_fields":    [],
        "retry_count":       0,
        "qa_notes":          "",
    }

    # ── INITIATED — validate student input ────────────
    if status == WorkflowStatus.INITIATED:
        passed, missing = _check_student_profile(state)

        if not passed:
            errors.append(f"Supervisor: Invalid input — missing: {missing}")
            logger.error(f"  ❌ Input validation failed: {missing}")
            return {
                **state,
                "workflow_status": WorkflowStatus.FAILED,
                "qa_report": {
                    **qa,
                    "missing_fields": missing,
                    "qa_notes": "Input validation failed",
                },
                "error_log": errors,
            }

        logger.info("  ✅ Input validated → routing to Scraper")
        return {
            **state,
            "workflow_status": WorkflowStatus.SCRAPING,
            "current_node":    "supervisor_agent",
            "qa_report": {
                **qa,
                "qa_notes": "Input valid — proceeding to scraping",
            },
            "error_log": errors,
        }

    # ── COMPLIANCE — validate scraper output ──────────
    elif status == WorkflowStatus.COMPLIANCE:
        passed, missing = _check_scraper_output(state)

        if not passed:
            if retries < MAX_RETRIES:
                logger.warning(
                    f"  ⚠️  Scraper QA failed. "
                    f"Retry {retries + 1}/{MAX_RETRIES}"
                )
                return {
                    **state,
                    "workflow_status": WorkflowStatus.SCRAPING,
                    "retry_count":     retries + 1,
                    "qa_report": {
                        **qa,
                        "scraper_passed": False,
                        "missing_fields": missing,
                    },
                    "error_log": errors + [
                        f"Scraper retry {retries + 1}: missing {missing}"
                    ],
                }
            else:
                errors.append("Scraper failed after max retries")
                return {
                    **state,
                    "workflow_status": WorkflowStatus.FAILED,
                    "qa_report":       {**qa, "missing_fields": missing},
                    "error_log":       errors,
                }

        logger.info("  ✅ Scraper output validated → routing to Compliance")
        return {
            **state,
            "workflow_status": WorkflowStatus.COMPLIANCE,
            "qa_report": {
                **qa,
                "scraper_passed": True,
                "qa_notes":       "Scraper passed QA",
            },
            "error_log": errors,
        }

    # ── DRAFTING — validate compliance report ─────────
    elif status == WorkflowStatus.DRAFTING:
        passed, missing = _check_compliance_output(state)

        if not passed:
            # Hard stop on violation
            if any("VIOLATION" in m for m in missing):
                logger.error("  ❌ COMPLIANCE VIOLATION — halting")
                return {
                    **state,
                    "workflow_status": WorkflowStatus.FAILED,
                    "qa_report": {
                        **qa,
                        "compliance_passed": False,
                        "missing_fields":    missing,
                    },
                    "error_log": errors + missing,
                }

            if retries < MAX_RETRIES:
                return {
                    **state,
                    "workflow_status": WorkflowStatus.COMPLIANCE,
                    "retry_count":     retries + 1,
                    "error_log": errors + [
                        f"Compliance retry {retries + 1}"
                    ],
                }
            errors.append("Compliance failed after max retries")
            return {
                **state,
                "workflow_status": WorkflowStatus.FAILED,
                "error_log":       errors,
            }

        logger.info("  ✅ Compliance validated → routing to Drafting")
        return {
            **state,
            "workflow_status": WorkflowStatus.DRAFTING,
            "qa_report": {
                **qa,
                "compliance_passed": True,
                "qa_notes":          "Compliance passed QA",
            },
            "error_log": errors,
        }

    # ── REVIEWING — validate drafted IEP ──────────────
    elif status == WorkflowStatus.REVIEWING:
        passed, missing = _check_drafting_output(state)

        if not passed:
            if retries < MAX_RETRIES:
                logger.warning(
                    f"  ⚠️  Draft QA failed. "
                    f"Retry {retries + 1}/{MAX_RETRIES}"
                )
                return {
                    **state,
                    "workflow_status": WorkflowStatus.DRAFTING,
                    "retry_count":     retries + 1,
                    "error_log": errors + [
                        f"Draft retry {retries + 1}: missing {missing}"
                    ],
                }
            errors.append("Drafting failed after max retries")
            return {
                **state,
                "workflow_status": WorkflowStatus.FAILED,
                "error_log":       errors,
            }

        logger.info("  ✅ Draft validated → routing to PDF Generator")
        return {
            **state,
            "workflow_status": WorkflowStatus.GENERATING,
            "qa_report": {
                **qa,
                "drafting_passed": True,
                "qa_notes":        "All 10 sections complete",
            },
            "error_log": errors,
        }

    # ── Fallback ───────────────────────────────────────
    logger.error(f"  ❌ Unknown workflow status: {status}")
    return {
        **state,
        "workflow_status": WorkflowStatus.FAILED,
        "error_log": errors + [f"Supervisor: Unknown status: {status}"],
    }


# ═══════════════════════════════════════════════════════
# ROUTING FUNCTION
# Used by LangGraph conditional edges
# ═══════════════════════════════════════════════════════

def route_after_supervisor(state: IEPState) -> NextNode:
    """
    Conditional router called by LangGraph after supervisor_agent.
    Maps WorkflowStatus → next node name.
    """
    status = state.get("workflow_status")

    routing_map = {
        WorkflowStatus.SCRAPING:   "scraper_agent",
        WorkflowStatus.COMPLIANCE: "compliance_agent",
        WorkflowStatus.DRAFTING:   "drafting_agent",
        WorkflowStatus.GENERATING: "pdf_generator",
        WorkflowStatus.COMPLETED:  "end_success",
        WorkflowStatus.FAILED:     "end_failure",
    }

    next_node = routing_map.get(status, "end_failure")
    logger.info(f"  ➡️  Routing to: {next_node}")
    return next_node