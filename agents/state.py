"""
agents/state.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SAMARTH — Shared State for LangGraph Workflow
The single source of truth passed between all agents.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

from typing import TypedDict, Optional, List, Dict, Any
from enum import Enum


# ═══════════════════════════════════════════════
# ENUMS
# ═══════════════════════════════════════════════

class WorkflowStatus(str, Enum):
    INITIATED  = "initiated"
    SCRAPING   = "scraping"
    COMPLIANCE = "compliance"
    DRAFTING   = "drafting"
    REVIEWING  = "reviewing"
    GENERATING = "generating_pdf"
    COMPLETED  = "completed"
    FAILED     = "failed"


class ComplianceStatus(str, Enum):
    PENDING   = "pending"
    COMPLIANT = "compliant"
    PARTIAL   = "partial"
    VIOLATION = "violation"


# ═══════════════════════════════════════════════
# SUB-STRUCTURES
# ═══════════════════════════════════════════════

class StudentProfile(TypedDict, total=False):
    student_id:           str
    student_name:         str
    age:                  int
    grade:                str
    school_name:          str
    disability_category:  str
    disability_severity:  str
    raw_notes:            str
    academic_history:     str
    teacher_observations: str
    parent_concerns:      str


class ExtractedInsights(TypedDict, total=False):
    strengths:             List[str]
    challenges:            List[str]
    learning_style:        str
    recommended_supports:  List[str]
    short_term_goals:      List[str]
    long_term_goals:       List[str]
    academic_performance:  Dict[str, Any]
    behavioural_notes:     List[str]
    assistive_tech_needs:  List[str]


class ComplianceReport(TypedDict, total=False):
    status:                    ComplianceStatus
    rpwd_relevant_sections:    List[str]
    ncte_relevant_sections:    List[str]
    identified_gaps:           List[str]
    mandatory_accommodations:  List[str]
    compliance_notes:          str
    retrieval_sources:         List[Dict]


class DraftedIEP(TypedDict, total=False):
    """
    Standard NASET-format IEP sections
    adapted for Indian RPwD Act 2016 compliance.
    """
    # Section 1 — Background Information
    background_info:         str

    # Section 2 — Present Levels of Performance
    academic_performance:    str   # Academic/Educational Achievement
    social_development:      str   # Social Development
    physical_development:    str   # Physical Development
    management_needs:        str   # Management Needs

    # Section 3 — Long-Term Adult Outcomes (age 14+)
    long_term_outcomes:      str

    # Section 4 — Annual Goals and Short-Term Objectives
    annual_goals:            str

    # Section 5 — Special Education Programs and Services
    special_education_services: str

    # Section 6 — Participation in General Education
    general_education_participation: str

    # Section 7 — Participating Agencies (Transition)
    participating_agencies:  str

    # Section 8 — Coordinated Activities
    coordinated_activities:  str

    # Section 9 — Graduation / Completion Information
    graduation_info:         str

    # Section 10 — Summary of Recommendations
    recommendations_summary: str

    # Section 11 — Reporting Progress to Parents
    progress_reporting:      str


class QAReport(TypedDict, total=False):
    scraper_passed:     bool
    compliance_passed:  bool
    drafting_passed:    bool
    missing_fields:     List[str]
    retry_count:        int
    qa_notes:           str


class IEPState(TypedDict, total=False):
    # Input
    student_profile:     StudentProfile

    # Agent Outputs
    extracted_insights:  ExtractedInsights
    compliance_report:   ComplianceReport
    drafted_iep:         DraftedIEP
    qa_report:           QAReport

    # Workflow Control
    workflow_status:     WorkflowStatus
    current_node:        str
    error_log:           List[str]
    retry_count:         int

    # Final Output
    pdf_output_path:     str
    iep_id:              str
    generated_at:        str