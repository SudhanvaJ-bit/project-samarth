"""
tests/test_drafting.py
Tests the Drafting Agent with mock insights + compliance report.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.state import WorkflowStatus, ComplianceStatus
from agents.drafting_agent import drafting_agent


# ── Mock data ─────────────────────────────────────────
MOCK_PROFILE = {
    "student_name": "Arjun Sharma",
    "age": 10,
    "grade": "Grade 4",
    "school_name": "Delhi Public School, Bengaluru",
    "disability_category": "Dyslexia",
    "disability_severity": "moderate",
}

MOCK_INSIGHTS = {
    "strengths": [
        "Strong oral communication",
        "Excellent spatial reasoning",
        "Creative thinker"
    ],

    "challenges": [
        "Reading comprehension",
        "Letter reversal b/d",
        "Written expression"
    ],

    "learning_style": "Auditory-Visual-Kinesthetic",

    "recommended_supports": [
        "Text-to-speech software",
        "Extended exam time",
        "Oral assessments"
    ],

    "short_term_goals": [
        "By end of Term 1, Arjun will accurately decode 80% of CVC words as measured by phonics assessment",

        "By end of Term 2, Arjun will write a 3-sentence paragraph with correct punctuation in 2 of 3 attempts",
    ],

    "long_term_goals": [
        "By end of academic year, Arjun will read Grade 3 passage with 70% comprehension"
    ],

    "academic_performance": {
        "overall_level": "below_grade",
        "strong_subjects": ["Mathematics", "EVS"],
        "weak_subjects": ["English", "Hindi"],
        "grade_trajectory": "improving",
    },

    "behavioural_notes": [
        "Loses focus during reading",
        "Engaged in group work"
    ],

    "assistive_tech_needs": [
        "Text-to-speech",
        "Speech-to-text"
    ],
}

MOCK_COMPLIANCE = {
    "status": ComplianceStatus.PARTIAL,

    "rpwd_relevant_sections": [
        "Section 17(i): Extended time for exam completion"
    ],

    "ncte_relevant_sections": [
        "Guideline 2.6.3: Individualized reasonable accommodation"
    ],

    "identified_gaps": [
        "Assistive technology not formally documented"
    ],

    "mandatory_accommodations": [
        "Extended exam time minimum 25% (RPwD Act Section 17)",
        "Text-to-speech software provision (RPwD Act Section 17)",
    ],

    "compliance_notes":
        "Student qualifies for all SLD accommodations under RPwD Act.",
}


# ──────────────────────────────────────────────────────
# Helper Function
# ──────────────────────────────────────────────────────

def safe_preview(content, length=80):
    """
    Safely convert any content type into preview text.
    Handles strings, lists, dicts, etc.
    """

    if isinstance(content, list):
        preview = " | ".join(map(str, content))

    elif isinstance(content, dict):
        preview = str(content)

    else:
        preview = str(content).replace("\n", " ")

    return preview[:length]


# ──────────────────────────────────────────────────────
# TEST 1
# ──────────────────────────────────────────────────────

def test_drafting_all_sections():
    """Test all 10 IEP sections are drafted."""

    print("\n✍️  Test 1: Draft all 10 IEP sections...")

    state = {
        "student_profile": MOCK_PROFILE,
        "extracted_insights": MOCK_INSIGHTS,
        "compliance_report": MOCK_COMPLIANCE,
        "error_log": [],
        "retry_count": 0,
    }

    result = drafting_agent(state)

    assert result["workflow_status"] == WorkflowStatus.REVIEWING, \
        f"Expected REVIEWING, got {result['workflow_status']}\nErrors: {result.get('error_log')}"

    draft = result.get("drafted_iep", {})
    assert draft, "No drafted IEP!"

    required = [
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

    print(f"  ✅ Workflow status: {result['workflow_status']}")
    print("\n  📋 IEP Sections drafted:")

    for section in required:
        content = draft.get(section, "")

        assert content, f"Section '{section}' is empty!"

        preview = safe_preview(content)

        print(f"  ✅ {section:<30} : {preview}...")


# ──────────────────────────────────────────────────────
# TEST 2
# ──────────────────────────────────────────────────────

def test_drafting_missing_compliance():
    """Test drafting fails without compliance report."""

    print("\n✍️  Test 2: Missing compliance report...")

    state = {
        "student_profile": MOCK_PROFILE,
        "extracted_insights": MOCK_INSIGHTS,
        "compliance_report": {},  # Missing compliance
        "error_log": [],
        "retry_count": 0,
    }

    result = drafting_agent(state)

    assert result["workflow_status"] == WorkflowStatus.FAILED

    print(f"  ✅ Correctly failed: {result['error_log'][0]}")


# ──────────────────────────────────────────────────────
# TEST 3
# ──────────────────────────────────────────────────────

def test_drafting_preserves_state():
    """Test drafting doesn't wipe previous state."""

    print("\n✍️  Test 3: State preservation...")

    state = {
        "student_profile": MOCK_PROFILE,
        "extracted_insights": MOCK_INSIGHTS,
        "compliance_report": MOCK_COMPLIANCE,
        "iep_id": "test-789",
        "error_log": [],
        "retry_count": 0,
    }

    result = drafting_agent(state)

    assert result.get("iep_id") == "test-789"

    assert result.get("compliance_report") == MOCK_COMPLIANCE

    print(f"  ✅ State preserved: iep_id = {result['iep_id']}")


# ──────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────

if __name__ == "__main__":

    print("\n🧪 Running Drafting Agent Tests...\n")

    test_drafting_all_sections()

    test_drafting_missing_compliance()

    test_drafting_preserves_state()

    print("\n🎉 ALL DRAFTING TESTS PASSED — Step 6 Complete!\n")