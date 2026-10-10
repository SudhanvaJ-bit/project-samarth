"""
tests/test_api.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
API tests — fast, offline, no Gemini calls.

The AI pipeline is replaced by a stand-in (see conftest.py), so these tests
check everything AROUND the AI: login, who can see what, the review
workflow, and the PDF download. Each test gets its own empty database and
folder.

Run:  pytest tests/test_api.py -v
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import pytest

VALID_PAYLOAD = {
    "student_name":         "Arjun Sharma",
    "age":                  10,
    "grade":                "Grade 4",
    "school_name":          "Delhi Public School, Bengaluru",
    "disability_category":  "Dyslexia",
    "disability_severity":  "moderate",
    "raw_notes": (
        "Arjun struggles with reading and written expression. He reverses "
        "letters like b/d. He excels in oral discussions."
    ),
    "academic_history":     "Grade 2: 58%, Grade 3: 62%",
    "teacher_observations": "Loses focus during reading.",
    "parent_concerns":      "Gets frustrated with reading at home.",
}


def generate(client, headers, **overrides):
    """Generate an IEP and return its id."""
    r = client.post("/iep/generate", json={**VALID_PAYLOAD, **overrides}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["iep_id"]


# ═════════════════════════════════════════════════════════════════════════
# Public endpoints
# ═════════════════════════════════════════════════════════════════════════

def test_root(client):
    r = client.get("/")
    assert r.status_code == 200
    data = r.json()
    assert data["project"] == "Project SAMARTH"
    assert data["version"] == "1.1.0"


def test_health_is_public(client):
    r = client.get("/iep/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    # The public health check must not reveal anything about stored IEPs
    assert "drafts" not in data and "ieps" not in data


def test_docs_available(client):
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


# ═════════════════════════════════════════════════════════════════════════
# Login
# ═════════════════════════════════════════════════════════════════════════

def test_login_success(client, make_user):
    make_user("teacher@school.test")
    r = client.post("/auth/login",
                    data={"username": "Teacher@School.test", "password": "correct-horse-battery"})
    assert r.status_code == 200
    data = r.json()
    assert data["token_type"] == "bearer"
    assert data["access_token"]
    assert data["user"]["email"] == "teacher@school.test"    # email is normalised
    assert "password_hash" not in data["user"]


@pytest.mark.parametrize("email,password", [
    ("teacher@school.test", "wrong-password"),     # wrong password
    ("nobody@school.test",  "correct-horse-battery"),  # no such account
    ("not-an-email",        "correct-horse-battery"),  # malformed email
])
def test_login_failures_look_identical(client, make_user, email, password):
    make_user("teacher@school.test")
    r = client.post("/auth/login", data={"username": email, "password": password})
    assert r.status_code == 401
    # Same message every time, so an attacker can't tell which part was wrong
    assert r.json()["detail"] == "Incorrect email or password."


def test_me(client, educator):
    r = client.get("/auth/me", headers=educator)
    assert r.status_code == 200
    assert r.json()["email"] == "teacher@school.test"
    assert r.json()["role"] == "educator"


@pytest.mark.parametrize("headers", [
    {},                                              # no token
    {"Authorization": "Bearer not-a-real-token"},    # forged token
])
def test_me_rejects_missing_or_bad_token(client, headers):
    assert client.get("/auth/me", headers=headers).status_code == 401


@pytest.mark.parametrize("method,path", [
    ("post", "/iep/generate"),
    ("get",  "/iep/drafts"),
    ("get",  "/iep/some-id/draft"),
    ("put",  "/iep/some-id/draft"),
    ("post", "/iep/some-id/finalize"),
    ("get",  "/iep/some-id/download"),
])
def test_iep_endpoints_require_login(client, method, path):
    r = getattr(client, method)(path)
    assert r.status_code == 401


def test_change_password(client, educator):
    r = client.post("/auth/me/password", headers=educator,
                    json={"current_password": "wrong", "new_password": "brand-new-pass"})
    assert r.status_code == 400

    r = client.post("/auth/me/password", headers=educator,
                    json={"current_password": "correct-horse-battery", "new_password": "short"})
    assert r.status_code == 400

    r = client.post("/auth/me/password", headers=educator,
                    json={"current_password": "correct-horse-battery",
                          "new_password": "brand-new-pass"})
    assert r.status_code == 200

    old = client.post("/auth/login", data={"username": "teacher@school.test",
                                           "password": "correct-horse-battery"})
    new = client.post("/auth/login", data={"username": "teacher@school.test",
                                           "password": "brand-new-pass"})
    assert old.status_code == 401
    assert new.status_code == 200


# ═════════════════════════════════════════════════════════════════════════
# Roles: admins manage accounts, educators manage IEPs
# ═════════════════════════════════════════════════════════════════════════

def test_admin_cannot_read_ieps(client, admin):
    # Least privilege: account management does not need children's records
    assert client.get("/iep/drafts", headers=admin).status_code == 403
    r = client.post("/iep/generate", json=VALID_PAYLOAD, headers=admin)
    assert r.status_code == 403


def test_educator_cannot_manage_accounts(client, educator):
    assert client.get("/auth/users", headers=educator).status_code == 403
    r = client.post("/auth/users", headers=educator,
                    json={"email": "x@school.test", "full_name": "X", "password": "password123"})
    assert r.status_code == 403


def test_admin_creates_and_lists_accounts(client, admin):
    r = client.post("/auth/users", headers=admin,
                    json={"email": "new@school.test", "full_name": "New Teacher",
                          "password": "password123"})
    assert r.status_code == 201
    assert r.json()["role"] == "educator"
    assert "password_hash" not in r.json()

    emails = [u["email"] for u in client.get("/auth/users", headers=admin).json()]
    assert "new@school.test" in emails

    # The new account can log in
    r = client.post("/auth/login", data={"username": "new@school.test", "password": "password123"})
    assert r.status_code == 200


@pytest.mark.parametrize("body,status", [
    ({"email": "admin@school.test", "full_name": "Dup", "password": "password123"}, 409),
    ({"email": "a@school.test", "full_name": "Short", "password": "short"},         400),
    ({"email": "b@school.test", "full_name": "Bad", "password": "password123",
      "role": "superuser"},                                                          400),
    ({"email": "not-an-email", "full_name": "Bad", "password": "password123"},      400),
])
def test_admin_create_user_validation(client, admin, body, status):
    assert client.post("/auth/users", headers=admin, json=body).status_code == status


def test_deactivation_takes_effect_immediately(client, admin, make_user, login):
    user = make_user("leaver@school.test")
    token = login("leaver@school.test")
    assert client.get("/iep/drafts", headers=token).status_code == 200

    r = client.patch(f"/auth/users/{user.id}", headers=admin, json={"is_active": False})
    assert r.status_code == 200
    assert r.json()["is_active"] is False

    # The token they already hold stops working at once, not when it expires
    assert client.get("/iep/drafts", headers=token).status_code == 401
    # And they can no longer log in
    r = client.post("/auth/login", data={"username": "leaver@school.test",
                                         "password": "correct-horse-battery"})
    assert r.status_code == 401


def test_admin_cannot_deactivate_self(client, admin):
    me = client.get("/auth/me", headers=admin).json()
    r = client.patch(f"/auth/users/{me['id']}", headers=admin, json={"is_active": False})
    assert r.status_code == 400


# ═════════════════════════════════════════════════════════════════════════
# Generating an IEP
# ═════════════════════════════════════════════════════════════════════════

def test_generate_success(client, educator, fake_pipeline):
    r = client.post("/iep/generate", json=VALID_PAYLOAD, headers=educator)
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["student_name"] == "Arjun Sharma"
    assert data["workflow_status"] == "Completed"
    assert data["compliance_status"] == "Partial"
    assert data["pdf_output_path"]
    assert data["errors"] == []
    assert "Review" in data["message"]

    # The pipeline received the form data unchanged
    assert fake_pipeline[0]["disability_category"] == "Dyslexia"
    assert fake_pipeline[0]["disability_severity"] == "moderate"

    # It now appears in the educator's list
    drafts = client.get("/iep/drafts", headers=educator).json()["drafts"]
    assert [d["iep_id"] for d in drafts] == [data["iep_id"]]
    assert drafts[0]["review_status"] == "pending"


def test_generate_writes_only_inside_test_folder(client, educator, fake_pipeline, workdir):
    iep_id = generate(client, educator)
    assert (workdir / "drafts" / f"{iep_id}.json").is_file()
    assert any((workdir / "outputs").glob("IEP_*.pdf"))


@pytest.mark.parametrize("change", [
    {"student_name": None},                     # required field missing
    {"raw_notes": "Too short."},                # notes under 50 characters
    {"disability_category": "Not A Category"},  # not in the RPwD list
    {"age": 2},                                 # below 3
    {"age": 30},                                # above 25
])
def test_generate_rejects_bad_input(client, educator, fake_pipeline, change):
    payload = {**VALID_PAYLOAD, **change}
    payload = {k: v for k, v in payload.items() if v is not None}
    r = client.post("/iep/generate", json=payload, headers=educator)
    assert r.status_code == 422
    assert fake_pipeline == []          # rejected before any AI call


def test_generate_from_report_rejects_non_pdf(client, educator):
    r = client.post("/iep/generate-from-report", headers=educator,
                    files={"file": ("notes.txt", b"hello", "text/plain")})
    assert r.status_code == 400


# ═════════════════════════════════════════════════════════════════════════
# Ownership: another educator's IEP behaves as if it doesn't exist
# ═════════════════════════════════════════════════════════════════════════

def test_other_educator_sees_404_everywhere(client, educator, other_educator, fake_pipeline):
    iep_id = generate(client, educator)

    assert client.get("/iep/drafts", headers=other_educator).json()["drafts"] == []
    assert client.get(f"/iep/{iep_id}/draft", headers=other_educator).status_code == 404
    assert client.get(f"/iep/{iep_id}/download", headers=other_educator).status_code == 404
    r = client.put(f"/iep/{iep_id}/draft", headers=other_educator,
                   json={"sections": {"annual_goals": "Hijacked"}})
    assert r.status_code == 404
    assert client.post(f"/iep/{iep_id}/finalize", headers=other_educator).status_code == 404

    # 404, not 403 — and the same answer as for an id that never existed
    missing = client.get("/iep/00000000-0000-0000-0000-000000000000/draft",
                         headers=other_educator)
    assert missing.status_code == 404

    # The owner's IEP was not changed by any of this
    sections = client.get(f"/iep/{iep_id}/draft", headers=educator).json()["sections"]
    goals = next(s for s in sections if s["key"] == "annual_goals")
    assert goals["content"] != "Hijacked"


def test_path_traversal_id_is_404(client, educator):
    assert client.get("/iep/..%2F..%2Fsecret/draft", headers=educator).status_code == 404


# ═════════════════════════════════════════════════════════════════════════
# Human review
# ═════════════════════════════════════════════════════════════════════════

def test_review_draft_shape(client, educator, fake_pipeline):
    iep_id = generate(client, educator)
    r = client.get(f"/iep/{iep_id}/draft", headers=educator)
    assert r.status_code == 200
    data = r.json()

    assert data["review_status"] == "pending"
    assert data["revision"] == 0
    assert len(data["student"]) == 7          # Section 1 structured fields
    assert len(data["sections"]) == 13        # Sections 2–11 prose
    name = next(f for f in data["student"] if f["key"] == "student_name")
    assert name["value"] == "Arjun Sharma"
    assert name["human_edited"] is False
    assert set(data["severity_options"]) == {"Mild", "Moderate", "Severe"}


def test_edit_records_who_and_what(client, educator, fake_pipeline):
    iep_id = generate(client, educator)
    r = client.put(f"/iep/{iep_id}/draft", headers=educator, json={
        "sections": {"annual_goals": "Teacher-written goals."},
        "profile":  {"grade": "Grade 5"},
        "review_notes": "Checked with parents.",
        "reviewed_by": "Someone Else",          # ignored: identity comes from login
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["review_status"] == "edited"
    assert data["revision"] == 1
    assert data["edited_sections"] == ["annual_goals"]
    assert data["edited_profile_fields"] == ["grade"]
    assert data["reviewed_by"] == "Asha Teacher (teacher@school.test)"

    # The original AI text is kept for comparison
    draft = client.get(f"/iep/{iep_id}/draft", headers=educator).json()
    goals = next(s for s in draft["sections"] if s["key"] == "annual_goals")
    assert goals["content"] == "Teacher-written goals."
    assert goals["original"].startswith("AI draft of")
    assert goals["human_edited"] is True


def test_reverting_an_edit_clears_the_flag(client, educator, fake_pipeline):
    iep_id = generate(client, educator)
    draft = client.get(f"/iep/{iep_id}/draft", headers=educator).json()
    original = next(s for s in draft["sections"] if s["key"] == "annual_goals")["original"]

    client.put(f"/iep/{iep_id}/draft", headers=educator,
               json={"sections": {"annual_goals": "Changed."}})
    r = client.put(f"/iep/{iep_id}/draft", headers=educator,
                   json={"sections": {"annual_goals": original}})
    assert r.json()["edited_sections"] == []


@pytest.mark.parametrize("profile", [
    {"age": "eleven"},
    {"age": 40},
    {"student_name": "   "},
    {"disability_severity": "Extreme"},
])
def test_invalid_profile_edit_saves_nothing(client, educator, fake_pipeline, profile):
    iep_id = generate(client, educator)
    r = client.put(f"/iep/{iep_id}/draft", headers=educator, json={
        "sections": {"annual_goals": "This must NOT be saved either."},
        "profile":  profile,
    })
    assert r.status_code == 422

    # All-or-nothing: the valid section edit in the same request was not applied
    draft = client.get(f"/iep/{iep_id}/draft", headers=educator).json()
    assert draft["revision"] == 0
    goals = next(s for s in draft["sections"] if s["key"] == "annual_goals")
    assert goals["human_edited"] is False


def test_finalize_and_download(client, educator, fake_pipeline):
    iep_id = generate(client, educator)
    r = client.post(f"/iep/{iep_id}/finalize", headers=educator,
                    json={"profile": {"grade": "Grade 5"}})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["review_status"] == "approved"
    assert data["download_url"] == f"/iep/{iep_id}/download"

    r = client.get(f"/iep/{iep_id}/download", headers=educator)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")

    drafts = client.get("/iep/drafts", headers=educator).json()["drafts"]
    assert drafts[0]["review_status"] == "approved"
    assert drafts[0]["grade"] == "Grade 5"


def test_download_missing_pdf_is_404(client, educator, fake_pipeline, workdir):
    iep_id = generate(client, educator)
    for pdf in (workdir / "outputs").glob("*.pdf"):
        pdf.unlink()
    assert client.get(f"/iep/{iep_id}/download", headers=educator).status_code == 404
