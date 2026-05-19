"""
tests/test_scraper.py
Tests the Scraper Agent with a mock student profile.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.state    import WorkflowStatus
from agents.scraper_agent import scraper_agent


# ── Mock student profile ──────────────────────────────
MOCK_STUDENT = {
    "student_name":        "Arjun Sharma",
    "age":                 10,
    "grade":               "Grade 4",
    "school_name":         "Delhi Public School, Bengaluru",
    "disability_category": "Dyslexia",
    "disability_severity": "moderate",
    "raw_notes": (
        "Arjun struggles significantly with reading and written expression. "
        "He reverses letters like b/d and p/q frequently. "
        "However, he excels in oral discussions and shows exceptional "
        "spatial reasoning. He is creative, enthusiastic, and has strong "
        "memory for facts when presented verbally. Loves science experiments."
    ),
    "academic_history": (
        "Grade 2: 58%, Grade 3: 62%. Consistently below average in "
        "English and Hindi. Average in Maths. Good in EVS."
    ),
    "teacher_observations": (
        "Loses focus during sustained reading tasks. Very engaged during "
        "group discussions and visual activities. Takes longer to copy "
        "from board. Gets frustrated during written tests."
    ),
    "parent_concerns": (
        "Child hates homework and gets very frustrated with reading. "
        "Very bright and curious at home. Loves building things."
    ),
}


def test_scraper_with_valid_input():
    """Test scraper with complete student profile."""
    print("\n🔍 Test 1: Valid student input...")

    initial_state = {
        "student_profile": MOCK_STUDENT,
        "error_log":       [],
        "retry_count":     0,
    }

    result = scraper_agent(initial_state)

    # Check workflow advanced
    assert result["workflow_status"] == WorkflowStatus.COMPLIANCE, \
        f"Expected COMPLIANCE, got {result['workflow_status']}"

    # Check insights extracted
    insights = result.get("extracted_insights", {})
    assert insights, "No insights extracted!"

    assert len(insights.get("strengths", [])) > 0,         "No strengths!"
    assert len(insights.get("challenges", [])) > 0,        "No challenges!"
    assert len(insights.get("short_term_goals", [])) > 0,  "No short-term goals!"
    assert len(insights.get("long_term_goals", [])) > 0,   "No long-term goals!"
    assert insights.get("learning_style"),                  "No learning style!"

    print(f"  ✅ Status       : {result['workflow_status']}")
    print(f"  ✅ Strengths    : {insights['strengths']}")
    print(f"  ✅ Challenges   : {insights['challenges']}")
    print(f"  ✅ Learning style: {insights['learning_style']}")
    print(f"  ✅ Short goals  : {insights['short_term_goals']}")
    print(f"  ✅ Long goals   : {insights['long_term_goals']}")
    print(f"  ✅ Supports     : {insights.get('recommended_supports', [])}")


def test_scraper_with_missing_fields():
    """Test scraper correctly fails when required fields missing."""
    print("\n🔍 Test 2: Missing required fields...")

    initial_state = {
        "student_profile": {
            "student_name": "Test Student",
            # Missing disability_category and raw_notes
        },
        "error_log":   [],
        "retry_count": 0,
    }

    result = scraper_agent(initial_state)

    assert result["workflow_status"] == WorkflowStatus.FAILED
    assert len(result["error_log"]) > 0
    print(f"  ✅ Correctly failed: {result['error_log'][0]}")


def test_scraper_preserves_state():
    """Test scraper doesn't wipe existing state fields."""
    print("\n🔍 Test 3: State preservation...")

    initial_state = {
        "student_profile": MOCK_STUDENT,
        "iep_id":          "test-123",
        "error_log":       [],
        "retry_count":     0,
    }

    result = scraper_agent(initial_state)

    assert result.get("iep_id") == "test-123", "iep_id was wiped!"
    print(f"  ✅ State preserved: iep_id = {result['iep_id']}")


if __name__ == "__main__":
    print("\n🧪 Running Scraper Agent Tests...\n")
    test_scraper_with_valid_input()
    test_scraper_with_missing_fields()
    test_scraper_preserves_state()
    print("\n🎉 ALL SCRAPER TESTS PASSED — Step 4 Complete!\n")