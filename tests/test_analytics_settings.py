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
