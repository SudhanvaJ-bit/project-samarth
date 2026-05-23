"""
tests/test_graph.py
Tests the LangGraph assembly — graph structure + pipeline run.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.state import WorkflowStatus
from agents.graph import build_graph, run_iep_pipeline, samarth_graph


# ── Mock student ──────────────────────────────────────
MOCK_STUDENT = {
    "student_name":        "Arjun Sharma",
    "age":                 10,
    "grade":               "Grade 4",
    "school_name":         "Delhi Public School, Bengaluru",
    "disability_category": "Dyslexia",
    "disability_severity": "moderate",
    "raw_notes": (
        "Arjun struggles with reading and written expression. "
        "He reverses letters like b/d and p/q. However, he excels "
        "in oral discussions and shows exceptional spatial reasoning. "
        "He is creative, enthusiastic, and has strong memory for facts "
        "when presented verbally. Loves science experiments."
    ),
    "academic_history": (
        "Grade 2: 58%, Grade 3: 62%. Below average in English and Hindi. "
        "Average in Maths. Good in EVS."
    ),
    "teacher_observations": (
        "Loses focus during sustained reading. Very engaged during "
        "group discussions and visual activities."
    ),
    "parent_concerns": (
        "Child hates homework and gets frustrated with reading. "
        "Very bright and curious at home."
    ),
}


def test_graph_compiles():
    """Test LangGraph compiles without errors."""
    print("\n🔗 Test 1: Graph compiles...")
    graph = build_graph()
    assert graph is not None, "Graph is None!"
    print("  ✅ Graph compiled successfully")


def test_graph_nodes_exist():
    """Test all expected nodes are registered."""
    print("\n🔗 Test 2: All nodes registered...")

    expected_nodes = [
        "supervisor_agent",
        "scraper_agent",
        "compliance_agent",
        "drafting_agent",
        "pdf_generator",
        "end_success",
        "end_failure",
    ]

    graph_nodes = list(samarth_graph.get_graph().nodes.keys())

    for node in expected_nodes:
        assert node in graph_nodes, f"Missing node: {node}"
        print(f"  ✅ Node registered: {node}")


def test_full_pipeline_run():
    """
    Test the complete pipeline runs end-to-end.
    This makes real Gemini API calls — takes 60-90 seconds.
    """
    print("\n🔗 Test 3: Full pipeline run (real API calls)...")
    print("  ⏳ Running all agents... (60-90 seconds)")

    final_state = run_iep_pipeline(MOCK_STUDENT, iep_id="test-graph-001")

    # Check pipeline completed
    status = final_state.get("workflow_status")
    errors = final_state.get("error_log", [])

    print(f"\n  Pipeline status : {status}")
    print(f"  Errors          : {errors if errors else 'None'}")

    assert status == WorkflowStatus.COMPLETED, \
        f"Pipeline failed with status: {status}\nErrors: {errors}"

    # Check all outputs present
    assert final_state.get("extracted_insights"), "No insights!"
    assert final_state.get("compliance_report"),  "No compliance report!"
    assert final_state.get("drafted_iep"),        "No drafted IEP!"
    assert final_state.get("pdf_output_path"),    "No PDF path!"

    # Check all 10 IEP sections drafted
    draft = final_state.get("drafted_iep", {})
    sections = [
        "student_profile_summary", "present_levels", "annual_goals",
        "short_term_objectives", "special_education_services",
        "accommodations", "assessment_modifications",
        "transition_planning", "parental_involvement", "review_schedule",
    ]
    for section in sections:
        assert draft.get(section), f"Missing IEP section: {section}"

    print(f"\n  ✅ Workflow status    : {status}")
    print(f"  ✅ Extracted insights : {len(final_state['extracted_insights'])} fields")
    print(f"  ✅ Compliance verdict : {final_state['compliance_report'].get('status')}")
    print(f"  ✅ IEP sections       : {len([s for s in sections if draft.get(s)])}/10")
    print(f"  ✅ PDF path           : {final_state['pdf_output_path']}")
    print(f"  ✅ Generated at       : {final_state.get('generated_at')}")


def test_pipeline_fails_on_bad_input():
    """Test pipeline fails gracefully on missing required fields."""
    print("\n🔗 Test 4: Pipeline fails on bad input...")

    bad_student = {
        "student_name": "Test Student",
        # Missing disability_category and raw_notes
    }

    final_state = run_iep_pipeline(bad_student)
    assert final_state["workflow_status"] == WorkflowStatus.FAILED
    assert len(final_state["error_log"]) > 0
    print(f"  ✅ Correctly failed: {final_state['error_log'][0]}")


if __name__ == "__main__":
    print("\n🧪 Running LangGraph Assembly Tests...\n")
    test_graph_compiles()
    test_graph_nodes_exist()
    test_pipeline_fails_on_bad_input()   # Quick test first
    test_full_pipeline_run()             # Full API test last
    print("\n🎉 ALL GRAPH TESTS PASSED — Step 8 Complete!\n")