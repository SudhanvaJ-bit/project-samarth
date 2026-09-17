"""
pdf_generator/iep_pdf.py — Project SAMARTH

FIXES IN THIS VERSION:
  [1] Windows date crash — %-d strftime directive is Linux-only.
      Replaced with cross-platform equivalent throughout.
  [2] Filename fix — built after student info extracted (not "student")
  [3] Severity — rendered from extracted data, not blank "—"
  [4] Age guard — flags implausibly low ages with "(verify)"
  [5] EMPTY EVALUATION PROCEDURES CELLS — the last objective was
      swallowing the "Evaluation Procedures:" line that followed it,
      so only row 3 had procedures and rows 1-2 showed "—".
      Two-part fix:
        (a) _parse_goals_narrative() now truncates the objective block
            before any trailing "Evaluation Procedures:" line
        (b) _render_section4() uses all() not any() so the per-row table
            is only used when EVERY objective genuinely has its own
            procedures; otherwise falls back to the shared table
            (which is correct NASET format anyway)
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
    """
    [FIX 1] Return "26 Jul 2026 12:15" — works on Windows and Linux.
    %-d (no leading zero) is Linux-only and crashes on Windows.
    """
    if dt is None:
        dt = datetime.today()
    day        = str(dt.day)
    month_year = dt.strftime("%b %Y")
    time_str   = dt.strftime("%H:%M")
    return f"{day} {month_year} {time_str}"


def _format_iep_date(dt: datetime = None) -> str:
    """Return "26 July 2026" for the IEP meeting date field."""
    if dt is None:
        dt = datetime.today()
    return f"{dt.day} {dt.strftime('%B')} {dt.strftime('%Y')}"


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


# ── Student info extraction ───────────────────────────────────────────────

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

    all_text = bg + " " + " ".join(
        str(v) for v in (iep or {}).values() if isinstance(v, str))
    for yr_m in re.finditer(r'\b(19|20)(\d{2})\b', all_text):
        year   = int(yr_m.group(0))
        approx = datetime.now().year - year
        if 3 <= approx <= 25:
            return str(approx)

    return ""


def _extract_student_from_background(bg: str, iep: dict) -> dict:
    """
    Parse student fields from background_info.

    FIX: patterns now stop at '|' (pipe), ';' (semicolon), and '('
    in addition to newline and comma. The drafting agent commonly emits
    a single pipe-delimited line like:
        Student Name: Mary Jones | Grade: 2 | Age: 8 years | School: ...
    Previously the greedy patterns swallowed everything after the label,
    dumping phone numbers and emails into the Disability Category cell.
    """
    result: dict = {}

    # Character class that terminates a field value.
    # Stops at: newline, pipe, semicolon, open paren, comma
    STOP = r"[^\n|;(,]+"

    patterns = {
        "name":       rf"Student\s+Name\s*[:\-]\s*({STOP})",
        "school":     rf"School(?:\s*/\s*Agency)?\s*[:\-]\s*({STOP})",
        "grade":      rf"(?:Current\s+)?Grade\s*[:\-]\s*({STOP})",
        "disability": rf"Disability\s+(?:Category|Classification)\s*[:\-]\s*({STOP})",
        "severity":   r"\b(Mild|Moderate|Severe)\b",
    }

    for key, pat in patterns.items():
        m = re.search(pat, bg, re.IGNORECASE)
        if m:
            value = m.group(1).strip().rstrip(".,;:|()-").strip()
            # Reject values that are obviously wrong
            if _is_valid_field_value(key, value):
                result[key] = value

    result["age"] = _find_age(bg, iep)
    return result


def _is_valid_field_value(key: str, value: str) -> bool:
    """
    Reject field values that clearly captured the wrong text.
    Guards against phone numbers, emails, and runaway captures.
    """
    if not value or len(value) > 120:
        return False

    lowered = value.lower()

    # Never accept contact details in any field
    if "@" in value or re.search(r"\+?\d{10,}", value):
        return False

    # Grade should be short and contain a digit or roman numeral
    if key == "grade":
        if len(value) > 25:
            return False

    # Name should be 2-4 words, no digits
    if key == "name":
        if any(ch.isdigit() for ch in value):
            return False
        if len(value.split()) > 5:
            return False

    # Disability should not contain contact/ID noise
    if key == "disability":
        if any(tok in lowered for tok in ("email", "phone", "student id", "dob")):
            return False

    return True


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


def _std_table(headers: list, rows: list, col_widths: list, styles: dict) -> Table:
    data = [[Paragraph(h, styles["tbl_hdr"]) for h in headers]] + rows
    tbl  = Table(data, colWidths=col_widths, repeatRows=1)
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


# ── Goal table builders ───────────────────────────────────────────────────

def _goals_table_shared(objectives: list, procedures: list, schedule: str, styles: dict) -> Table:
    """
    NASET goal table — procedures shown once for the whole goal.
    This is the CORRECT NASET format when evaluation procedures apply
    to all objectives under a goal (which is the normal case).
    """
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
    """
    NASET goal table where each objective genuinely has its own
    Procedures and Schedule. Only used when EVERY objective has them.
    """
    header = [
        Paragraph("Short-term Instructional Objective", styles["tbl_hdr"]),
        Paragraph("Evaluation Procedures",              styles["tbl_hdr"]),
        Paragraph("Evaluation Schedule",                styles["tbl_hdr"]),
    ]
    rows = []
    for obj_text, proc, sched in parsed_objs:
        rows.append([
            Paragraph(_strip_md(obj_text),            styles["tbl_cell"]),
            Paragraph(_strip_md(proc or "—"),          styles["tbl_cell"]),
            Paragraph(_strip_md(sched or "Quarterly"), styles["tbl_cell"]),
        ])

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
    """Extract embedded evaluation info from an objective's text."""
    obj_text = obj_text.strip()

    # Format A: pipe separator
    if "|" in obj_text:
        parts = [p.strip() for p in obj_text.split("|")]
        clean = _strip_md(parts[0])
        proc, sched = "", ""
        for part in parts[1:]:
            if re.match(r"Evaluation Procedures?:", part, re.IGNORECASE):
                proc = re.sub(r"^Evaluation Procedures?:\s*", "", part,
                              flags=re.IGNORECASE).strip()
            elif re.match(r"Evaluation Schedule:", part, re.IGNORECASE):
                sched = re.sub(r"^Evaluation Schedule:\s*", "", part,
                               flags=re.IGNORECASE).strip()
        return clean, proc, sched

    # Format B: sentence-end before "Evaluation Procedures:"
    ep_m = re.search(r'[.!?]\s+Evaluation\s+Procedures?:\s+', obj_text, re.IGNORECASE)
    if ep_m:
        clean     = _strip_md(obj_text[:ep_m.start() + 1])
        eval_part = obj_text[ep_m.start() + 1:]
        proc_m  = re.search(
            r'Evaluation\s+Procedures?:\s*(.+?)(?=\s+Evaluation\s+Schedule:|$)',
            eval_part, re.IGNORECASE | re.DOTALL,
        )
        sched_m = re.search(
            r'Evaluation\s+Schedule:\s*(.+?)\.?\s*$',
            eval_part, re.IGNORECASE,
        )
        proc  = _strip_md(proc_m.group(1).strip())  if proc_m  else ""
        sched = _strip_md(sched_m.group(1).strip().rstrip(".")) if sched_m else ""
        return clean, proc, sched

    return _strip_md(obj_text), "", ""


def _normalize_goals_text(text: str) -> str:
    counter = [0]
    def _replacer(m):
        counter[0] += 1
        return f"\nAnnual Goal {counter[0]}:\n"
    return re.sub(
        r'\n?Annual\s+Goal(?:\s+\d+)?[:\.]?\s*\n?',
        _replacer, text, flags=re.IGNORECASE,
    )


def _parse_goals_narrative(text: str) -> list:
    """
    Parse narrative annual_goals text into goal dicts.

    [FIX 5a] The objective block is now truncated BEFORE any trailing
    "Evaluation Procedures:" / "Evaluation Schedule:" line, so the last
    numbered objective no longer swallows it. Previously the regex used
    \\Z (end of string) for the final item, absorbing the procedures line
    into objective 3 — which left rows 1 and 2 with empty cells.
    """
    text = _strip_section_prefix(text)
    text = _normalize_goals_text(text)

    chunks = re.split(
        r'\n?Annual\s+Goal\s+\d+[:\.]?\s*\n?',
        text, flags=re.IGNORECASE,
    )

    goals = []

    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue

        chunk = re.sub(
            r'^Annual\s+Goal(?:\s+\d+)?[:\.]?\s*',
            '', chunk, flags=re.IGNORECASE,
        ).strip()

        if len(chunk) < 30 or re.match(r'^Section\s+\d+', chunk, re.IGNORECASE):
            continue

        halves = re.split(
            r'\n\s*Short-term\s+(?:Instructional\s+)?Objectives?:?\s*\n',
            chunk, maxsplit=1, flags=re.IGNORECASE,
        )
        goal_text = _strip_md(halves[0].strip())

        if not goal_text or len(goal_text) < 20:
            continue

        objectives     = []
        procedures     = []
        schedule       = "Quarterly"
        per_obj_parsed = []

        if len(halves) > 1:
            obj_block = halves[1]

            # Truncate at any leaked next-goal marker
            next_goal = re.search(
                r'\nAnnual\s+Goal\s+\d+[:\.]', obj_block, re.IGNORECASE)
            if next_goal:
                obj_block = obj_block[:next_goal.start()]

            # ── [FIX 5a] Split off the trailing shared eval block FIRST ──
            # Find a line that STARTS with "Evaluation Procedures:" or
            # "Evaluation Schedule:" — that block belongs to the whole goal,
            # not to the last objective.
            shared_eval_match = re.search(
                r'\n\s*Evaluation\s+(?:Procedures?|Schedule)\s*:',
                obj_block, re.IGNORECASE,
            )
            shared_eval_text = ""
            if shared_eval_match:
                shared_eval_text = obj_block[shared_eval_match.start():]
                obj_block        = obj_block[:shared_eval_match.start()]

            # Extract numbered objective items from the truncated block
            raw_items = re.findall(
                r'^\s*\d+\.\s+(.+?)(?=\n\s*\d+\.|\Z)',
                obj_block, flags=re.MULTILINE | re.DOTALL,
            )

            for item in raw_items:
                obj_c, p, s = _split_inline_eval(item.strip())
                per_obj_parsed.append((obj_c, p, s))
                objectives.append(obj_c)
                if p and p not in procedures:
                    procedures.append(p)
                if s:
                    schedule = s

            # ── Parse the shared eval block that we split off ──
            if shared_eval_text:
                ep_m = re.search(
                    r'Evaluation\s+Procedures?\s*:\s*(.+?)'
                    r'(?=\n\s*Evaluation\s+Schedule\s*:|\Z)',
                    shared_eval_text, re.IGNORECASE | re.DOTALL,
                )
                if ep_m:
                    proc_text = _strip_md(ep_m.group(1).strip().rstrip(".\n"))
                    if proc_text and proc_text not in procedures:
                        procedures.append(proc_text)

                es_m = re.search(
                    r'Evaluation\s+Schedule\s*:\s*(.+?)(?:\n|\Z)',
                    shared_eval_text, re.IGNORECASE,
                )
                if es_m:
                    schedule = _strip_md(es_m.group(1).strip().rstrip("."))

        goals.append({
            "goal_text":      goal_text,
            "objectives":     objectives,
            "procedures":     procedures,
            "schedule":       schedule,
            "per_obj_parsed": per_obj_parsed,
        })

    return goals


# ── Section renderers ─────────────────────────────────────────────────────

def _render_section1(student: dict, iep_id: str, compliance_status: Any,
                     styles: dict) -> list:
    # [FIX 4] Age sanity check
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

    # [FIX 3] Severity — never blank
    severity_raw = str(student.get("severity", "")).strip()
    severity_display = (
        severity_raw
        if severity_raw and severity_raw not in ("—", "None", "")
        else "Not Specified"
    )

    rows = [
        ("School / Agency",      student.get("school", "—")),
        ("Date of IEP Meeting",  _format_iep_date()),
        ("Student Name",         student.get("name", "—")),
        ("Student ID",           iep_id[:8].upper()),
        ("Age",                  age_display),
        ("Current Grade",        student.get("grade", "—")),
        ("Disability Category",  student.get("disability", "—")),
        ("Severity",             severity_display),
        ("Dominant Language",    student.get("language", "English")),
        ("Interpreter Needed",   "No"),
        ("Compliance Status",    _fix_compliance(compliance_status)),
        ("IEP ID",               iep_id),
    ]

    return [_kv_table(rows, styles), Spacer(1, 10)]


def _render_section2(iep: dict, styles: dict) -> list:
    story = []
    subsections = [
        ("A — Academic / Educational Achievement & Learning Characteristics",
         "academic_performance"),
        ("B — Social Development",   "social_development"),
        ("C — Physical Development", "physical_development"),
        ("D — Management Needs",     "management_needs"),
    ]
    for label, key in subsections:
        content = iep.get(key, "")
        if not content:
            continue
        story.append(Paragraph(label, styles["sub_hdr"]))
        story.extend(_body_paras(content, styles))
        story.append(Spacer(1, 6))
    return story


def _render_section3(iep: dict, styles: dict) -> list:
    return _body_paras(iep.get("long_term_outcomes", ""), styles)


def _render_section4(iep: dict, styles: dict) -> list:
    """
    Section 4 — Annual Goals and STOs.

    [FIX 5b] Uses all() instead of any() when deciding between the
    per-row and shared table. Previously, if only ONE objective had its
    own procedures (usually the last, due to the parsing bug), the
    per-row table was chosen and the other rows rendered "—".
    Now the per-row table is only used when EVERY objective genuinely
    has its own procedures; otherwise the shared table is used, which
    shows procedures once for the goal — correct NASET format.
    """
    story = []
    raw   = iep.get("annual_goals", "")
    if not raw:
        return [Paragraph("No annual goals drafted.", styles["note"])]

    goals = _parse_goals_narrative(_to_clean_str(raw))

    if not goals:
        return _body_paras(raw, styles)

    for i, g in enumerate(goals, 1):
        goal_text      = g["goal_text"]
        objectives     = g["objectives"]
        procedures     = g["procedures"]
        schedule       = g["schedule"]
        per_obj_parsed = g["per_obj_parsed"]

        if len(goal_text) < 40 or re.match(r'^Section\s+\d+', goal_text, re.IGNORECASE):
            continue

        story.append(Paragraph(f"Annual Goal {i}", styles["goal_num"]))
        story.append(Paragraph(goal_text, styles["body"]))
        story.append(Spacer(1, 4))

        if not objectives:
            story.append(Paragraph(
                "Short-term objectives to be confirmed with IEP team.",
                styles["note"],
            ))
        elif per_obj_parsed and all(p for _, p, _ in per_obj_parsed):
            # [FIX 5b] all() not any() — every objective must have its own
            story.append(_goals_table_per_row(per_obj_parsed, styles))
        else:
            story.append(_goals_table_shared(objectives, procedures, schedule, styles))

        story.append(Spacer(1, 8))

    return story


def _render_section5(iep: dict, styles: dict) -> list:
    return _body_paras(iep.get("special_education_services", ""), styles)


def _render_section6(iep: dict, styles: dict) -> list:
    return _body_paras(iep.get("general_education_participation", ""), styles)


def _render_section7(iep: dict, styles: dict) -> list:
    return _body_paras(iep.get("participating_agencies", ""), styles)


def _render_section8(iep: dict, styles: dict) -> list:
    return _body_paras(iep.get("coordinated_activities", ""), styles)


def _render_section9(iep: dict, styles: dict) -> list:
    return _body_paras(iep.get("graduation_info", ""), styles)


def _render_section10(iep: dict, styles: dict) -> list:
    return _body_paras(iep.get("recommendations_summary", ""), styles)


def _render_section11(iep: dict, styles: dict) -> list:
    story = _body_paras(iep.get("progress_reporting", ""), styles)
    story += [
        Spacer(1, 20),
        HRFlowable(width=CONTENT_W, thickness=0.5, color=BORDER),
        Spacer(1, 12),
        Paragraph("IEP Committee Signatures & Acknowledgement", styles["sub_hdr"]),
    ]
    sig_data = [[
        Paragraph("Special Education Teacher", styles["kv_label"]),
        Paragraph("Parent / Guardian",         styles["kv_label"]),
        Paragraph("Principal / Head Master",   styles["kv_label"]),
    ], [
        Paragraph("_____________________", styles["body"]),
        Paragraph("_____________________", styles["body"]),
        Paragraph("_____________________", styles["body"]),
    ], [
        Paragraph("Name: _______________", styles["body_sm"]),
        Paragraph("Name: _______________", styles["body_sm"]),
        Paragraph("Name: _______________", styles["body_sm"]),
    ], [
        Paragraph("Designation: ________", styles["body_sm"]),
        Paragraph("Relationship: _______", styles["body_sm"]),
        Paragraph("School Seal: ",         styles["body_sm"]),
    ], [
        Paragraph("Date: _______________", styles["body_sm"]),
        Paragraph("Date: _______________", styles["body_sm"]),
        Paragraph("Date: _______________", styles["body_sm"]),
    ]]
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
    """[FIX 1] Cross-platform header/footer — no %-d Linux-only directive."""
    from reportlab.lib.units import cm as _cm

    footer_text = (
        f"Generated by Project SAMARTH · Compliant with RPwD Act 2016 "
        f"& NCTE/NCERT Guidelines · {_format_date_crossplatform()}"
    )

    def _draw(canvas, doc):
        canvas.saveState()
        page_w, page_h = A4

        canvas.setFillColor(DARK_NAVY)
        canvas.rect(0, page_h - 1.6 * _cm, page_w, 1.6 * _cm, fill=1, stroke=0)
        canvas.setFillColor(WHITE)
        canvas.setFont("Helvetica-Bold", 11)
        canvas.drawCentredString(page_w / 2, page_h - 1.0 * _cm,
                                 "INDIVIDUALIZED EDUCATION PROGRAM")
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#a5b4c8"))
        canvas.drawCentredString(
            page_w / 2, page_h - 1.4 * _cm,
            "Project SAMARTH · Compliant with RPwD Act 2016 & NCTE/NCERT Guidelines · India",
        )

        canvas.setFillColor(colors.HexColor("#f1f5f9"))
        canvas.rect(0, 0, page_w, 1.2 * _cm, fill=1, stroke=0)
        canvas.setFillColor(MID_GRAY)
        canvas.setFont("Helvetica", 7)
        canvas.drawString(MARGIN, 0.45 * _cm, footer_text)
        canvas.drawRightString(
            page_w - MARGIN, 0.45 * _cm,
            f"IEP ID: {iep_id}  |  Page {doc.page}",
        )

        canvas.restoreState()

    return _draw


# ── Main entry point ──────────────────────────────────────────────────────

def generate_iep_pdf(state: dict, output_dir: str = "outputs") -> str:
    """Build the complete NASET IEP PDF and return the output file path."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    iep_id     = state.get("student_id", state.get("iep_id", "unknown"))
    profile    = state.get("student_profile", {})
    drafted    = state.get("drafted_iep", {})
    compliance = state.get("compliance_report", {})

    bg_text = drafted.get("background_info", "")
    student = _extract_student_from_background(bg_text, drafted)

    student.setdefault("name",       profile.get("student_name", ""))
    student.setdefault("school",     profile.get("school_name", ""))
    student.setdefault("grade",      str(profile.get("grade", "")))
    student.setdefault("disability", profile.get("disability_category", ""))
    student.setdefault("language",   profile.get("dominant_language", "English"))

    student["severity"] = (
        student.get("severity")
        or profile.get("disability_severity", "")
        or ""
    )

    # [FIX 2] Filename built after student name is known
    student_name = student.get("name", "").strip()
    if student_name:
        safe_name = _sanitize_filename(student_name)
        filename  = f"IEP_{safe_name}_{iep_id[:8]}.pdf"
    else:
        filename  = f"IEP_student_{iep_id[:8]}.pdf"
        logger.warning("generate_iep_pdf: student name unavailable — using fallback filename.")

    output_path = str(Path(output_dir) / filename)

    styles = _build_styles()

    doc = SimpleDocTemplate(
        output_path,
        pagesize     = A4,
        leftMargin   = MARGIN,
        rightMargin  = MARGIN,
        topMargin    = 2.2 * cm,
        bottomMargin = 1.6 * cm,
        title        = f"IEP — {student_name or iep_id}",
        author       = "Project SAMARTH",
    )

    compliance_status = (compliance or {}).get("status", "unknown")
    on_page = _make_header_footer(iep_id, student_name)

    story = []
    story += _section_block("1", "Background Information", styles)
    story += _render_section1(student, iep_id, compliance_status, styles)

    story += _section_block("2", "Present Levels of Performance and Individual Needs", styles)
    story += _render_section2(drafted, styles)

    story += _section_block("3", "Long-Term Adult Outcomes", styles)
    story += _render_section3(drafted, styles)

    story += _section_block("4", "Measurable Annual Goals and Short-Term Instructional Objectives", styles)
    story += _render_section4(drafted, styles)

    story += _section_block("5", "Special Education Programs and Related Services / Program Modifications", styles)
    story += _render_section5(drafted, styles)

    story += _section_block("6", "Participation in General Education Classes, Non-Academic and Extracurricular Activities", styles)
    story += _render_section6(drafted, styles)

    story += _section_block("7", "Participating Agencies for Students Who Require Transition Services", styles)
    story += _render_section7(drafted, styles)

    story += _section_block("8", "Coordinated Set of Activities Leading to Long-Term Adult Outcomes", styles)
    story += _render_section8(drafted, styles)

    story += _section_block("9", "Graduation / School Completion Information", styles)
    story += _render_section9(drafted, styles)

    story += _section_block("10", "Summary of Selected Recommendations", styles)
    story += _render_section10(drafted, styles)

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
        return {
            **state,
            "workflow_status": WorkflowStatus.FAILED,
            "error_log":       errors,
        }

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
        return {
            **state,
            "workflow_status": WorkflowStatus.FAILED,
            "error_log":       errors,
        }