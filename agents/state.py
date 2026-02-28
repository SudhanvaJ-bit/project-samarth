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
    student_profile_summary:     str
    present_levels:              str
    annual_goals:                str
    short_term_objectives:       str
    special_education_services:  str
    accommodations:              str
    assessment_modifications:    str
    transition_planning:         str
    parental_involvement:        str
    review_schedule:             str


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