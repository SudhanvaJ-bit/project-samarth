"""
tests/test_supervisor.py
Tests the Supervisor Agent routing and QA logic.
No API calls — pure Python logic tests.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.state import WorkflowStatus, ComplianceStatus
from agents.supervisor_agent import supervisor_agent, route_after_supervisor


# ── Helpers ───────────────────────────────────────────
def make_state(**kwargs):
    base = {
        "error_log":   [],
        "retry_count": 0,
    }
    base.update(kwargs)
    return base


def test_validates_good_input():
    """Supervisor advances INITIATED → SCRAPING on valid input."""
    print("\n🧠 Test 1: Valid input validation...")

    state = make_state(
        workflow_status = WorkflowStatus.INITIATED,
        student_profile = {
            "student_name":        "Arjun Sharma",
            "age":                 10,
            "disability_category": "Dyslexia",
            "raw_notes":           "Struggles with reading",
        },
    )
    result = supervisor_agent(state)
    assert result["workflow_status"] == WorkflowStatus.SCRAPING
    print(f"  ✅ INITIATED → SCRAPING")


def test_rejects_missing_input():
    """Supervisor halts on missing required fields."""
    print("\n🧠 Test 2: Missing required input...")

    state = make_state(
        workflow_status = WorkflowStatus.INITIATED,
        student_profile = {"student_name": "Test"},
    )
    result = supervisor_agent(state)
    assert result["workflow_status"] == WorkflowStatus.FAILED
    assert len(result["error_log"]) > 0
    print(f"  ✅ Correctly halted: {result['error_log'][0]}")


def test_validates_scraper_output():
    """Supervisor advances COMPLIANCE → COMPLIANCE on good scraper output."""
    print("\n🧠 Test 3: Good scraper output...")

    state = make_state(
        workflow_status    = WorkflowStatus.COMPLIANCE,
        student_profile    = {"student_name": "Arjun"},
        extracted_insights = {
            "strengths":            ["Good at math"],
            "challenges":           ["Reading difficulty"],
            "short_term_goals":     ["Improve phonics by Term 1"],
            "long_term_goals":      ["Read at grade level"],
            "recommended_supports": ["Text-to-speech"],
            "learning_style":       "Visual",
        },
    )
    result = supervisor_agent(state)
    assert result["workflow_status"] == WorkflowStatus.COMPLIANCE
    assert result["qa_report"]["scraper_passed"] is True
    print(f"  ✅ Scraper QA passed → routing to Compliance Agent")


def test_retries_bad_scraper_output():
    """Supervisor retries on incomplete scraper output."""
    print("\n🧠 Test 4: Incomplete scraper output — retry...")

    state = make_state(
        workflow_status    = WorkflowStatus.COMPLIANCE,
        extracted_insights = {"strengths": ["Good"]},  # Missing most fields
    )
    result = supervisor_agent(state)
    assert result["workflow_status"] == WorkflowStatus.SCRAPING
    assert result["retry_count"] == 1
    print(f"  ✅ Retry triggered: retry_count = {result['retry_count']}")


def test_halts_on_compliance_violation():
    """Supervisor halts pipeline on compliance VIOLATION."""
    print("\n🧠 Test 5: Compliance violation — hard stop...")

    state = make_state(
        workflow_status   = WorkflowStatus.DRAFTING,
        compliance_report = {
            "status":                   ComplianceStatus.VIOLATION,
            "mandatory_accommodations": [],
            "compliance_notes":         "School refused to provide services",
        },
    )
    result = supervisor_agent(state)
    assert result["workflow_status"] == WorkflowStatus.FAILED
    print(f"  ✅ Correctly halted on VIOLATION")


def test_validates_drafted_iep():
    """Supervisor advances REVIEWING → GENERATING on complete draft."""
    print("\n🧠 Test 6: Complete drafted IEP...")

    state = make_state(
        workflow_status = WorkflowStatus.REVIEWING,
        drafted_iep     = {
            "student_profile_summary":    "Profile summary",
            "present_levels":             "Current performance",
            "annual_goals":               "Annual goals",
            "short_term_objectives":      "Short term objectives",
            "special_education_services": "Services",
            "accommodations":             "Accommodations",
            "assessment_modifications":   "Assessment mods",
            "transition_planning":        "N/A",
            "parental_involvement":       "Parent plan",
            "review_schedule":            "Review dates",
        },
    )
    result = supervisor_agent(state)
    assert result["workflow_status"] == WorkflowStatus.GENERATING
    assert result["qa_report"]["drafting_passed"] is True
    print(f"  ✅ Draft QA passed → routing to PDF Generator")


def test_routing_function():
    """Test route_after_supervisor maps all statuses correctly."""
    print("\n🧠 Test 7: Routing function...")

    tests = [
        (WorkflowStatus.SCRAPING,   "scraper_agent"),
        (WorkflowStatus.COMPLIANCE, "compliance_agent"),
        (WorkflowStatus.DRAFTING,   "drafting_agent"),
        (WorkflowStatus.GENERATING, "pdf_generator"),
        (WorkflowStatus.COMPLETED,  "end_success"),
        (WorkflowStatus.FAILED,     "end_failure"),
    ]

    for status, expected_node in tests:
        state  = make_state(workflow_status=status)
        result = route_after_supervisor(state)
        assert result == expected_node, \
            f"Expected {expected_node}, got {result}"
        print(f"  ✅ {status.value:<20} → {result}")


if __name__ == "__main__":
    print("\n🧪 Running Supervisor Agent Tests...\n")
    test_validates_good_input()
    test_rejects_missing_input()
    test_validates_scraper_output()
    test_retries_bad_scraper_output()
    test_halts_on_compliance_violation()
    test_validates_drafted_iep()
    test_routing_function()
    print("\n🎉 ALL SUPERVISOR TESTS PASSED — Step 7 Complete!\n")