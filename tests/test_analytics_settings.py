"""
tests/test_analytics_settings.py — Analytics, Settings, Profile and the PDF
title. Offline, no Gemini.
"""

import pytest

from tests.test_api import VALID_PAYLOAD, generate


# ═════════════════════════════════════════════════════════════════════════
# Analytics
# ═════════════════════════════════════════════════════════════════════════

def test_analytics_empty(client, educator):
    data = client.get("/analytics", headers=educator).json()
    assert data["totals"]["ieps"] == 0
    assert data["totals"]["students"] == 0
    assert len(data["monthly"]) == 6
    assert all(m["count"] == 0 for m in data["monthly"])
    assert data["human_edit_rate"] is None
    assert data["avg_generation_seconds"] is None
    assert data["recent"] == []


def test_analytics_counts_real_records(client, educator, other_educator, fake_pipeline):
    student = client.post("/students", headers=educator, json={
        "full_name": "Kavya Rao", "date_of_birth": "2017-06-02", "grade": "Grade 3",
        "school_name": "KV Mysuru", "disability_category": "Hearing Impairment",
    }).json()
    first  = generate(client, educator)                                        # Dyslexia, Grade 4
    second = generate(client, educator, disability_category="ADHD", grade="Grade 6",
                      student_code=student["student_code"])
    # Teacher edits and approves the first one
    client.put(f"/iep/{first}/draft", headers=educator, json={"sections": {"annual_goals": "Edited"}})
    client.post(f"/iep/{first}/finalize", headers=educator)

    data = client.get("/analytics", headers=educator).json()
    t = data["totals"]
    assert t["ieps"] == 2 and t["this_month"] == 2
    assert t["approved"] == 1 and t["awaiting_review"] == 1
    assert t["students"] == 1 and t["linked_to_student"] == 1
    assert data["monthly"][-1]["count"] == 2
    assert data["human_edit_rate"] == 50
    assert isinstance(data["avg_generation_seconds"], int) and data["timed_ieps"] == 2
    assert {d["label"] for d in data["by_disability"]} == {"Dyslexia", "ADHD"}
    assert {g["label"] for g in data["by_grade"]} == {"Grade 4", "Grade 6"}
    assert [e["type"] for e in data["recent"]].count("approved") == 1
    assert second in [e["iep_id"] for e in data["recent"]]

    # Another educator's analytics never include these
    other = client.get("/analytics", headers=other_educator).json()
    assert other["totals"]["ieps"] == 0 and other["totals"]["students"] == 0


def test_analytics_requires_educator(client, admin):
    assert client.get("/analytics").status_code == 401
    assert client.get("/analytics", headers=admin).status_code == 403


# ═════════════════════════════════════════════════════════════════════════
# Settings
# ═════════════════════════════════════════════════════════════════════════

def test_preferences_default_then_saved(client, educator, other_educator):
    assert client.get("/settings/preferences", headers=educator).json() == {
        "default_school_name": "", "default_grade": "",
        "default_severity": "moderate", "default_language": "",
    }
    r = client.put("/settings/preferences", headers=educator, json={
        "default_school_name": "  KV Mysuru ", "default_grade": "Grade 3",
        "default_severity": "mild", "default_language": "Kannada",
    })
    assert r.status_code == 200
    saved = client.get("/settings/preferences", headers=educator).json()
    assert saved["default_school_name"] == "KV Mysuru"        # trimmed
    assert saved["default_severity"] == "mild"
    # Saved per educator
    assert client.get("/settings/preferences", headers=other_educator).json()["default_school_name"] == ""


@pytest.mark.parametrize("bad", [
    {"default_severity": "extreme"},
    {"default_school_name": "x" * 201},
])
def test_preferences_validation(client, educator, bad):
    assert client.put("/settings/preferences", headers=educator, json=bad).status_code == 422


def test_preferences_blocked_in_demo(client, educator, monkeypatch):
    import agents.model_config as mc
    monkeypatch.setattr(mc, "DEMO_MODE", True)
    assert client.put("/settings/preferences", headers=educator, json={}).status_code == 403


def test_system_info(client, educator, admin, fake_pipeline, monkeypatch):
    import app.routers.iep as iep_router
    monkeypatch.setattr(iep_router, "DAILY_LIMIT", 20)
    generate(client, educator)
    info = client.get("/settings/system", headers=educator).json()
    assert info["llm_mode"] in ("live", "replay", "demo")
    assert set(info["models"]) >= {"scraper", "compliance", "drafting", "extraction"}
    assert info["daily_limit"] == 20 and info["used_last_24h"] == 1
    assert "GOOGLE_API_KEY" not in str(info)                  # never exposes secrets
    # Admins can see it too, without usage figures
    assert client.get("/settings/system", headers=admin).json()["used_last_24h"] is None


# ═════════════════════════════════════════════════════════════════════════
# Profile
# ═════════════════════════════════════════════════════════════════════════

def test_rename_me(client, educator):
    r = client.patch("/auth/me", headers=educator, json={"full_name": "  Asha R. Teacher "})
    assert r.status_code == 200 and r.json()["full_name"] == "Asha R. Teacher"
    assert client.get("/auth/me", headers=educator).json()["full_name"] == "Asha R. Teacher"
    assert client.patch("/auth/me", headers=educator, json={"full_name": "A"}).status_code == 400


def test_rename_is_the_new_reviewer_name(client, educator, fake_pipeline):
    iep_id = generate(client, educator)
    client.patch("/auth/me", headers=educator, json={"full_name": "Asha Renamed"})
    r = client.put(f"/iep/{iep_id}/draft", headers=educator, json={"sections": {"annual_goals": "x"}})
    assert r.json()["reviewed_by"].startswith("Asha Renamed")


def test_rename_blocked_in_demo(client, educator, monkeypatch):
    import app.routers.auth as auth_router
    monkeypatch.setattr(auth_router, "DEMO_MODE", True)
    assert client.patch("/auth/me", headers=educator, json={"full_name": "New Name"}).status_code == 403


# ═════════════════════════════════════════════════════════════════════════
# PDF title
# ═════════════════════════════════════════════════════════════════════════

def test_pdf_title_is_samarth(client, educator, fake_pipeline, workdir):
    import pdfplumber
    iep_id = generate(client, educator)
    r = client.get(f"/iep/{iep_id}/download", headers=educator)
    path = workdir / "check.pdf"
    path.write_bytes(r.content)
    with pdfplumber.open(str(path)) as pdf:
        first = pdf.pages[0].extract_text()
        assert pdf.metadata.get("Title", "").startswith("SAMARTH IEP")
    top = first.splitlines()[0]
    assert top.strip() == "SAMARTH"
    assert "INDIVIDUALIZED EDUCATION PROGRAM" not in first
    assert "Individualized Education Program (IEP)" in first     # small subtitle


# ═════════════════════════════════════════════════════════════════════════
# PDF details: footer, student ID, meeting date
# ═════════════════════════════════════════════════════════════════════════

def _pdf_pages(client, headers, iep_id, workdir):
    import pdfplumber
    path = workdir / f"{iep_id}.pdf"
    path.write_bytes(client.get(f"/iep/{iep_id}/download", headers=headers).content)
    return pdfplumber.open(str(path))


def test_pdf_footer_is_honest_and_does_not_overlap(client, educator, fake_pipeline, workdir):
    iep_id = generate(client, educator)
    with _pdf_pages(client, educator, iep_id, workdir) as pdf:
        page = pdf.pages[0]
        text = page.extract_text()
        assert "Compliant with RPwD" not in text            # Section 1 has the real status
        assert "educator review required" in text
        assert " IST" in text                                 # India time, not server UTC
        # Footer: everything in the bottom 1.2 cm must not overlap horizontally
        footer = sorted((w for w in page.extract_words() if w["top"] > page.height - 34),
                        key=lambda w: w["x0"])
        assert footer
        for a, b in zip(footer, footer[1:]):
            assert a["x1"] <= b["x0"] + 0.5, f"{a['text']!r} overlaps {b['text']!r}"


def test_pdf_shows_registered_student_id(client, educator, fake_pipeline, workdir):
    s = client.post("/students", headers=educator, json={
        "full_name": "Arjun Sharma", "date_of_birth": "2016-03-14", "grade": "Grade 4",
        "school_name": "DPS Bengaluru", "disability_category": "Dyslexia",
    }).json()
    iep_id = generate(client, educator, student_code=s["student_code"])
    with _pdf_pages(client, educator, iep_id, workdir) as pdf:
        assert f"Student ID {s['student_code']}" in pdf.pages[0].extract_text()
    # The PDF made right after generation shows it too, not only rebuilds
    import glob
    first = max(glob.glob(str(workdir / "outputs" / "IEP_*.pdf")), key=lambda p: __import__("os").path.getmtime(p))
    import pdfplumber
    with pdfplumber.open(first) as pdf:
        assert s["student_code"] in pdf.pages[0].extract_text()


def test_meeting_date_does_not_change_on_rebuild(client, educator, fake_pipeline, workdir, monkeypatch):
    monkeypatch.setenv("SAMARTH_FIXED_DATE", "2026-01-15")
    iep_id = generate(client, educator)
    monkeypatch.setenv("SAMARTH_FIXED_DATE", "2026-03-01")       # weeks later…
    client.post(f"/iep/{iep_id}/finalize", headers=educator)      # …the teacher approves
    with _pdf_pages(client, educator, iep_id, workdir) as pdf:
        text = pdf.pages[0].extract_text()
    assert "Date of IEP Meeting 15 January 2026" in text
    assert "1 March 2026" not in text
