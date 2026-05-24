"""
pdf_generator/iep_pdf.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 9 — PDF GENERATOR (NASET Standard Format)

Renders IEP in the standard NASET 11-section format
adapted for Indian RPwD Act 2016 compliance.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import os
import logging
from datetime import datetime
from pathlib import Path

from reportlab.lib.pagesizes  import A4
from reportlab.lib.styles     import ParagraphStyle
from reportlab.lib.units      import cm
from reportlab.lib            import colors
from reportlab.platypus       import (
    SimpleDocTemplate, Paragraph, Spacer,
    Table, TableStyle, HRFlowable,
    PageBreak, KeepTogether,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT

from agents.state import IEPState, WorkflowStatus

logger     = logging.getLogger(__name__)
OUTPUT_DIR = Path(os.getenv("IEP_OUTPUT_DIR", "./outputs"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Colour palette ────────────────────────────────────
NAVY   = colors.HexColor("#1a3a5c")
TEAL   = colors.HexColor("#17a589")
LIGHT  = colors.HexColor("#eaf4f4")
GOLD   = colors.HexColor("#d4ac0d")
GREY   = colors.HexColor("#7f8c8d")
LGREY  = colors.HexColor("#f2f3f4")
WHITE  = colors.white
BLACK  = colors.black
GREEN  = colors.HexColor("#1e8449")
RED    = colors.HexColor("#c0392b")


# ═══════════════════════════════════════════════════════
# STYLES
# ═══════════════════════════════════════════════════════

def get_styles() -> dict:
    return {
        "doc_title": ParagraphStyle(
            "DocTitle", fontSize=15, fontName="Helvetica-Bold",
            textColor=WHITE, alignment=TA_CENTER, spaceAfter=2,
        ),
        "doc_subtitle": ParagraphStyle(
            "DocSubtitle", fontSize=9, fontName="Helvetica",
            textColor=LIGHT, alignment=TA_CENTER, spaceAfter=0,
        ),
        "section_title": ParagraphStyle(
            "SectionTitle", fontSize=10, fontName="Helvetica-Bold",
            textColor=WHITE, leading=14, leftIndent=6,
        ),
        "subsection": ParagraphStyle(
            "Subsection", fontSize=9.5, fontName="Helvetica-Bold",
            textColor=NAVY, spaceAfter=3, spaceBefore=6,
        ),
        "body": ParagraphStyle(
            "Body", fontSize=9, fontName="Helvetica",
            textColor=BLACK, spaceAfter=4, leading=13,
        ),
        "label": ParagraphStyle(
            "Label", fontSize=8.5, fontName="Helvetica-Bold",
            textColor=NAVY, spaceAfter=1,
        ),
        "footer": ParagraphStyle(
            "Footer", fontSize=7, fontName="Helvetica",
            textColor=GREY, alignment=TA_CENTER,
        ),
        "cite": ParagraphStyle(
            "Cite", fontSize=8, fontName="Helvetica-Oblique",
            textColor=GREY, spaceAfter=3, leading=11,
        ),
    }


# ═══════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════

def section_header(number: int, title: str, styles: dict) -> Table:
    """Navy section header bar."""
    t = Table(
        [[Paragraph(f"  Section {number} — {title}", styles["section_title"])]],
        colWidths=[17 * cm],
    )
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), NAVY),
        ("TOPPADDING",    (0,0),(-1,-1), 7),
        ("BOTTOMPADDING", (0,0),(-1,-1), 7),
    ]))
    return t


def body_block(content: str, styles: dict) -> list:
    """Split content on newlines → list of Paragraphs."""
    elements = []
    if isinstance(content, dict):
        content = "\n".join(f"{k}: {v}" for k, v in content.items())
    for line in str(content).split("\n"):
        line = line.strip()
        if line:
            elements.append(Paragraph(line, styles["body"]))
    return elements


def info_row(label: str, value: str) -> list:
    """Single label+value row for info tables."""
    return [label, value]


# ═══════════════════════════════════════════════════════
# MAIN PDF BUILDER
# ═══════════════════════════════════════════════════════

def generate_iep_pdf(state: IEPState) -> str:
    """Renders full NASET-format IEP PDF. Returns file path."""
    profile    = state.get("student_profile", {})
    draft      = state.get("drafted_iep", {})
    compliance = state.get("compliance_report", {})
    iep_id     = state.get("iep_id", "unknown")
    styles     = get_styles()

    student_name = profile.get("student_name", "Student").replace(" ", "_")
    filename     = f"IEP_{student_name}_{iep_id[:8]}.pdf"
    output_path  = OUTPUT_DIR / filename

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize     = A4,
        rightMargin  = 2   * cm,
        leftMargin   = 2   * cm,
        topMargin    = 1.5 * cm,
        bottomMargin = 2   * cm,
        title        = f"IEP — {profile.get('student_name', '')}",
        author       = "Project SAMARTH",
    )

    story = []
    S     = styles   # shorthand

    # ════════════════════════════════════════════════════
    # COVER HEADER
    # ════════════════════════════════════════════════════
    header_data = [
        [Paragraph("INDIVIDUALIZED EDUCATION PROGRAM", S["doc_title"])],
        [Paragraph(
            "Project SAMARTH  ·  Compliant with RPwD Act 2016 &amp; NCTE/NCERT Guidelines  ·  India",
            S["doc_subtitle"],
        )],
    ]
    ht = Table(header_data, colWidths=[17 * cm])
    ht.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), NAVY),
        ("TOPPADDING",    (0,0),(-1,-1), 10),
        ("BOTTOMPADDING", (0,0),(-1,-1), 10),
    ]))
    story.append(ht)
    story.append(Spacer(1, 0.3 * cm))

    # ── Compliance badge ──────────────────────────────
    status_raw  = str(compliance.get("status", "")).lower()
    badge_color = {"compliant": GREEN, "partial": GOLD, "violation": RED}.get(status_raw, GREY)
    badge_label = status_raw.upper() if status_raw else "PENDING"

    # ════════════════════════════════════════════════════
    # SECTION 1 — BACKGROUND INFORMATION
    # ════════════════════════════════════════════════════
    story.append(section_header(1, "Background Information", S))
    story.append(Spacer(1, 0.2 * cm))

    # Student info table
    today = datetime.now().strftime("%d %B %Y")
    s1_data = [
        ["School / Agency",       profile.get("school_name", "N/A"),
         "Date of IEP Meeting",   today],
        ["Student Name",          profile.get("student_name", "N/A"),
         "Student ID",            iep_id[:10]],
        ["Age",                   str(profile.get("age", "N/A")),
         "Current Grade",         profile.get("grade", "N/A")],
        ["Disability Category",   profile.get("disability_category", "N/A"),
         "Severity",              str(profile.get("disability_severity", "N/A")).capitalize()],
        ["Dominant Language",     "English",
         "Interpreter Needed",    "No"],
        ["Compliance Status",     badge_label,
         "IEP ID",                iep_id[:14]],
    ]
    s1_table = Table(s1_data, colWidths=[3.5*cm, 5*cm, 3.5*cm, 5*cm])
    s1_table.setStyle(TableStyle([
        ("FONTNAME",      (0,0),(-1,-1), "Helvetica"),
        ("FONTNAME",      (0,0),(0,-1),  "Helvetica-Bold"),
        ("FONTNAME",      (2,0),(2,-1),  "Helvetica-Bold"),
        ("FONTSIZE",      (0,0),(-1,-1), 8.5),
        ("TEXTCOLOR",     (0,0),(0,-1),  NAVY),
        ("TEXTCOLOR",     (2,0),(2,-1),  NAVY),
        ("BACKGROUND",    (0,0),(-1,-1), LIGHT),
        ("BACKGROUND",    (0,0),(0,-1),  colors.HexColor("#d6eaf8")),
        ("BACKGROUND",    (2,0),(2,-1),  colors.HexColor("#d6eaf8")),
        ("ROWPADDING",    (0,0),(-1,-1), 5),
        ("GRID",          (0,0),(-1,-1), 0.4, colors.HexColor("#aed6f1")),
        ("TEXTCOLOR",     (1,5),(1,5),   badge_color),
        ("FONTNAME",      (1,5),(1,5),   "Helvetica-Bold"),
    ]))
    story.append(s1_table)
    story.append(Spacer(1, 0.15 * cm))

    # Background narrative
    bg = draft.get("background_info", "")
    if bg:
        story.extend(body_block(bg, S))
    story.append(Spacer(1, 0.3 * cm))

    # ── Legal citation ────────────────────────────────
    rpwd_refs = compliance.get("rpwd_relevant_sections", [])
    cite_text = (
        " | ".join(rpwd_refs[:2])
        if rpwd_refs
        else "RPwD Act 2016 — Sections 16 & 17 | NCERT Inclusive Education Guidelines"
    )
    story.append(Paragraph(f"⚖  Legal Basis: {cite_text}", S["cite"]))
    story.append(HRFlowable(width="100%", thickness=0.5, color=TEAL))
    story.append(Spacer(1, 0.3 * cm))

    # ════════════════════════════════════════════════════
    # SECTION 2 — PRESENT LEVELS OF PERFORMANCE
    # ════════════════════════════════════════════════════
    story.append(section_header(2, "Present Levels of Performance and Individual Needs", S))
    story.append(Spacer(1, 0.2 * cm))

    subsections_2 = [
        ("A — Academic / Educational Achievement & Learning Characteristics",
         draft.get("academic_performance", "")),
        ("B — Social Development",
         draft.get("social_development", "")),
        ("C — Physical Development",
         draft.get("physical_development", "")),
        ("D — Management Needs",
         draft.get("management_needs", "")),
    ]
    for sub_title, content in subsections_2:
        if content:
            story.append(Paragraph(sub_title, S["subsection"]))
            story.extend(body_block(content, S))
    story.append(Spacer(1, 0.3 * cm))

    # ════════════════════════════════════════════════════
    # SECTION 3 — LONG-TERM ADULT OUTCOMES
    # ════════════════════════════════════════════════════
    story.append(section_header(3, "Long-Term Adult Outcomes", S))
    story.append(Spacer(1, 0.2 * cm))
    story.extend(body_block(draft.get("long_term_outcomes", "N/A"), S))
    story.append(Spacer(1, 0.3 * cm))

    # ════════════════════════════════════════════════════
    # SECTION 4 — ANNUAL GOALS AND SHORT-TERM OBJECTIVES
    # ════════════════════════════════════════════════════
    story.append(section_header(4, "Measurable Annual Goals and Short-Term Instructional Objectives", S))
    story.append(Spacer(1, 0.2 * cm))
    story.extend(body_block(draft.get("annual_goals", ""), S))
    story.append(Spacer(1, 0.3 * cm))

    # ════════════════════════════════════════════════════
    # SECTION 5 — SPECIAL EDUCATION PROGRAMS & SERVICES
    # ════════════════════════════════════════════════════
    story.append(section_header(5, "Special Education Programs and Related Services / Program Modifications", S))
    story.append(Spacer(1, 0.2 * cm))
    story.extend(body_block(draft.get("special_education_services", ""), S))
    story.append(Spacer(1, 0.3 * cm))

    # ════════════════════════════════════════════════════
    # SECTION 6 — GENERAL EDUCATION PARTICIPATION
    # ════════════════════════════════════════════════════
    story.append(section_header(6, "Participation in General Education Classes, Non-Academic and Extracurricular Activities", S))
    story.append(Spacer(1, 0.2 * cm))
    story.extend(body_block(draft.get("general_education_participation", ""), S))
    story.append(Spacer(1, 0.3 * cm))

    # ════════════════════════════════════════════════════
    # SECTION 7 — PARTICIPATING AGENCIES
    # ════════════════════════════════════════════════════
    story.append(section_header(7, "Participating Agencies for Students Who Require Transition Services", S))
    story.append(Spacer(1, 0.2 * cm))
    story.extend(body_block(draft.get("participating_agencies", "N/A"), S))
    story.append(Spacer(1, 0.3 * cm))

    # ════════════════════════════════════════════════════
    # SECTION 8 — COORDINATED ACTIVITIES
    # ════════════════════════════════════════════════════
    story.append(section_header(8, "Coordinated Set of Activities Leading to Long-Term Adult Outcomes", S))
    story.append(Spacer(1, 0.2 * cm))
    story.extend(body_block(draft.get("coordinated_activities", ""), S))
    story.append(Spacer(1, 0.3 * cm))

    # ════════════════════════════════════════════════════
    # SECTION 9 — GRADUATION / COMPLETION INFORMATION
    # ════════════════════════════════════════════════════
    story.append(section_header(9, "Graduation / School Completion Information", S))
    story.append(Spacer(1, 0.2 * cm))
    story.extend(body_block(draft.get("graduation_info", ""), S))
    story.append(Spacer(1, 0.3 * cm))

    # ════════════════════════════════════════════════════
    # SECTION 10 — SUMMARY OF RECOMMENDATIONS
    # ════════════════════════════════════════════════════
    story.append(section_header(10, "Summary of Selected Recommendations", S))
    story.append(Spacer(1, 0.2 * cm))

    # Mandatory accommodations box
    mandatory = compliance.get("mandatory_accommodations", [])
    if mandatory:
        story.append(Paragraph("Legally Mandated Accommodations (RPwD Act 2016):", S["subsection"]))
        for item in mandatory:
            story.append(Paragraph(f"• {item}", S["body"]))
        story.append(Spacer(1, 0.15 * cm))

    story.extend(body_block(draft.get("recommendations_summary", ""), S))
    story.append(Spacer(1, 0.3 * cm))

    # ════════════════════════════════════════════════════
    # SECTION 11 — REPORTING PROGRESS TO PARENTS
    # ════════════════════════════════════════════════════
    story.append(section_header(11, "Reporting Progress to Parents", S))
    story.append(Spacer(1, 0.2 * cm))
    story.extend(body_block(draft.get("progress_reporting", ""), S))
    story.append(Spacer(1, 0.3 * cm))

    # ════════════════════════════════════════════════════
    # SIGNATURE BLOCK
    # ════════════════════════════════════════════════════
    story.append(PageBreak())
    sh = Table(
        [[Paragraph("  IEP Committee Signatures & Acknowledgement", S["section_title"])]],
        colWidths=[17 * cm],
    )
    sh.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), NAVY),
        ("TOPPADDING",    (0,0),(-1,-1), 7),
        ("BOTTOMPADDING", (0,0),(-1,-1), 7),
    ]))
    story.append(sh)
    story.append(Spacer(1, 0.4 * cm))

    sig_data = [
        ["Special Education Teacher",   "Parent / Guardian",          "Principal / Head Master"],
        ["\n\n\n_____________________", "\n\n\n_____________________", "\n\n\n_____________________"],
        ["Name: ___________________",   "Name: ___________________",  "Name: ___________________"],
        ["Designation: ___________",    "Relationship: ___________",  "School Seal:"],
        ["Date: ___________________",   "Date: ___________________",  "Date: ___________________"],
    ]
    sig_table = Table(sig_data, colWidths=[5.5*cm, 5.5*cm, 5.5*cm])
    sig_table.setStyle(TableStyle([
        ("FONTNAME",      (0,0),(-1,0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0,0),(-1,-1), 9),
        ("TEXTCOLOR",     (0,0),(-1,0),  NAVY),
        ("ALIGN",         (0,0),(-1,-1), "CENTER"),
        ("BACKGROUND",    (0,0),(-1,0),  LIGHT),
        ("GRID",          (0,0),(-1,-1), 0.3, GREY),
        ("TOPPADDING",    (0,0),(-1,-1), 5),
        ("BOTTOMPADDING", (0,0),(-1,-1), 5),
    ]))
    story.append(sig_table)
    story.append(Spacer(1, 0.5 * cm))

    # Parent rights notice
    story.append(Paragraph(
        "Parent/Guardian Rights: You have the right to receive a copy of this IEP, "
        "participate in all IEP meetings, request an independent evaluation, and file "
        "a complaint with the State Commissioner for Disabilities per RPwD Act 2016 Section 23.",
        S["cite"],
    ))

    # ════════════════════════════════════════════════════
    # FOOTER
    # ════════════════════════════════════════════════════
    story.append(Spacer(1, 0.8 * cm))
    story.append(HRFlowable(width="100%", thickness=0.3, color=GREY))
    story.append(Spacer(1, 0.15 * cm))
    story.append(Paragraph(
        f"Generated by Project SAMARTH  ·  Compliant with RPwD Act 2016 &amp; NCTE/NCERT Guidelines  ·  "
        f"{datetime.now().strftime('%d %B %Y %H:%M')}  ·  IEP ID: {iep_id}",
        S["footer"],
    ))

    doc.build(story)
    logger.info(f"  ✅ PDF generated: {output_path}")
    return str(output_path)


# ═══════════════════════════════════════════════════════
# LANGGRAPH NODE WRAPPER
# ═══════════════════════════════════════════════════════

def pdf_generator_node(state: IEPState) -> IEPState:
    """LangGraph node: PDF Generator"""
    logger.info("📄 PDF Generator: Rendering NASET-format IEP...")
    errors = list(state.get("error_log", []))

    if not state.get("drafted_iep"):
        errors.append("PDF Generator: No drafted IEP found.")
        return {**state, "workflow_status": WorkflowStatus.FAILED, "error_log": errors}

    try:
        pdf_path = generate_iep_pdf(state)
        return {
            **state,
            "pdf_output_path": pdf_path,
            "workflow_status": WorkflowStatus.COMPLETED,
            "current_node":    "pdf_generator",
            "error_log":       errors,
        }
    except Exception as e:
        errors.append(f"PDF Generator: {e}")
        logger.error(f"  ❌ PDF generation failed: {e}")
        return {**state, "workflow_status": WorkflowStatus.FAILED, "error_log": errors}