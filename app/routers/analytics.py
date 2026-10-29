"""
app/routers/analytics.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  GET /analytics   — figures for the Analytics page (educators)

Everything is computed from the signed-in educator's OWN IEPs and students,
so one teacher's figures never include another's records.

THE NUMBERS
- Totals, this month, and the last 6 months (by calendar month, in the
  time zone the browser sends — India by default).
- Review progress: awaiting review / in review / approved.
- Disability categories and grades of the students IEPs were made for.
- Human-edit rate: the share of IEPs where the teacher changed at least one
  section or student detail during review. A useful honest measure of how
  much the AI's draft needed correcting.
- Average generation time: recorded for IEPs generated from now on.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from app.db import IEPDraft, Student, User, get_session
from app.services.auth import require_educator

router = APIRouter(prefix="/analytics", tags=["Analytics"])

MONTHS = 6


def _parse(ts) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(ts))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _month_starts(now_local: datetime, n: int) -> list:
    """First day of each of the last n months, oldest first (local time)."""
    year, month = now_local.year, now_local.month
    out = []
    for _ in range(n):
        out.append((year, month))
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return list(reversed(out))


@router.get("", summary="Your IEP and student figures")
def analytics(
    tz_offset_minutes: int = Query(330, ge=-720, le=840,
                                   description="Browser's UTC offset; 330 = India"),
    user: User = Depends(require_educator),
    session: Session = Depends(get_session),
):
    tz = timezone(timedelta(minutes=tz_offset_minutes))
    now = datetime.now(tz)

    records = [row.record or {} for row in session.exec(
        select(IEPDraft).where(IEPDraft.owner_id == user.id)).all()]
    students = session.exec(select(Student).where(Student.owner_id == user.id)).all()

    created = [(_parse(r.get("created_at")), r) for r in records]
    created = [(dt.astimezone(tz), r) for dt, r in created if dt]
    created.sort(key=lambda x: x[0], reverse=True)

    # ── Monthly ─────────────────────────────────────────────
    per_month = Counter((dt.year, dt.month) for dt, _ in created)
    monthly = [{
        "month": f"{y}-{m:02d}",
        "label": datetime(y, m, 1).strftime("%b"),
        "count": per_month.get((y, m), 0),
    } for y, m in _month_starts(now, MONTHS)]

    # ── Review progress ─────────────────────────────────────
    status = Counter(r.get("review_status", "pending") for r in records)
    edited = sum(1 for r in records if r.get("edited_sections") or r.get("edited_profile_fields"))

    # ── Who the IEPs were for ───────────────────────────────
    def profile(r, key):
        return str((r.get("student_profile") or {}).get(key) or "").strip()

    by_disability = Counter(profile(r, "disability_category") or "Not recorded" for r in records)
    by_grade      = Counter(profile(r, "grade") for r in records if profile(r, "grade"))

    timed = [r["generation_seconds"] for r in records
             if isinstance(r.get("generation_seconds"), (int, float))]

    # ── Recent activity ─────────────────────────────────────
    events = []
    for dt, r in created:
        name = profile(r, "student_name") or "a student"
        events.append({"type": "generated", "student_name": name,
                       "iep_id": r.get("iep_id", ""), "at": dt.isoformat()})
        if r.get("review_status") == "approved":
            up = _parse(r.get("updated_at"))
            if up:
                events.append({"type": "approved", "student_name": name,
                               "iep_id": r.get("iep_id", ""), "at": up.astimezone(tz).isoformat()})
    events.sort(key=lambda e: e["at"], reverse=True)

    def ranked(counter):
        total = sum(counter.values()) or 1
        return [{"label": k, "count": v, "pct": round(100 * v / total)}
                for k, v in counter.most_common()]

    return {
        "totals": {
            "ieps":              len(records),
            "this_month":        per_month.get((now.year, now.month), 0),
            "approved":          status.get("approved", 0),
            "awaiting_review":   status.get("pending", 0),
            "in_review":         status.get("edited", 0),
            "students":          sum(1 for s in students if not s.is_archived),
            "students_archived": sum(1 for s in students if s.is_archived),
            "linked_to_student": sum(1 for r in records if r.get("student_code")),
        },
        "human_edit_rate":        round(100 * edited / len(records)) if records else None,
        "avg_generation_seconds": round(sum(timed) / len(timed)) if timed else None,
        "timed_ieps":             len(timed),
        "monthly":                monthly,
        "by_disability":          ranked(by_disability),
        "by_grade":               ranked(by_grade),
        "recent":                 events[:8],
    }
