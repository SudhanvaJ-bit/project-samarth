"""
agents/graph.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 8 — LANGGRAPH ASSEMBLY

Wires all 4 agents into a stateful directed workflow.

Flow:
  START
    ↓
  supervisor ──→ scraper ──→ supervisor ──→ compliance
                                               ↓
                            supervisor ←── drafting
                                ↓
                          pdf_generator
                                ↓
                              END
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import logging
import uuid
from datetime import datetime, timezone

from langgraph.graph import StateGraph, END

from agents.state            import IEPState, WorkflowStatus
from agents.scraper_agent    import scraper_agent
from agents.compliance_agent import compliance_agent
from agents.drafting_agent   import drafting_agent
from agents.supervisor_agent import supervisor_agent, route_after_supervisor

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════
# TERMINAL NODES
# ═══════════════════════════════════════════════════════

def pdf_generator_node(state: IEPState) -> IEPState:
    """
    Placeholder PDF generator node.
    Will be replaced by real ReportLab renderer in Step 9.
    """
    logger.info("📄 PDF Generator: (placeholder) IEP ready for rendering")
    return {
        **state,
        "workflow_status": WorkflowStatus.COMPLETED,
        "pdf_output_path": f"outputs/IEP_{state.get('iep_id', 'unknown')}.pdf",
        "current_node":    "pdf_generator",
    }


def end_success(state: IEPState) -> IEPState:
    """Terminal success node — stamps completion metadata."""
    logger.info("🎉 Workflow completed successfully!")
    return {
        **state,
        "workflow_status": WorkflowStatus.COMPLETED,
        "generated_at":    datetime.now(timezone.utc).isoformat(),
    }


def end_failure(state: IEPState) -> IEPState:
    """Terminal failure node — logs all accumulated errors."""
    errors = state.get("error_log", [])
    logger.error(f"❌ Workflow FAILED. Errors: {errors}")
    return {
        **state,
        "workflow_status": WorkflowStatus.FAILED,
        "generated_at":    datetime.now(timezone.utc).isoformat(),
    }


# ═══════════════════════════════════════════════════════
# GRAPH BUILDER
# ═══════════════════════════════════════════════════════

def build_graph():
    """
    Assembles and compiles the SAMARTH LangGraph workflow.

    Returns a compiled graph callable:
        result = graph.invoke(initial_state)
    """
    graph = StateGraph(IEPState)

    # ── Register all nodes ────────────────────────────
    graph.add_node("supervisor_agent",  supervisor_agent)
    graph.add_node("scraper_agent",     scraper_agent)
    graph.add_node("compliance_agent",  compliance_agent)
    graph.add_node("drafting_agent",    drafting_agent)
    graph.add_node("pdf_generator",     pdf_generator_node)
    graph.add_node("end_success",       end_success)
    graph.add_node("end_failure",       end_failure)

    # ── Entry point ───────────────────────────────────
    graph.set_entry_point("supervisor_agent")

    # ── Conditional edges from Supervisor ─────────────
    graph.add_conditional_edges(
        source   = "supervisor_agent",
        path     = route_after_supervisor,
        path_map = {
            "scraper_agent":    "scraper_agent",
            "compliance_agent": "compliance_agent",
            "drafting_agent":   "drafting_agent",
            "pdf_generator":    "pdf_generator",
            "end_success":      "end_success",
            "end_failure":      "end_failure",
        },
    )

    # ── Agents always return to Supervisor for QA ─────
    graph.add_edge("scraper_agent",    "supervisor_agent")
    graph.add_edge("compliance_agent", "supervisor_agent")
    graph.add_edge("drafting_agent",   "supervisor_agent")
    graph.add_edge("pdf_generator", "end_success")

    # ── Terminal nodes ────────────────────────────────
    graph.add_edge("end_success", END)
    graph.add_edge("end_failure", END)

    compiled = graph.compile()
    logger.info("✅ SAMARTH LangGraph compiled successfully")
    return compiled


# ── Singleton compiled graph ──────────────────────────
samarth_graph = build_graph()


# ═══════════════════════════════════════════════════════
# PIPELINE RUNNER
# ═══════════════════════════════════════════════════════

def run_iep_pipeline(student_data: dict, iep_id: str = None) -> IEPState:
    """
    Entry point for FastAPI and tests.
    Builds initial state and runs the complete graph.

    Args:
        student_data : Validated student dict
        iep_id       : Optional unique ID (auto-generated if not provided)

    Returns:
        Final IEPState after all agents have run
    """
    if not iep_id:
        iep_id = str(uuid.uuid4())

    initial_state: IEPState = {
        "student_profile":    student_data,
        "extracted_insights": {},
        "compliance_report":  {},
        "drafted_iep":        {},
        "qa_report":          {},
        "workflow_status":    WorkflowStatus.INITIATED,
        "current_node":       "start",
        "error_log":          [],
        "retry_count":        0,
        "pdf_output_path":    "",
        "iep_id":             iep_id,
        "generated_at":       "",
    }

    logger.info(f"🚀 Starting SAMARTH pipeline")
    logger.info(f"   IEP ID   : {iep_id}")
    logger.info(f"   Student  : {student_data.get('student_name')}")
    logger.info(f"   Disability: {student_data.get('disability_category')}")

    final_state = samarth_graph.invoke(initial_state)
    return final_state