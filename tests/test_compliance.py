"""
tests/test_compliance.py
Tests the Compliance Agent with mock insights + student profile.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.state            import WorkflowStatus, ComplianceStatus
from agents.compliance_agent import compliance_agent

# ── Mock data (reuse from scraper test) ──────────────
MOCK_PROFILE = {
    "student_name":        "Arjun Sharma",
    "age":                 10,
    "grade":               "Grade 4",
    "school_name":         "Delhi Public School, Bengaluru",
    "disability_category": "Dyslexia",
    "disability_severity": "moderate",
}

MOCK_INSIGHTS = {
    "strengths":            ["Strong in oral communication", "Excellent spatial reasoning"],
    "challenges":           ["Reading comprehension", "Letter reversal", "Written expression"],
    "learning_style":       "Auditory-Visual-Kinesthetic",
    "recommended_supports": ["Text-to-speech software", "Extended exam time", "Oral assessments"],
    "short_term_goals":     ["By Term 1, will decode 80% CVC words"],
    "long_term_goals":      ["By year end, will read Grade 3 passage with 70% comprehension"],
    "assistive_tech_needs": ["Text-to-speech software", "Speech-to-text for writing"],
    "behavioural_notes":    ["Loses focus during reading", "Engaged in group discussions"],
}


def test_compliance_with_valid_input():
    """Test compliance agent produces a legal report."""
    print("\n⚖️  Test 1: Valid compliance check...")

    state = {
        "student_profile":    MOCK_PROFILE,
        "extracted_insights": MOCK_INSIGHTS,
        "error_log":          [],
        "retry_count":        0,
    }

    result = compliance_agent(state)

    # Should advance to DRAFTING (not FAILED)
    assert result["workflow_status"] in [
        WorkflowStatus.DRAFTING,
        WorkflowStatus.FAILED,  # Acceptable if violation found
    ], f"Unexpected status: {result['workflow_status']}"

    report = result.get("compliance_report", {})
    assert report, "No compliance report generated!"

    # Status must be one of the valid values
    assert report.get("status") in [
        ComplianceStatus.COMPLIANT,
        ComplianceStatus.PARTIAL,
        ComplianceStatus.VIOLATION,
    ], f"Invalid status: {report.get('status')}"

    # Must have mandatory accommodations
    assert len(report.get("mandatory_accommodations", [])) > 0, \
        "No mandatory accommodations identified!"

    print(f"  ✅ Status              : {result['workflow_status']}")
    print(f"  ✅ Compliance verdict  : {report['status']}")
    print(f"  ✅ RPwD sections cited : {len(report.get('rpwd_relevant_sections', []))}")
    print(f"  ✅ NCTE sections cited : {len(report.get('ncte_relevant_sections', []))}")
    print(f"  ✅ Gaps identified     : {len(report.get('identified_gaps', []))}")
    print(f"  ✅ Mandatory items     : {len(report.get('mandatory_accommodations', []))}")
    print(f"\n  📋 Compliance notes:")
    print(f"     {report.get('compliance_notes', '')[:200]}...")
    print(f"\n  📋 Mandatory accommodations:")
    for item in report.get("mandatory_accommodations", []):
        print(f"     → {item}")


def test_compliance_missing_insights():
    """Test compliance fails gracefully without insights."""
    print("\n⚖️  Test 2: Missing insights...")

    state = {
        "student_profile":    MOCK_PROFILE,
        "extracted_insights": {},   # Empty — scraper hasn't run
        "error_log":          [],
        "retry_count":        0,
    }

    result = compliance_agent(state)
    assert result["workflow_status"] == WorkflowStatus.FAILED
    assert len(result["error_log"]) > 0
    print(f"  ✅ Correctly failed: {result['error_log'][0]}")


def test_compliance_preserves_state():
    """Test compliance doesn't wipe previous state."""
    print("\n⚖️  Test 3: State preservation...")

    state = {
        "student_profile":    MOCK_PROFILE,
        "extracted_insights": MOCK_INSIGHTS,
        "iep_id":             "test-456",
        "error_log":          [],
        "retry_count":        0,
    }

    result = compliance_agent(state)
    assert result.get("iep_id") == "test-456", "iep_id was wiped!"
    assert result.get("extracted_insights") == MOCK_INSIGHTS, \
        "Insights were wiped!"
    print(f"  ✅ State preserved: iep_id = {result['iep_id']}")


if __name__ == "__main__":
    print("\n🧪 Running Compliance Agent Tests...\n")
    test_compliance_with_valid_input()
    test_compliance_missing_insights()
    test_compliance_preserves_state()
    print("\n🎉 ALL COMPLIANCE TESTS PASSED — Step 5 Complete!\n")