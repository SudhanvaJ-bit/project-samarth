"""
tests/test_pdf.py
Tests the PDF Generator with mock IEP state.
"""

import sys
import os
import uuid
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.state            import WorkflowStatus, ComplianceStatus
from pdf_generator.iep_pdf   import generate_iep_pdf, pdf_generator_node


# ── Mock complete IEP state ───────────────────────────
MOCK_STATE = {
    "iep_id": "test-pdf-001",
    "student_profile": {
        "student_name":        "Arjun Sharma",
        "age":                 10,
        "grade":               "Grade 4",
        "school_name":         "Delhi Public School, Bengaluru",
        "disability_category": "Dyslexia",
        "disability_severity": "Moderate",
    },
    "compliance_report": {
        "status":                   ComplianceStatus.PARTIAL,
        "rpwd_relevant_sections":   ["Section 17(i): Extended time for exams"],
        "mandatory_accommodations": ["25% extra exam time", "Text-to-speech access"],
        "compliance_notes":         "Student qualifies for SLD accommodations.",
    },
    "drafted_iep": {
        "background_info": (
            "Student: Arjun Sharma | School: Delhi Public School, Bengaluru | "
            "Grade: 4 | Disability: Dyslexia (Moderate) per RPwD Act 2016 Schedule. "
            "Date of IEP Meeting: January 2026. Parent/Guardian: Mr. & Mrs. Sharma. "
            "Medical Alerts: None. Date of Initiation of Services: February 2026."
        ),
        "academic_performance": (
            "Present Level — Academic Achievement: Arjun is currently functioning "
            "below grade level in English and Hindi. He performs at grade level in "
            "Mathematics and above grade level in Environmental Science.\n"
            "Present Level — Learning Style: Arjun has an Auditory-Visual-Kinesthetic "
            "learning style. He learns best through oral instruction and hands-on activities.\n"
            "Abilities: Arjun can follow verbal instructions and excels in oral discussions.\n"
            "Needs: Arjun requires multi-sensory instruction and assistive technology "
            "for reading and writing tasks."
        ),
        "social_development": (
            "Present Level — Social Interaction: Arjun interacts well with peers in "
            "structured group activities. He initiates social interactions with adults.\n"
            "Abilities: Arjun has developed friendships and participates in group work.\n"
            "Needs: Arjun needs continued support in expressing frustration appropriately "
            "during academic tasks."
        ),
        "physical_development": (
            "Present Level — Physical: Arjun has no physical disabilities. He participates "
            "fully in all physical education and extracurricular activities.\n"
            "Abilities: Full participation in all school physical activities.\n"
            "Needs: No physical management needs identified."
        ),
        "management_needs": (
            "Arjun has moderate management needs for academic goals. He requires "
            "assistive technology, extended time, and specialist teacher support.\n"
            "Social management needs are minimal. Physical management needs are none.\n"
            "Abilities: Arjun performs effectively with additional support and technology.\n"
            "Needs: Full inclusion placement with moderate special education support."
        ),
        "long_term_outcomes": (
            "N/A — Student is below 14 years. Transition planning will be introduced "
            "at age 14 per RPwD Act 2016 Section 17 and NCTE Guidelines."
        ),
        "annual_goals": (
            "Annual Goal 1: Arjun will improve reading fluency and comprehension.\n"
            "Short-term Objectives:\n"
            "1. Decode 80% of CVC words | Evaluation: Phonics test | Schedule: Quarterly\n"
            "2. Read Grade 3 passage with 70% comprehension | Evaluation: Teacher assessment | Schedule: Term-end\n\n"
            "Annual Goal 2: Arjun will improve written expression.\n"
            "Short-term Objectives:\n"
            "1. Write 3-sentence paragraph with correct punctuation | Evaluation: Writing rubric | Schedule: Quarterly"
        ),
        "special_education_services": (
            "A. Special Education Services:\n"
            "Reading Intervention — 3x/week, 45 min, Special Education Teacher, Pull-out\n"
            "Writing Support — 2x/week, 30 min, Resource Teacher, In-class\n\n"
            "B. Extended School Year: No\n\n"
            "C. Supplementary Aids:\n"
            "Text-to-speech software — November 2025\n"
            "Extended exam time (25% minimum per RPwD Act) — November 2025\n\n"
            "D. Assistive Technology: Text-to-speech and speech-to-text software required.\n\n"
            "F. Testing Modifications: 25% extended time on all assessments (RPwD Act Section 17). "
            "Oral responses permitted. Scribe available for written exams."
        ),
        "general_education_participation": (
            "Arjun will participate in all general education classes with support personnel. "
            "He will be included in all non-academic and extracurricular activities.\n"
            "Support: Special education teacher provides in-class support during English and Hindi lessons."
        ),
        "participating_agencies": (
            "N/A — Transition services not applicable at this age. "
            "Will be identified at age 14."
        ),
        "coordinated_activities": (
            "1. Instruction: Multi-sensory literacy instruction programme.\n"
            "2. Related Services: Speech-language therapy assessment recommended.\n"
            "3. Employment/Post-secondary: N/A\n"
            "4. Community Experience: N/A\n"
            "5. Activities of Daily Living: N/A\n"
            "6. Functional Vocational Assessment: N/A"
        ),
        "graduation_info": (
            "Credential Sought: CBSE Secondary School Certificate.\n"
            "Expected Completion: 2030.\n"
            "Board Exam Accommodations: Extended time and scribe as per RPwD Act 2016 — "
            "to be applied for through the school examination committee."
        ),
        "recommendations_summary": (
            "Disability Classification: Specific Learning Disability — Dyslexia (RPwD Act 2016 Schedule).\n"
            "Recommended Placement: Full inclusion with moderate support.\n"
            "Extended School Year: No.\n"
            "Transportation: Standard school transport — no special needs.\n"
            "Additional Recommendations: Annual IEP review in January 2027. "
            "Quarterly progress monitoring by Special Education Coordinator."
        ),
        "progress_reporting": (
            "Parents will be informed of progress with same frequency as non-disabled students.\n"
            "Methods: Quarterly progress reports, term-end report cards, monthly teacher contact.\n"
            "Criteria: Progress toward annual goals measured by assessment results and teacher observation.\n"
            "Parent Meetings: End of each academic term.\n"
            "Emergency Contact: Class teacher to contact parents immediately if significant regression observed."
        ),
    },
    "error_log":       [],
    "workflow_status": WorkflowStatus.GENERATING,
}


def test_pdf_generates():
    """Test PDF file is created successfully."""
    print("\n📄 Test 1: PDF generation...")

    pdf_path = generate_iep_pdf(MOCK_STATE)

    assert pdf_path, "No PDF path returned!"
    assert Path(pdf_path).exists(), f"PDF file not found: {pdf_path}"
    assert Path(pdf_path).stat().st_size > 1000, "PDF file too small!"

    size_kb = Path(pdf_path).stat().st_size / 1024
    print(f"  ✅ PDF generated  : {pdf_path}")
    print(f"  ✅ File size      : {size_kb:.1f} KB")


def test_pdf_filename_format():
    """Test PDF has correct filename format."""
    print("\n📄 Test 2: Filename format...")

    state = {**MOCK_STATE, "iep_id": "abcd1234-efgh"}
    pdf_path = generate_iep_pdf(state)

    filename = Path(pdf_path).name
    assert "Arjun_Sharma" in filename, f"Student name missing: {filename}"
    assert "abcd1234" in filename,     f"IEP ID missing: {filename}"
    assert filename.endswith(".pdf"),  f"Not a PDF: {filename}"
    print(f"  ✅ Filename correct: {filename}")


def test_pdf_node_updates_state():
    """Test pdf_generator_node updates state correctly."""
    print("\n📄 Test 3: LangGraph node updates state...")

    result = pdf_generator_node(MOCK_STATE)

    assert result["workflow_status"] == WorkflowStatus.COMPLETED
    assert result["pdf_output_path"], "No PDF path in state!"
    assert Path(result["pdf_output_path"]).exists()

    print(f"  ✅ Workflow status : {result['workflow_status']}")
    print(f"  ✅ PDF path in state: {result['pdf_output_path']}")


def test_pdf_node_fails_without_draft():
    """Test PDF node fails gracefully without drafted IEP."""
    print("\n📄 Test 4: Fails without drafted IEP...")

    empty_state = {
        "iep_id":          "test-empty",
        "student_profile": {},
        "drafted_iep":     {},
        "error_log":       [],
    }
    result = pdf_generator_node(empty_state)
    assert result["workflow_status"] == WorkflowStatus.FAILED
    print(f"  ✅ Correctly failed: {result['error_log'][0]}")


if __name__ == "__main__":
    print("\n🧪 Running PDF Generator Tests...\n")
    test_pdf_generates()
    test_pdf_filename_format()
    test_pdf_node_updates_state()
    test_pdf_node_fails_without_draft()
    print("\n🎉 ALL PDF TESTS PASSED — Step 9 Complete!\n")
    print("📂 Check D:\\SAMARTH\\outputs\\ for your generated PDFs!")