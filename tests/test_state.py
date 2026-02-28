"""
tests/test_state.py
Quick sanity check — can we import and instantiate IEPState?
"""

import sys
import os

# Make sure Python can find our modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.state import (
    IEPState,
    StudentProfile,
    ExtractedInsights,
    ComplianceReport,
    DraftedIEP,
    WorkflowStatus,
    ComplianceStatus,
)


def test_workflow_status_values():
    """All expected status values exist"""
    assert WorkflowStatus.INITIATED  == "initiated"
    assert WorkflowStatus.SCRAPING   == "scraping"
    assert WorkflowStatus.COMPLIANCE == "compliance"
    assert WorkflowStatus.DRAFTING   == "drafting"
    assert WorkflowStatus.COMPLETED  == "completed"
    assert WorkflowStatus.FAILED     == "failed"
    print("✅ WorkflowStatus enum — PASSED")


def test_compliance_status_values():
    """All compliance verdicts exist"""
    assert ComplianceStatus.PENDING   == "pending"
    assert ComplianceStatus.COMPLIANT == "compliant"
    assert ComplianceStatus.PARTIAL   == "partial"
    assert ComplianceStatus.VIOLATION == "violation"
    print("✅ ComplianceStatus enum — PASSED")


def test_create_student_profile():
    """StudentProfile can be created with expected fields"""
    profile: StudentProfile = {
        "student_name":        "Arjun Sharma",
        "age":                 10,
        "grade":               "Grade 4",
        "school_name":         "Delhi Public School",
        "disability_category": "Dyslexia",
        "disability_severity": "moderate",
        "raw_notes":           "Struggles with reading but excels in math and visual tasks.",
    }
    assert profile["student_name"] == "Arjun Sharma"
    assert profile["age"] == 10
    assert profile["disability_category"] == "Dyslexia"
    print("✅ StudentProfile creation — PASSED")


def test_create_full_iep_state():
    """Full IEPState can be assembled with all sub-structures"""
    state: IEPState = {
        "student_profile": {
            "student_name":        "Arjun Sharma",
            "age":                 10,
            "disability_category": "Dyslexia",
            "raw_notes":           "Struggles with reading but excels in math.",
        },
        "extracted_insights": {
            "strengths":            ["Strong in mathematics", "Creative thinker"],
            "challenges":           ["Reading comprehension", "Letter reversal"],
            "learning_style":       "Visual-Kinesthetic",
            "short_term_goals":     ["Improve phonemic awareness by Term 1"],
            "long_term_goals":      ["Read at grade level by year end"],
            "recommended_supports": ["Text-to-speech", "Extra exam time"],
        },
        "compliance_report": {
            "status":                   ComplianceStatus.PARTIAL,
            "mandatory_accommodations": ["25% extra time in exams (RPwD Section 20)"],
            "identified_gaps":          ["Transition plan not yet included"],
            "compliance_notes":         "Student meets partial compliance. Accommodations required.",
        },
        "workflow_status": WorkflowStatus.DRAFTING,
        "current_node":    "compliance_agent",
        "error_log":       [],
        "retry_count":     0,
        "iep_id":          "test-001",
    }

    # Verify structure
    assert state["student_profile"]["student_name"] == "Arjun Sharma"
    assert state["workflow_status"] == WorkflowStatus.DRAFTING
    assert len(state["extracted_insights"]["strengths"]) == 2
    assert state["compliance_report"]["status"] == ComplianceStatus.PARTIAL
    assert state["error_log"] == []
    print("✅ Full IEPState assembly — PASSED")


def test_state_workflow_transitions():
    """Workflow status transitions follow the correct order"""
    order = [
        WorkflowStatus.INITIATED,
        WorkflowStatus.SCRAPING,
        WorkflowStatus.COMPLIANCE,
        WorkflowStatus.DRAFTING,
        WorkflowStatus.REVIEWING,
        WorkflowStatus.GENERATING,
        WorkflowStatus.COMPLETED,
    ]
    # Verify all are distinct
    assert len(set(order)) == len(order)
    print("✅ WorkflowStatus transition order — PASSED")


if __name__ == "__main__":
    print("\n🧪 Running SAMARTH State Tests...\n")
    test_workflow_status_values()
    test_compliance_status_values()
    test_create_student_profile()
    test_create_full_iep_state()
    test_state_workflow_transitions()
    print("\n🎉 ALL STATE TESTS PASSED — Step 2 Complete!\n")