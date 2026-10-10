"""
tests/test_integration.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 11 — FULL END-TO-END INTEGRATION TEST

Tests the complete SAMARTH pipeline:
  Real student input → Real Gemini calls → Real PDF file

This is the final proof that everything works together.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import sys
import os
import time
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.state  import WorkflowStatus, ComplianceStatus
from agents.graph  import run_iep_pipeline


# ── Test students — 3 different disability profiles ──

STUDENT_DYSLEXIA = {
    "student_name":         "Arjun Sharma",
    "age":                  10,
    "grade":                "Grade 4",
    "school_name":          "Delhi Public School, Bengaluru",
    "disability_category":  "Dyslexia",
    "disability_severity":  "moderate",
    "raw_notes": (
        "Arjun struggles significantly with reading and written expression. "
        "He reverses letters like b/d and p/q frequently. However, he excels "
        "in oral discussions and shows exceptional spatial reasoning. "
        "Creative, enthusiastic, strong verbal memory. Loves science experiments."
    ),
    "academic_history":      "Grade 2: 58%, Grade 3: 62%. Below average English/Hindi. Average Maths.",
    "teacher_observations":  "Loses focus during reading. Very engaged in group discussions.",
    "parent_concerns":       "Gets frustrated with reading at home. Very bright and curious.",
}

STUDENT_ASD = {
    "student_name":         "Priya Nair",
    "age":                  8,
    "grade":                "Grade 2",
    "school_name":          "Kendriya Vidyalaya, Chennai",
    "disability_category":  "Autism Spectrum Disorder",
    "disability_severity":  "mild",
    "raw_notes": (
        "Priya has difficulty with social interactions and prefers structured routines. "
        "She gets distressed by sudden changes in schedule. However, she demonstrates "
        "exceptional memory for facts and shows strong mathematical ability. "
        "She communicates well one-on-one but struggles in group settings."
    ),
    "academic_history":     "Grade 1: 72%. Strong in Maths and Science. Needs support in group activities.",
    "teacher_observations": "Prefers working alone. Excellent attention to detail. Sensitive to loud noises.",
    "parent_concerns":      "Difficulty making friends. Meltdowns during schedule changes.",
}

STUDENT_VISUAL = {
    "student_name":         "Rahul Verma",
    "age":                  14,
    "grade":                "Grade 9",
    "school_name":          "Jawahar Navodaya Vidyalaya, Pune",
    "disability_category":  "Visual Impairment",
    "disability_severity":  "moderate",
    "raw_notes": (
        "Rahul has low vision and requires large print materials and assistive technology. "
        "He is academically strong and highly motivated. Excellent in oral work, "
        "mathematics, and science. Struggles with standard printed textbooks and "
        "requires additional time for written work. Uses a magnifier currently."
    ),
    "academic_history":     "Grade 8: 78%. Strong across subjects. Needs assistive tech support.",
    "teacher_observations": "Very motivated. Needs front seating and large print materials.",
    "parent_concerns":      "Worried about board exam accommodations. Wants college education.",
}


# ═══════════════════════════════════════════════════════
# HELPER
# ═══════════════════════════════════════════════════════

NASET_SECTIONS = [
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


def run_and_validate(student: dict, test_name: str) -> dict:
    """Run pipeline and validate all outputs."""
    print(f"\n  ⏳ Running pipeline for {student['student_name']}...")
    start = time.time()

    state = run_iep_pipeline(student, iep_id=f"integration-{student['student_name'][:5].lower()}")

    elapsed = round(time.time() - start, 1)
    status  = state.get("workflow_status")
    errors  = state.get("error_log", [])

    print(f"  ⏱️  Completed in {elapsed}s")
    print(f"  📊 Status: {status}")

    if errors:
        print(f"  ⚠️  Errors: {errors}")

    # ── Assert pipeline completed ─────────────────────
    assert status == WorkflowStatus.COMPLETED, \
        f"{test_name} FAILED: status={status}\nErrors: {errors}"

    # ── Assert extracted insights ─────────────────────
    insights = state.get("extracted_insights", {})
    assert len(insights.get("strengths",        [])) > 0, "No strengths extracted"
    assert len(insights.get("challenges",       [])) > 0, "No challenges extracted"
    assert len(insights.get("short_term_goals", [])) > 0, "No short-term goals"
    assert len(insights.get("long_term_goals",  [])) > 0, "No long-term goals"

    # ── Assert compliance report ──────────────────────
    compliance = state.get("compliance_report", {})
    assert compliance.get("status") in [
        ComplianceStatus.COMPLIANT,
        ComplianceStatus.PARTIAL,
    ], f"Unexpected compliance status: {compliance.get('status')}"
    assert len(compliance.get("mandatory_accommodations", [])) > 0, \
        "No mandatory accommodations identified"

    # ── Assert all 14 IEP sections ────────────────────
    draft = state.get("drafted_iep", {})
    missing_sections = [s for s in NASET_SECTIONS if not draft.get(s)]
    assert len(missing_sections) == 0, \
        f"Missing IEP sections: {missing_sections}"

    # ── Assert PDF exists on disk ─────────────────────
    pdf_path = state.get("pdf_output_path", "")
    assert pdf_path, "No PDF path in state"
    assert Path(pdf_path).exists(), f"PDF file not found: {pdf_path}"

    pdf_size = Path(pdf_path).stat().st_size
    assert pdf_size > 5000, f"PDF too small: {pdf_size} bytes"

    print(f"  ✅ Insights      : {len(insights.get('strengths',[]))} strengths, "
          f"{len(insights.get('challenges',[]))} challenges")
    print(f"  ✅ Compliance    : {compliance.get('status')} | "
          f"{len(compliance.get('mandatory_accommodations',[]))} mandatory items")
    print(f"  ✅ IEP sections  : {len(NASET_SECTIONS)}/14 complete")
    print(f"  ✅ PDF           : {Path(pdf_path).name} ({pdf_size/1024:.1f} KB)")

    return state


# ═══════════════════════════════════════════════════════
# INTEGRATION TESTS
# ═══════════════════════════════════════════════════════

def test_dyslexia_pipeline():
    """Full pipeline: Dyslexia student."""
    print("\n🔗 Integration Test 1: Dyslexia — Arjun Sharma")
    state = run_and_validate(STUDENT_DYSLEXIA, "Dyslexia pipeline")

    # Dyslexia-specific assertions
    accommodations = state["compliance_report"].get("mandatory_accommodations", [])
    accomm_text    = " ".join(accommodations).lower()
    assert any(
        word in accomm_text
        for word in ["time", "text", "speech", "reading", "exam"]
    ), "Expected reading/time accommodations for Dyslexia"

    print("  ✅ Dyslexia-specific accommodations verified")


def test_asd_pipeline():
    """Full pipeline: Autism Spectrum Disorder student."""
    print("\n🔗 Integration Test 2: ASD — Priya Nair")
    run_and_validate(STUDENT_ASD, "ASD pipeline")
    print("  ✅ ASD pipeline complete")


def test_transition_planning_at_14():
    """Student aged 14+ must have real transition planning."""
    print("\n🔗 Integration Test 3: Transition Planning — Rahul Verma (age 14)")
    state = run_and_validate(STUDENT_VISUAL, "Visual Impairment + Transition")

    # Age 14+ must have real transition plan — not N/A
    transition = state["drafted_iep"].get("long_term_outcomes", "")
    assert "N/A" not in transition, \
        "Student is 14 — transition plan must not be N/A"
    assert len(transition) > 100, \
        "Transition plan too short for age 14+ student"

    print(f"  ✅ Transition plan present: {transition[:80]}...")


def test_pdf_files_exist():
    """All 3 generated PDFs exist and are valid."""
    print("\n🔗 Integration Test 4: All PDF files exist...")

    outputs = list(Path("./outputs").glob("IEP_*.pdf"))
    assert len(outputs) >= 3, f"Expected at least 3 PDFs, found {len(outputs)}"

    for pdf in outputs:
        size = pdf.stat().st_size
        assert size > 5000, f"PDF too small: {pdf.name} ({size} bytes)"
        print(f"  ✅ {pdf.name} — {size/1024:.1f} KB")


def test_pipeline_rejects_invalid_input():
    """Pipeline gracefully handles missing required fields."""
    print("\n🔗 Integration Test 5: Invalid input rejection...")

    bad_student = {"student_name": "Test", "age": 10}
    state       = run_iep_pipeline(bad_student)

    assert state["workflow_status"] == WorkflowStatus.FAILED
    assert len(state["error_log"]) > 0
    print(f"  ✅ Invalid input rejected: {state['error_log'][0]}")


# The API (login, ownership, review, download) is tested in tests/test_api.py
# with a stand-in pipeline, so it runs fast and offline.


if __name__ == "__main__":
    print("\n" + "="*55)
    print("  🧪 SAMARTH FULL INTEGRATION TEST SUITE")
    print("="*55)
    print("  Tests: 3 real students × full pipeline")
    print("  Expected time: 4-6 minutes (real Gemini calls)")
    print("="*55)

    start_all = time.time()

    test_pipeline_rejects_invalid_input()  # Quick — no API

    test_dyslexia_pipeline()               # ~90s — real API
    test_asd_pipeline()                    # ~90s — real API
    test_transition_planning_at_14()       # ~90s — real API

    test_pdf_files_exist()                 # Quick — file check

    total = round(time.time() - start_all, 1)

    print("\n" + "="*55)
    print(f"  🎉 ALL INTEGRATION TESTS PASSED!")
    print(f"  ⏱️  Total time: {total}s")
    print(f"  📂 PDFs in: D:\\SAMARTH\\outputs\\")
    print("="*55)
    print("\n  ✅ Project SAMARTH — Phase 1 COMPLETE!\n")