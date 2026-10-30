"""
pdf_generator/iep_pdf.py — Project SAMARTH

FIXES IN THIS VERSION:
  [1] Windows date crash — %-d strftime directive is Linux-only.
  [2] Filename built after student info is known (not "student").
  [3] Severity rendered from data; never blank "—".
  [4] Age guard flags implausibly low ages with "(verify)".
  [5] Empty Evaluation Procedures cells — trailing shared eval block is
      split off before objectives are parsed; all() not any() for the
      per-row table.
  [6] NEW — SECTION 1 USES STRUCTURED DATA, NOT REGEX OVER PROSE.
      Section 1 fields (school, grade, age, disability, severity) used to
      be regex-parsed OUT OF the drafting agent's background_info prose.
      That kept breaking whenever the model changed how it separated
      fields ("|", ";", "." ...) — e.g. "Orange Sables Elementary. Date of
      IEP Meeting: April 12" landing in the School cell.
      But those values already exist as clean structured data in
      student_profile, produced by the extractor. Re-parsing them from
      prose was reading a copy of data we already held. The profile is
      now the source of truth; regex is only a fallback for a field the
      profile genuinely lacks, and every regex value is validated.
"""

import ast
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    CondPageBreak, HRFlowable, KeepTogether,
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

logger = logging.getLogger(__name__)

# ── Palette ──────────────────────────────────────────────────────────────
DARK_NAVY = colors.HexColor("#0d1b2a")
NAVY      = colors.HexColor("#1b3a5c")
STEEL     = colors.HexColor("#2c4f7c")
OFF_WHITE = colors.HexColor("#f9fafb")
MID_GRAY  = colors.HexColor("#6b7280")
BORDER    = colors.HexColor("#d1d5db")
BLACK     = colors.HexColor("#111827")
WHITE     = colors.white

PAGE_W, PAGE_H = A4
MARGIN    = 2.0 * cm
CONTENT_W = PAGE_W - 2 * MARGIN

_BG_SKIP = re.compile(
    r"""^(
        Student\s+(?:Name|ID)
        |School(?:\s*/\s*Agency)?
        |(?:Current\s+)?Grade
        |\bAge\b
        |Date\s+of\s+(?:IEP|Birth|Initiation|Evaluation|Services|Meeting)
        |Disability(?:\s+\w+)*
        |Dominant\s+Language
        |Interpreter\s+Needed
        |Parent\s*/?\s*Guardian
        |Contact\s+Information
        |Medical\s+Alerts?
    )[:\s]""",
    re.VERBOSE | re.IGNORECASE,
)

_TRANSITION_WORDS = [
    'transition', 'at age 14', 'age of 14', 'reaches 14', 'reach age',
    'below 14', 'above 14', 'adult outcome', 'long-term', 'post-school',
    'planning will', 'will be developed', 'commence at',
]


# ── Cross-platform date helpers ───────────────────────────────────────────

def _format_date_crossplatform(dt: datetime = None) -> str:
    """'26 Jul 2026 12:15 IST' — %-d is Linux-only and crashes on Windows.
    India time by default; the server itself may run on UTC."""
    from agents.model_config import LOCAL_TZ_LABEL, now_local
    if dt is None:
        dt = now_local()
    return f"{dt.day} {dt.strftime('%b %Y')} {dt.strftime('%H:%M')} {LOCAL_TZ_LABEL}"


def _format_iep_date(dt=None) -> str:
    """'26 July 2026' for the IEP meeting date field (date or datetime)."""
    if dt is None:
        from agents.model_config import current_date
        dt = current_date()
    return f"{dt.day} {dt.strftime('%B')} {dt.strftime('%Y')}"


def _meeting_date(state: dict):
    """
    The IEP's meeting date as SAVED with the IEP, so rebuilding the PDF later
    (review, finalize, download) never changes it. Falls back to today.
    """
    from datetime import date as _date
    try:
        return _date.fromisoformat(str(state.get("meeting_date") or ""))
    except ValueError:
        return None


# ── Text helpers ──────────────────────────────────────────────────────────

def _strip_md(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"\*(.+?)\*",     r"\1", text, flags=re.DOTALL)
    text = re.sub(r"__(.+?)__",     r"\1", text, flags=re.DOTALL)
    text = re.sub(r"_(.+?)_",       r"\1", text, flags=re.DOTALL)
    text = re.sub(r"^#{1,6}\s+",    "",    text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-*]\s+",   "• ",  text, flags=re.MULTILINE)
    return text.strip()


def _parse_structured(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return value
    if not isinstance(value, str):
        return value
    for loader in (json.loads, ast.literal_eval):
        try:
            return loader(value.strip())
        except Exception:
            pass
    return value


def _to_clean_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return _strip_md(value)
    if isinstance(value, list):
        return _strip_md("\n".join(str(i) for i in value))
    if isinstance(value, dict):
        return _strip_md("\n".join(f"{k}: {v}" for k, v in value.items()))
    return _strip_md(str(value))


def _fix_compliance(status: Any) -> str:
    if not status:
        return "Unknown"
    if hasattr(status, "value"):
        status = str(status.value)
    elif hasattr(status, "name"):
        status = status.name
    upper = str(status).upper()
    if "NON" in upper or "NOT_COMPLIANT" in upper:
        return "Non-Compliant"
    if "PARTIAL" in upper:
        return "Partially Compliant"
    if "COMPLIANT" in upper or "FULL" in upper:
        return "Fully Compliant"
    return str(status).split(".")[-1].replace("_", " ").title()


def _strip_section_prefix(text: str) -> str:
    if not text:
        return text
    lines = text.strip().split("\n")
    while lines and re.match(r"^\s*Section\s+\d+[\s:\-]", lines[0], re.IGNORECASE):
        lines.pop(0)
    return "\n".join(lines).strip()


def _sanitize_filename(name: str) -> str:
    safe = re.sub(r"[^\w\s\-]", "", name)
    safe = re.sub(r"\s+", "_", safe.strip())
    return safe if safe else "student"


def _clean(value) -> str:
    """Return a stripped string, or '' for None / placeholder values."""
    if value is None:
        return ""
    s = str(value).strip()
    return "" if s.lower() in ("", "none", "n/a", "—", "-", "not specified") else s


# ── Regex fallback extraction (used ONLY when the profile lacks a field) ──

def _find_age(bg: str, iep: dict) -> str:
    direct_patterns = [
        r'\bAge[:\s]+(\d{1,2})\b',
        r'\b(\d{1,2})\s+years\s+(?:of\s+age|old)\b',
        r'\b(\d{1,2})[- ]year[s]?[- ]old\b',
        r'\baged?\s+(\d{1,2})\b',
    ]
    for pat in direct_patterns:
        m = re.search(pat, bg, re.IGNORECASE)
        if m and 3 <= int(m.group(1)) <= 25:
            return m.group(1)

    for section_text in (iep or {}).values():
        if not isinstance(section_text, str):
            continue
        for sentence in re.split(r'[.\n]', section_text):
            s_lower = sentence.lower()
            if any(kw in s_lower for kw in _TRANSITION_WORDS):
                continue
            if any(kw in s_lower for kw in ['grade', 'term', 'goal', 'step', 'section']):
                continue
            for pat in direct_patterns:
                m = re.search(pat, sentence, re.IGNORECASE)
                if m and 3 <= int(m.group(1)) <= 25:
                    return m.group(1)
    return ""


def _is_valid_field_value(key: str, value: str) -> bool:
    """
    Reject regex captures that clearly grabbed the wrong text:
    contact details, run-on captures that swallowed another field label,
    names with digits, over-long grades.
    """
    if not value or len(value) > 80:
        return False
    if "@" in value or re.search(r"\+?\d{10,}", value):
        return False
    # A second "Label:" inside the value means it ran into the next field
    if re.search(r"\b[A-Z][A-Za-z /]{2,30}:", value):
        return False
    if key == "grade" and len(value) > 20:
        return False
    if key == "name" and (any(ch.isdigit() for ch in value) or len(value.split()) > 5):
        return False
    return True


def _extract_student_from_background(bg: str, iep: dict) -> dict:
    """
    Fallback only. Each value stops at a field separator — newline, pipe,
    semicolon, bracket, comma, or a full stop followed by a space — and is
    then validated before use.
    """
    result: dict = {}
    STOP = r"[^\n|;(,]+?"
    END  = r"(?=\s*(?:\.\s|\n|\||;|,|\(|$))"

    patterns = {
        "name":       rf"Student\s+Name\s*[:\-]\s*({STOP}){END}",
        "school":     rf"School(?:\s*/\s*Agency)?\s*[:\-]\s*({STOP}){END}",
        "grade":      rf"(?:Current\s+)?Grade\s*[:\-]\s*({STOP}){END}",
        "disability": rf"Disability\s+(?:Category|Classification)\s*[:\-]\s*({STOP}){END}",
    }
    for key, pat in patterns.items():
        m = re.search(pat, bg, re.IGNORECASE)
        if m:
            value = m.group(1).strip().rstrip(".,;:|()-").strip()
            if _is_valid_field_value(key, value):
                result[key] = value

    sev = re.search(r"\b(Mild|Moderate|Severe)\b", bg, re.IGNORECASE)
    if sev:
        result["severity"] = sev.group(1).capitalize()

    result["age"] = _find_age(bg, iep)
    return result


def _build_student_record(profile: dict, drafted: dict) -> dict:
    """
    [6] Assemble Section 1 fields with the STRUCTURED PROFILE AS SOURCE OF
    TRUTH. Regex over the drafted prose is consulted only for a field the
    profile genuinely lacks.
    """
    parsed = _extract_student_from_background(drafted.get("background_info", ""), drafted)

    def pick(profile_key: str, parsed_key: str) -> str:
        return _clean(profile.get(profile_key)) or _clean(parsed.get(parsed_key))

    return {
        "name":       pick("student_name",        "name"),
        "school":     pick("school_name",         "school"),
        "grade":      pick("grade",               "grade"),
        "disability": pick("disability_category", "disability"),
        "severity":   pick("disability_severity", "severity"),
        "age":        pick("age",                 "age"),
        "language":   _clean(profile.get("dominant_language")) or "English",
    }


def _clean_background(text: str) -> str:
    if not text:
        return ""
    text = _strip_section_prefix(text)
    filtered = [
        line for line in text.split("\n")
        if line.strip() and not _BG_SKIP.match(line.strip())
    ]
    return "\n".join(filtered).strip()


# ── Styles ────────────────────────────────────────────────────────────────

def _build_styles() -> dict:
    return {
        "doc_title": ParagraphStyle("doc_title",
            fontSize=15, fontName="Helvetica-Bold",
            textColor=WHITE, alignment=TA_CENTER, spaceAfter=3),
        "doc_sub": ParagraphStyle("doc_sub",
            fontSize=8, fontName="Helvetica",
            textColor=colors.HexColor("#a5b4c8"),
            alignment=TA_CENTER, spaceAfter=2),
        "section_hdr": ParagraphStyle("section_hdr",
            fontSize=10, fontName="Helvetica-Bold", textColor=WHITE),
        "sub_hdr": ParagraphStyle("sub_hdr",
            fontSize=10, fontName="Helvetica-Bold",
            textColor=NAVY, spaceBefore=10, spaceAfter=4,
            keepWithNext=1),
        "body": ParagraphStyle("body",
            fontSize=9, fontName="Helvetica",
            textColor=BLACK, leading=14, spaceAfter=5,
            alignment=TA_JUSTIFY),
        "body_sm": ParagraphStyle("body_sm",
            fontSize=8, fontName="Helvetica",
            textColor=BLACK, leading=12, spaceAfter=4),
        "kv_label": ParagraphStyle("kv_label",
            fontSize=8, fontName="Helvetica-Bold", textColor=MID_GRAY),
        "kv_value": ParagraphStyle("kv_value",
            fontSize=9, fontName="Helvetica", textColor=BLACK),
        "tbl_hdr": ParagraphStyle("tbl_hdr",
            fontSize=8, fontName="Helvetica-Bold",
            textColor=WHITE, alignment=TA_CENTER),
        "tbl_cell": ParagraphStyle("tbl_cell",
            fontSize=8, fontName="Helvetica",
            textColor=BLACK, leading=11),
        "goal_num": ParagraphStyle("goal_num",
            fontSize=9, fontName="Helvetica-Bold",
            textColor=NAVY, spaceBefore=8, spaceAfter=3,
            keepWithNext=1),
        "note": ParagraphStyle("note",
            fontSize=8, fontName="Helvetica",
            textColor=MID_GRAY, leading=11, spaceAfter=4),
        "footer": ParagraphStyle("footer",
            fontSize=7, fontName="Helvetica",
            textColor=MID_GRAY, alignment=TA_CENTER),
    }


# ── Layout primitives ─────────────────────────────────────────────────────

def _section_block(number: str, title: str, styles: dict) -> list:
    tbl = Table(
        [[Paragraph(f"Section {number} — {title}", styles["section_hdr"])]],
        colWidths=[CONTENT_W],
    )
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), NAVY),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING",   (0, 0), (-1, -1), 12),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 12),
    ]))
    return [CondPageBreak(5 * cm), Spacer(1, 10), tbl, Spacer(1, 8)]


def _body_paras(text: Any, styles: dict) -> list:
    raw   = _to_clean_str(text)
    clean = _strip_section_prefix(raw)
    if not clean:
        return []
    return [
        Paragraph(line.strip(), styles["body"])
        for line in clean.split("\n") if line.strip()
    ]


def _kv_table(rows: list, styles: dict) -> Table:
    data = [
        [Paragraph(k, styles["kv_label"]),
         Paragraph(_strip_md(str(v)), styles["kv_value"])]
        for k, v in rows
    ]
    tbl = Table(data, colWidths=[CONTENT_W * 0.32, CONTENT_W * 0.68])
    tbl.setStyle(TableStyle([
        ("GRID",           (0, 0), (-1, -1), 0.5, BORDER),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [WHITE, OFF_WHITE]),
        ("TOPPADDING",     (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 5),
        ("LEFTPADDING",    (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",   (0, 0), (-1, -1), 8),
        ("VALIGN",         (0, 0), (-1, -1), "TOP"),
    ]))
    return tbl


# ── Goal table builders ───────────────────────────────────────────────────

def _goals_table_shared(objectives: list, procedures: list, schedule: str, styles: dict) -> Table:
    """Procedures shown once for the whole goal — correct NASET format."""
    proc_text  = _strip_md("\n".join(str(p) for p in procedures) if procedures else "—")
    sched_text = _strip_md(str(schedule) if schedule else "Quarterly")

    header = [
        Paragraph("Short-term Instructional Objective", styles["tbl_hdr"]),
        Paragraph("Evaluation Procedures",              styles["tbl_hdr"]),
        Paragraph("Evaluation Schedule",                styles["tbl_hdr"]),
    ]
    data = [header]
    for j, obj in enumerate(objectives):
        data.append([
            Paragraph(_strip_md(str(obj)), styles["tbl_cell"]),
            Paragraph(proc_text,  styles["tbl_cell"]) if j == 0 else Paragraph("", styles["tbl_cell"]),
            Paragraph(sched_text, styles["tbl_cell"]) if j == 0 else Paragraph("", styles["tbl_cell"]),
        ])

    widths = [CONTENT_W * 0.46, CONTENT_W * 0.34, CONTENT_W * 0.20]
    tbl = Table(data, colWidths=widths, repeatRows=1, splitByRow=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",     (0, 0), (-1, 0),  STEEL),
        ("TEXTCOLOR",      (0, 0), (-1, 0),  WHITE),
        ("GRID",           (0, 0), (-1, -1), 0.5, BORDER),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, OFF_WHITE]),
        ("TOPPADDING",     (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 5),
        ("LEFTPADDING",    (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",   (0, 0), (-1, -1), 6),
        ("VALIGN",         (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND",     (1, 2), (2, -1),  colors.HexColor("#f0f4f8")),
    ]))
    return tbl


def _goals_table_per_row(parsed_objs: list, styles: dict) -> Table:
    """Only used when EVERY objective carries its own procedures."""
    header = [
        Paragraph("Short-term Instructional Objective", styles["tbl_hdr"]),
        Paragraph("Evaluation Procedures",              styles["tbl_hdr"]),
        Paragraph("Evaluation Schedule",                styles["tbl_hdr"]),
    ]
    rows = [[
        Paragraph(_strip_md(obj_text),            styles["tbl_cell"]),
        Paragraph(_strip_md(proc or "—"),          styles["tbl_cell"]),
        Paragraph(_strip_md(sched or "Quarterly"), styles["tbl_cell"]),
    ] for obj_text, proc, sched in parsed_objs]

    widths = [CONTENT_W * 0.46, CONTENT_W * 0.34, CONTENT_W * 0.20]
    tbl = Table([header] + rows, colWidths=widths, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",     (0, 0), (-1, 0),  STEEL),
        ("TEXTCOLOR",      (0, 0), (-1, 0),  WHITE),
        ("GRID",           (0, 0), (-1, -1), 0.5, BORDER),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, OFF_WHITE]),
        ("TOPPADDING",     (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 5),
        ("LEFTPADDING",    (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",   (0, 0), (-1, -1), 6),
        ("VALIGN",         (0, 0), (-1, -1), "TOP"),
    ]))
    return tbl


# ── Goal text parsers ─────────────────────────────────────────────────────

def _split_inline_eval(obj_text: str) -> tuple:
    obj_text = obj_text.strip()

    if "|" in obj_text:
        parts = [p.strip() for p in obj_text.split("|")]
        clean = _strip_md(parts[0])
        proc, sched = "", ""
        for part in parts[1:]:
            if re.match(r"Evaluation Procedures?:", part, re.IGNORECASE):
                proc = re.sub(r"^Evaluation Procedures?:\s*", "", part, flags=re.IGNORECASE).strip()
            elif re.match(r"Evaluation Schedule:", part, re.IGNORECASE):
                sched = re.sub(r"^Evaluation Schedule:\s*", "", part, flags=re.IGNORECASE).strip()
        return clean, proc, sched

    ep_m = re.search(r'[.!?]\s+Evaluation\s+Procedures?:\s+', obj_text, re.IGNORECASE)
    if ep_m:
        clean     = _strip_md(obj_text[:ep_m.start() + 1])
        eval_part = obj_text[ep_m.start() + 1:]
        proc_m  = re.search(
            r'Evaluation\s+Procedures?:\s*(.+?)(?=\s+Evaluation\s+Schedule:|$)',
            eval_part, re.IGNORECASE | re.DOTALL)
        sched_m = re.search(r'Evaluation\s+Schedule:\s*(.+?)\.?\s*$', eval_part, re.IGNORECASE)
        proc  = _strip_md(proc_m.group(1).strip()) if proc_m else ""
        sched = _strip_md(sched_m.group(1).strip().rstrip(".")) if sched_m else ""
        return clean, proc, sched

    return _strip_md(obj_text), "", ""


def _normalize_goals_text(text: str) -> str:
    counter = [0]
    def _replacer(m):
        counter[0] += 1
        return f"\nAnnual Goal {counter[0]}:\n"
    return re.sub(r'\n?Annual\s+Goal(?:\s+\d+)?[:\.]?\s*\n?',
                  _replacer, text, flags=re.IGNORECASE)


def _parse_goals_narrative(text: str) -> list:
    text = _strip_section_prefix(text)
    text = _normalize_goals_text(text)

    chunks = re.split(r'\n?Annual\s+Goal\s+\d+[:\.]?\s*\n?', text, flags=re.IGNORECASE)
    goals = []

    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        chunk = re.sub(r'^Annual\s+Goal(?:\s+\d+)?[:\.]?\s*', '', chunk, flags=re.IGNORECASE).strip()
        if len(chunk) < 30 or re.match(r'^Section\s+\d+', chunk, re.IGNORECASE):
            continue

        halves = re.split(r'\n\s*Short-term\s+(?:Instructional\s+)?Objectives?:?\s*\n',
                          chunk, maxsplit=1, flags=re.IGNORECASE)
        goal_text = _strip_md(halves[0].strip())
        if not goal_text or len(goal_text) < 20:
            continue

        objectives, procedures, schedule, per_obj_parsed = [], [], "Quarterly", []

        if len(halves) > 1:
            obj_block = halves[1]

            next_goal = re.search(r'\nAnnual\s+Goal\s+\d+[:\.]', obj_block, re.IGNORECASE)
            if next_goal:
                obj_block = obj_block[:next_goal.start()]

            # Split off the trailing shared eval block so the last objective
            # doesn't swallow it
            shared_eval_match = re.search(
                r'\n\s*Evaluation\s+(?:Procedures?|Schedule)\s*:', obj_block, re.IGNORECASE)
            shared_eval_text = ""
            if shared_eval_match:
                shared_eval_text = obj_block[shared_eval_match.start():]
                obj_block        = obj_block[:shared_eval_match.start()]

            raw_items = re.findall(r'^\s*\d+\.\s+(.+?)(?=\n\s*\d+\.|\Z)',
                                   obj_block, flags=re.MULTILINE | re.DOTALL)
            for item in raw_items:
                obj_c, p, s = _split_inline_eval(item.strip())
                per_obj_parsed.append((obj_c, p, s))
                objectives.append(obj_c)
                if p and p not in procedures:
                    procedures.append(p)
                if s:
                    schedule = s

            if shared_eval_text:
                ep_m = re.search(
                    r'Evaluation\s+Procedures?\s*:\s*(.+?)(?=\n\s*Evaluation\s+Schedule\s*:|\Z)',
                    shared_eval_text, re.IGNORECASE | re.DOTALL)
                if ep_m:
                    proc_text = _strip_md(ep_m.group(1).strip().rstrip(".\n"))
                    if proc_text and proc_text not in procedures:
                        procedures.append(proc_text)
                es_m = re.search(r'Evaluation\s+Schedule\s*:\s*(.+?)(?:\n|\Z)',
                                 shared_eval_text, re.IGNORECASE)
                if es_m:
                    schedule = _strip_md(es_m.group(1).strip().rstrip("."))

        goals.append({
            "goal_text": goal_text, "objectives": objectives,
            "procedures": procedures, "schedule": schedule,
            "per_obj_parsed": per_obj_parsed,
        })

    return goals


# ── Section renderers ─────────────────────────────────────────────────────

def _render_section1(student: dict, iep_id: str, compliance_status: Any, styles: dict,
                     student_code: str = "", meeting_date=None) -> list:
    age_raw   = str(student.get("age", "")).strip()
    grade_raw = str(student.get("grade", "")).strip()
    age_display = age_raw or "—"
    if age_raw and grade_raw:
        try:
            age_int   = int(re.search(r'\d+', age_raw).group())
            grade_int = int(re.search(r'\d+', grade_raw).group())
            if age_int < (grade_int + 4):
                age_display = f"{age_raw} (verify)"
        except (AttributeError, ValueError):
            pass

    rows = [
        ("School / Agency",      student.get("school") or "—"),
        ("Date of IEP Meeting",  _format_iep_date(meeting_date)),
        ("Student Name",         student.get("name") or "—"),
        # The registered student's ID when the IEP is filed under one
        ("Student ID",           student_code or iep_id[:8].upper()),
        ("Age",                  age_display),
        ("Current Grade",        student.get("grade") or "—"),
        ("Disability Category",  student.get("disability") or "—"),
        ("Severity",             student.get("severity") or "Not Specified"),
        ("Dominant Language",    student.get("language") or "English"),
        ("Interpreter Needed",   "No"),
        ("Compliance Status",    _fix_compliance(compliance_status)),
        ("IEP ID",               iep_id),
    ]
    return [_kv_table(rows, styles), Spacer(1, 10)]


def _render_section2(iep: dict, styles: dict) -> list:
    story = []
    for label, key in [
        ("A — Academic / Educational Achievement & Learning Characteristics", "academic_performance"),
        ("B — Social Development",   "social_development"),
        ("C — Physical Development", "physical_development"),
        ("D — Management Needs",     "management_needs"),
    ]:
        content = iep.get(key, "")
        if not content:
            continue
        story.append(Paragraph(label, styles["sub_hdr"]))
        story.extend(_body_paras(content, styles))
        story.append(Spacer(1, 6))
    return story


def _render_section4(iep: dict, styles: dict) -> list:
    story = []
    raw   = iep.get("annual_goals", "")
    if not raw:
        return [Paragraph("No annual goals drafted.", styles["note"])]

    goals = _parse_goals_narrative(_to_clean_str(raw))
    if not goals:
        return _body_paras(raw, styles)

    for i, g in enumerate(goals, 1):
        if len(g["goal_text"]) < 40 or re.match(r'^Section\s+\d+', g["goal_text"], re.IGNORECASE):
            continue
        story.append(Paragraph(f"Annual Goal {i}", styles["goal_num"]))
        story.append(Paragraph(g["goal_text"], styles["body"]))
        story.append(Spacer(1, 4))

        if not g["objectives"]:
            story.append(Paragraph("Short-term objectives to be confirmed with IEP team.", styles["note"]))
        elif g["per_obj_parsed"] and all(p for _, p, _ in g["per_obj_parsed"]):
            story.append(_goals_table_per_row(g["per_obj_parsed"], styles))
        else:
            story.append(_goals_table_shared(g["objectives"], g["procedures"], g["schedule"], styles))
        story.append(Spacer(1, 8))
    return story


def _render_section11(iep: dict, styles: dict) -> list:
    story = _body_paras(iep.get("progress_reporting", ""), styles)
    story += [
        Spacer(1, 20),
        HRFlowable(width=CONTENT_W, thickness=0.5, color=BORDER),
        Spacer(1, 12),
        Paragraph("IEP Committee Signatures & Acknowledgement", styles["sub_hdr"]),
    ]
    sig_data = [
        [Paragraph("Special Education Teacher", styles["kv_label"]),
         Paragraph("Parent / Guardian",         styles["kv_label"]),
         Paragraph("Principal / Head Master",   styles["kv_label"])],
        [Paragraph("_____________________", styles["body"])] * 3,
        [Paragraph("Name: _______________", styles["body_sm"])] * 3,
        [Paragraph("Designation: ________", styles["body_sm"]),
         Paragraph("Relationship: _______", styles["body_sm"]),
         Paragraph("School Seal: ",         styles["body_sm"])],
        [Paragraph("Date: _______________", styles["body_sm"])] * 3,
    ]
    sig_tbl = Table(sig_data, colWidths=[CONTENT_W / 3] * 3)
    sig_tbl.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(sig_tbl)
    story.append(Spacer(1, 12))
    story.append(Paragraph(
        "Parent/Guardian Rights: You have the right to receive a copy of this IEP, "
        "participate in all IEP meetings, request an independent evaluation, and file "
        "a complaint with the State Commissioner for Disabilities per RPwD Act 2016 Section 23.",
        styles["note"],
    ))
    return story


# ── Header / Footer ───────────────────────────────────────────────────────

def _make_header_footer(iep_id: str, student_name: str):
    from reportlab.lib.units import cm as _cm
    # Kept short: the left and right footer texts share one line. It must not
    # claim compliance — Section 1 states the actual compliance status.
    footer_text = (
        f"SAMARTH · AI-assisted IEP, educator review required · "
        f"{_format_date_crossplatform()}"
    )

    def _draw(canvas, doc):
        canvas.saveState()
        page_w, page_h = A4
        canvas.setFillColor(DARK_NAVY)
        canvas.rect(0, page_h - 1.6 * _cm, page_w, 1.6 * _cm, fill=1, stroke=0)
        canvas.setFillColor(WHITE)
        # Project name as the title; the document type stays in the small
        # line below so readers (parents, schools) know what this is.
        canvas.setFont("Helvetica-Bold", 14)
        canvas.drawCentredString(page_w / 2, page_h - 0.95 * _cm, "SAMARTH")
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#a5b4c8"))
        canvas.drawCentredString(page_w / 2, page_h - 1.4 * _cm,
            "Individualized Education Program (IEP) · RPwD Act 2016 & NCTE/NCERT Guidelines · India")
        canvas.setFillColor(colors.HexColor("#f1f5f9"))
        canvas.rect(0, 0, page_w, 1.2 * _cm, fill=1, stroke=0)
        canvas.setFillColor(MID_GRAY)
        canvas.setFont("Helvetica", 7)
        canvas.drawString(MARGIN, 0.45 * _cm, footer_text)
        canvas.drawRightString(page_w - MARGIN, 0.45 * _cm, f"IEP {str(iep_id)[:8]}  ·  Page {doc.page}")
        canvas.restoreState()

    return _draw


# ── Main entry point ──────────────────────────────────────────────────────

def generate_iep_pdf(state: dict, output_dir: str = "outputs") -> str:
    """Build the complete NASET IEP PDF and return the output file path."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    iep_id     = state.get("student_id", state.get("iep_id", "unknown"))
    profile    = state.get("student_profile", {}) or {}
    drafted    = state.get("drafted_iep", {}) or {}
    compliance = state.get("compliance_report", {}) or {}

    # [6] Structured profile first, regex over prose only as a fallback
    student      = _build_student_record(profile, drafted)
    student_name = student.get("name", "").strip()

    if student_name:
        filename = f"IEP_{_sanitize_filename(student_name)}_{iep_id[:8]}.pdf"
    else:
        filename = f"IEP_student_{iep_id[:8]}.pdf"
        logger.warning("generate_iep_pdf: student name unavailable — using fallback filename.")

    output_path = str(Path(output_dir) / filename)
    styles      = _build_styles()

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=2.2 * cm, bottomMargin=1.6 * cm,
        title=f"SAMARTH IEP — {student_name or iep_id}", author="SAMARTH",
    )

    on_page = _make_header_footer(iep_id, student_name)
    body    = lambda key: _body_paras(drafted.get(key, ""), styles)

    story = []
    story += _section_block("1",  "Background Information", styles)
    story += _render_section1(student, iep_id, compliance.get("status", "unknown"), styles,
                              student_code=state.get("student_code", ""),
                              meeting_date=_meeting_date(state))
    story += _section_block("2",  "Present Levels of Performance and Individual Needs", styles)
    story += _render_section2(drafted, styles)
    story += _section_block("3",  "Long-Term Adult Outcomes", styles)
    story += body("long_term_outcomes")
    story += _section_block("4",  "Measurable Annual Goals and Short-Term Instructional Objectives", styles)
    story += _render_section4(drafted, styles)
    story += _section_block("5",  "Special Education Programs and Related Services / Program Modifications", styles)
    story += body("special_education_services")
    story += _section_block("6",  "Participation in General Education Classes, Non-Academic and Extracurricular Activities", styles)
    story += body("general_education_participation")
    story += _section_block("7",  "Participating Agencies for Students Who Require Transition Services", styles)
    story += body("participating_agencies")
    story += _section_block("8",  "Coordinated Set of Activities Leading to Long-Term Adult Outcomes", styles)
    story += body("coordinated_activities")
    story += _section_block("9",  "Graduation / School Completion Information", styles)
    story += body("graduation_info")
    story += _section_block("10", "Summary of Selected Recommendations", styles)
    story += body("recommendations_summary")
    story += _section_block("11", "Reporting Progress to Parents", styles)
    story += _render_section11(drafted, styles)

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    logger.info(f"✅ PDF generated: {output_path}")
    return output_path


# ── LangGraph node wrapper ────────────────────────────────────────────────

def pdf_generator_node(state: dict) -> dict:
    """LangGraph node: PDF Generator"""
    from agents.state import WorkflowStatus

    logger.info("📄 PDF Generator: Building IEP document...")
    errors = list(state.get("error_log", []))

    if not state.get("drafted_iep"):
        errors.append("PDF Generator: No drafted IEP found in state.")
        return {**state, "workflow_status": WorkflowStatus.FAILED, "error_log": errors}

    try:
        output_path = generate_iep_pdf(state, output_dir="outputs")
        logger.info(f"  ✅ PDF saved: {output_path}")
        return {
            **state,
            "pdf_output_path": output_path,
            "workflow_status": WorkflowStatus.COMPLETED,
            "current_node":    "pdf_generator",
            "error_log":       errors,
        }
    except Exception as e:
        errors.append(f"PDF Generator: {e}")
        logger.error(f"  ❌ PDF generation failed: {e}")
        return {**state, "workflow_status": WorkflowStatus.FAILED, "error_log": errors}