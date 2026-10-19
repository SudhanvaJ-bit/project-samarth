"""
tests/test_demo.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The online demo (SAMARTH_LLM_MODE=demo) — offline, no Gemini.

Demo mode is normally chosen when the server starts. Here it is switched on
per test with monkeypatch, against a throwaway demo folder.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import json
from datetime import date
from pathlib import Path

import pytest

import agents.model_config as mc
from models.student import StudentInput

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLES = json.loads((PROJECT_ROOT / "demo" / "samples.json").read_text(encoding="utf-8"))["samples"]


@pytest.fixture
def demo_dir(tmp_path, monkeypatch):
    """A demo folder with the real samples, all marked verified, recorded on 2026-09-27."""
    d = tmp_path / "demo"
    (d / "recordings").mkdir(parents=True)
    (d / "samples.json").write_text(json.dumps({"samples": SAMPLES}), encoding="utf-8")
    (d / "manifest.json").write_text(json.dumps({
        "recorded_on": "2026-09-27",
        "verified": [s["id"] for s in SAMPLES],
    }), encoding="utf-8")

    import app.routers.auth as auth_router
    import app.routers.iep as iep_router
    import app.main as main
    import app.services.demo as demo
    monkeypatch.delenv("SAMARTH_FIXED_DATE", raising=False)
    monkeypatch.setattr(mc, "LLM_MODE", "demo")
    monkeypatch.setattr(mc, "DEMO_MODE", True)
    monkeypatch.setattr(mc, "DEMO_DIR", d)
    monkeypatch.setattr(mc, "_RECORD_DIR", d / "recordings")
    monkeypatch.setattr(demo, "DEMO_MODE", True)
    monkeypatch.setattr(demo, "DEMO_DIR", d)
    for module in (auth_router, iep_router, main):
        monkeypatch.setattr(module, "DEMO_MODE", True)
    return d


# ═════════════════════════════════════════════════════════════════════════
# The sample students themselves
# ═════════════════════════════════════════════════════════════════════════

def test_samples_are_valid_api_input():
    assert len(SAMPLES) >= 3
    assert len({s["id"] for s in SAMPLES}) == len(SAMPLES)
    for s in SAMPLES:
        StudentInput(**s["student"])          # raises if the API would reject it


# ═════════════════════════════════════════════════════════════════════════
# Replay engine
# ═════════════════════════════════════════════════════════════════════════

def test_fixed_date_override(monkeypatch):
    monkeypatch.setenv("SAMARTH_FIXED_DATE", "2026-01-15")
    assert mc.current_date() == date(2026, 1, 15)


def test_demo_date_comes_from_manifest(demo_dir):
    assert mc.current_date() == date(2026, 9, 27)


def test_real_date_by_default(monkeypatch):
    monkeypatch.delenv("SAMARTH_FIXED_DATE", raising=False)
    monkeypatch.setattr(mc, "DEMO_MODE", False)
    assert mc.current_date() == date.today()


def test_demo_replays_a_recorded_prompt(demo_dir):
    from langchain_core.messages import HumanMessage, SystemMessage
    messages = [SystemMessage(content="sys"), HumanMessage(content="hello")]
    key = mc._recording_key("scraper", messages)
    (demo_dir / "recordings" / f"{key}.json").write_text(
        json.dumps({"role": "scraper", "model": "m", "text": "recorded answer"}), encoding="utf-8")

    response = mc.invoke_with_fallback("scraper", messages)
    assert response.content == "recorded answer"
    assert response.replayed is True


def test_demo_never_calls_gemini_for_unrecorded_prompt(demo_dir, monkeypatch):
    from langchain_core.messages import HumanMessage
    monkeypatch.setattr(mc, "generate_content_with_fallback",
                        lambda *a, **k: pytest.fail("demo mode called Gemini"))
    with pytest.raises(mc.DemoRecordingMissing):
        mc.invoke_with_fallback("scraper", [HumanMessage(content="never recorded")])


def test_embeddings_record_then_replay(tmp_path, monkeypatch):
    monkeypatch.setattr(mc, "_RECORD_DIR", tmp_path)
    monkeypatch.setattr(mc, "LLM_MODE", "live")
    monkeypatch.setattr(mc, "DEMO_MODE", False)
    assert mc.embed_with_recording("q", "model", "RETRIEVAL_QUERY", lambda: [0.1, 0.2]) == [0.1, 0.2]

    # Now in demo mode the same query replays without calling compute()
    monkeypatch.setattr(mc, "LLM_MODE", "demo")
    monkeypatch.setattr(mc, "DEMO_MODE", True)
    replayed = mc.embed_with_recording("q", "model", "RETRIEVAL_QUERY",
                                       lambda: pytest.fail("demo mode called Gemini"))
    assert replayed == [0.1, 0.2]

    with pytest.raises(mc.DemoRecordingMissing):
        mc.embed_with_recording("other query", "model", "RETRIEVAL_QUERY", lambda: [9.9])


def test_no_api_key_gives_clear_error(monkeypatch):
    monkeypatch.setattr(mc, "_client", None)
    with pytest.raises(RuntimeError, match="GOOGLE_API_KEY"):
        mc.get_client()


# ═════════════════════════════════════════════════════════════════════════
# API behaviour in demo mode
# ═════════════════════════════════════════════════════════════════════════

def test_demo_info_is_public(client, demo_dir):
    data = client.get("/demo").json()
    assert data["enabled"] is True
    assert data["recorded_on"] == "2026-09-27"
    assert data["login"]["email"]
    assert [s["id"] for s in data["samples"]] == [s["id"] for s in SAMPLES]


def test_unverified_samples_are_hidden(client, demo_dir):
    (demo_dir / "manifest.json").write_text(json.dumps({
        "recorded_on": "2026-09-27", "verified": [SAMPLES[0]["id"]]}), encoding="utf-8")
    ids = [s["id"] for s in client.get("/demo").json()["samples"]]
    assert ids == [SAMPLES[0]["id"]]


def test_demo_off_by_default(client):
    assert client.get("/demo").json() == {"enabled": False}


def test_demo_account_login(client, demo_dir):
    from app.services import demo
    demo.ensure_demo_account()
    demo.ensure_demo_account()          # safe to run on every startup
    r = client.post("/auth/login", data={"username": demo.DEMO_EMAIL,
                                         "password": demo.DEMO_PASSWORD})
    assert r.status_code == 200
    assert r.json()["user"]["role"] == "educator"


def test_demo_generates_sample(client, demo_dir, educator, fake_pipeline):
    r = client.post("/iep/generate", json=SAMPLES[0]["student"], headers=educator)
    assert r.status_code == 201, r.text
    assert r.json()["workflow_status"] == "Completed"


def test_demo_rejects_edited_sample_before_running(client, demo_dir, educator, fake_pipeline):
    edited = {**SAMPLES[0]["student"], "raw_notes": SAMPLES[0]["student"]["raw_notes"] + " Edited."}
    r = client.post("/iep/generate", json=edited, headers=educator)
    assert r.status_code == 422
    assert "sample" in r.json()["detail"]
    assert fake_pipeline == []


def test_demo_blocks_pdf_upload(client, demo_dir, educator):
    r = client.post("/iep/generate-from-report", headers=educator,
                    files={"file": ("report.pdf", b"%PDF-1.4", "application/pdf")})
    assert r.status_code == 403


def test_demo_blocks_password_change(client, demo_dir, educator):
    r = client.post("/auth/me/password", headers=educator,
                    json={"current_password": "correct-horse-battery",
                          "new_password": "something-else"})
    assert r.status_code == 403


def test_health_reports_demo_mode(client, demo_dir):
    assert client.get("/iep/health").json()["demo_mode"] is True
