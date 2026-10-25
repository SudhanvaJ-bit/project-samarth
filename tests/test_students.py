"""
tests/test_students.py — the student register. Offline, no Gemini.
"""

import re
from datetime import date

import pytest

STUDENT = {
    "full_name":           "Arjun Sharma",
    "date_of_birth":       "2016-03-14",
    "grade":               "Grade 4",
    "school_name":         "Delhi Public School, Bengaluru",
    "disability_category": "Dyslexia",
    "disability_severity": "moderate",
    "guardian_name":       "Meera Sharma",
    "notes": ("Arjun struggles with reading and written expression. He reverses "
              "letters like b/d. He excels in oral discussions."),
}

CODE_RE = re.compile(r"^STU-[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{6}$")


def register(client, headers, **changes):
    r = client.post("/students", json={**STUDENT, **changes}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def iep_payload(student, **changes):
    """What the website sends when generating for a registered student."""
    return {
        "student_name":        student["full_name"],
        "age":                 student["age"],
        "grade":               student["grade"],
        "school_name":         student["school_name"],
        "disability_category": student["disability_category"],
        "disability_severity": student["disability_severity"],
        "raw_notes":           student["notes"],
        "student_code":        student["student_code"],
        **changes,
    }


# ═════════════════════════════════════════════════════════════════════════
# Registering
# ═════════════════════════════════════════════════════════════════════════

def test_register_student_gets_unique_code(client, educator):
    s = register(client, educator)
    assert CODE_RE.match(s["student_code"])
    assert s["full_name"] == "Arjun Sharma"
    assert s["iep_count"] == 0 and s["latest_iep"] is None
    assert s["is_archived"] is False


def test_codes_are_unique_and_not_sequential(client, educator):
    codes = [register(client, educator, full_name=f"Student {i}")["student_code"] for i in range(25)]
    assert len(set(codes)) == 25


def test_code_collision_draws_a_new_code(client, educator, monkeypatch):
    from app.services import students as reg
    first = register(client, educator)["student_code"]
    drawn = iter([first, first, "STU-ZZZZZZ"])           # the first two clash
    monkeypatch.setattr(reg, "new_code", lambda: next(drawn))
    assert register(client, educator)["student_code"] == "STU-ZZZZZZ"


def test_age_is_calculated_from_date_of_birth(client, educator, monkeypatch):
    monkeypatch.setenv("SAMARTH_FIXED_DATE", "2026-03-13")
    assert register(client, educator)["age"] == 9          # birthday is tomorrow
    monkeypatch.setenv("SAMARTH_FIXED_DATE", "2026-03-14")
    assert client.get("/students", headers=educator).json()[0]["age"] == 10


@pytest.mark.parametrize("change", [
    {"full_name": " "},                         # blank after trimming
    {"date_of_birth": "2099-01-01"},            # in the future
    {"date_of_birth": "2025-01-01"},            # too young (under 3)
    {"date_of_birth": "1990-01-01"},            # too old (over 25)
    {"disability_category": "Not A Category"},
    {"disability_severity": "extreme"},
    {"grade": ""},
    {"school_name": "x" * 201},
])
def test_register_rejects_bad_input(client, educator, change):
    r = client.post("/students", json={**STUDENT, **change}, headers=educator)
    assert r.status_code == 422


def test_text_is_trimmed(client, educator):
    s = register(client, educator, full_name="  Arjun Sharma  ", grade=" Grade 4 ")
    assert s["full_name"] == "Arjun Sharma" and s["grade"] == "Grade 4"


# ═════════════════════════════════════════════════════════════════════════
# Who can see what
# ═════════════════════════════════════════════════════════════════════════

def test_students_require_login(client):
    assert client.get("/students").status_code == 401
    assert client.post("/students", json=STUDENT).status_code == 401


def test_admin_cannot_see_students(client, admin):
    assert client.get("/students", headers=admin).status_code == 403


def test_other_educator_sees_404(client, educator, other_educator):
    code = register(client, educator)["student_code"]
    assert client.get("/students", headers=other_educator).json() == []
    assert client.get(f"/students/{code}", headers=other_educator).status_code == 404
    assert client.patch(f"/students/{code}", json={"grade": "X"}, headers=other_educator).status_code == 404
    assert client.delete(f"/students/{code}", headers=other_educator).status_code == 404
    assert client.get(f"/students/{code}/ieps", headers=other_educator).status_code == 404
    # The owner's record is untouched
    assert client.get(f"/students/{code}", headers=educator).json()["grade"] == "Grade 4"


def test_other_educator_cannot_file_iep_under_my_student(client, educator, other_educator, fake_pipeline):
    s = register(client, educator)
    r = client.post("/iep/generate", json=iep_payload(s), headers=other_educator)
    assert r.status_code == 404
    assert fake_pipeline == []                  # rejected before any AI call


def test_code_lookup_is_case_insensitive(client, educator):
    code = register(client, educator)["student_code"]
    assert client.get(f"/students/{code.lower()}", headers=educator).status_code == 200


# ═════════════════════════════════════════════════════════════════════════
# Editing, archiving, deleting
# ═════════════════════════════════════════════════════════════════════════

def test_update_changes_only_sent_fields(client, educator):
    s = register(client, educator)
    r = client.patch(f"/students/{s['student_code']}", headers=educator,
                     json={"grade": "Grade 5", "parent_concerns": "Homework stress"})
    assert r.status_code == 200
    data = r.json()
    assert data["grade"] == "Grade 5" and data["parent_concerns"] == "Homework stress"
    assert data["school_name"] == STUDENT["school_name"]          # unchanged
    assert data["student_code"] == s["student_code"]              # the ID never changes


def test_update_cannot_clear_required_field(client, educator):
    code = register(client, educator)["student_code"]
    assert client.patch(f"/students/{code}", json={"full_name": None}, headers=educator).status_code == 422
    assert client.patch(f"/students/{code}", json={"date_of_birth": "2099-01-01"},
                        headers=educator).status_code == 422


def test_archive_hides_then_restores(client, educator):
    code = register(client, educator)["student_code"]
    client.patch(f"/students/{code}", json={"is_archived": True}, headers=educator)
    assert client.get("/students", headers=educator).json() == []
    archived = client.get("/students?include_archived=true", headers=educator).json()
    assert [x["student_code"] for x in archived] == [code]
    client.patch(f"/students/{code}", json={"is_archived": False}, headers=educator)
    assert len(client.get("/students", headers=educator).json()) == 1


def test_delete_student_without_ieps(client, educator):
    code = register(client, educator)["student_code"]
    assert client.delete(f"/students/{code}", headers=educator).status_code == 204
    assert client.get(f"/students/{code}", headers=educator).status_code == 404


# ═════════════════════════════════════════════════════════════════════════
# IEPs filed under a student
# ═════════════════════════════════════════════════════════════════════════

def test_generate_for_registered_student(client, educator, fake_pipeline):
    s = register(client, educator)
    r = client.post("/iep/generate", json=iep_payload(s), headers=educator)
    assert r.status_code == 201, r.text
    iep_id = r.json()["iep_id"]

    # The code is not sent to the AI — the prompt stays exactly as before
    assert "student_code" not in fake_pipeline[0]

    ieps = client.get(f"/students/{s['student_code']}/ieps", headers=educator).json()["ieps"]
    assert [i["iep_id"] for i in ieps] == [iep_id]

    listed = client.get("/students", headers=educator).json()[0]
    assert listed["iep_count"] == 1
    assert listed["latest_iep"]["iep_id"] == iep_id

    drafts = client.get("/iep/drafts", headers=educator).json()["drafts"]
    assert drafts[0]["student_code"] == s["student_code"]


def test_iep_without_student_still_works(client, educator, fake_pipeline):
    s = register(client, educator)
    payload = iep_payload(s)
    payload.pop("student_code")
    assert client.post("/iep/generate", json=payload, headers=educator).status_code == 201
    assert client.get(f"/students/{s['student_code']}/ieps", headers=educator).json()["ieps"] == []


def test_unknown_student_code_rejected(client, educator, fake_pipeline):
    s = register(client, educator)
    r = client.post("/iep/generate", json=iep_payload(s, student_code="STU-ZZZZZZ"), headers=educator)
    assert r.status_code == 404
    assert fake_pipeline == []


def test_student_with_ieps_cannot_be_deleted(client, educator, fake_pipeline):
    s = register(client, educator)
    client.post("/iep/generate", json=iep_payload(s), headers=educator)
    r = client.delete(f"/students/{s['student_code']}", headers=educator)
    assert r.status_code == 409
    assert "Archive" in r.json()["detail"]


def test_editing_student_does_not_rewrite_existing_iep(client, educator, fake_pipeline):
    s = register(client, educator)
    iep_id = client.post("/iep/generate", json=iep_payload(s), headers=educator).json()["iep_id"]
    client.patch(f"/students/{s['student_code']}", json={"full_name": "Renamed Student"}, headers=educator)
    draft = client.get(f"/iep/{iep_id}/draft", headers=educator).json()
    assert draft["student_name"] == "Arjun Sharma"          # the IEP keeps its snapshot
