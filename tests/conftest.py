"""
tests/conftest.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Shared setup for the whole test suite. pytest loads this file first,
before any test file, so the settings below are in place before the app
is imported.

WHAT IT GUARANTEES
1. Offline tests never touch your real data. The user database is a
   throwaway SQLite file in a temporary folder, and every offline test runs
   inside its own empty folder, so drafts/ and outputs/ are created there —
   not in the project.
2. Live Gemini tests are skipped by default. They are slow and spend API
   quota. Run them only when you mean to:
       pytest --live
3. Ready-made logged-in users for API tests (see the fixtures below).

RUN
    pytest                 # fast offline suite (about a minute)
    pytest --live          # also the real-Gemini tests (several minutes)
    pytest tests/test_api.py -v
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ── Environment — must be set BEFORE any app module is imported ──────────
# Load the real .env first (live tests need the real GOOGLE_API_KEY), then
# override the settings that must never point at real data.
from dotenv import load_dotenv  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")

_TEST_TMP = Path(tempfile.mkdtemp(prefix="samarth-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TEST_TMP / 'test_users.db').as_posix()}"
os.environ["JWT_SECRET"]   = "test-only-secret-not-used-anywhere-else-0123456789"
os.environ.setdefault("GOOGLE_API_KEY", "test-dummy-key")   # offline tests never call Gemini


# ── Live-test switch ─────────────────────────────────────────────────────

# Tests that call the real Gemini API. Listed here in one place so the
# individual test files stay unchanged and runnable as scripts.
LIVE_TESTS = {
    "test_compliance.py":  "*",
    "test_drafting.py":    "*",
    "test_scraper.py":     "*",
    "test_graph.py":       {"test_full_pipeline_run"},
    "test_integration.py": {"test_dyslexia_pipeline", "test_asd_pipeline",
                            "test_transition_planning_at_14", "test_pdf_files_exist"},
}


def pytest_addoption(parser):
    parser.addoption("--live", action="store_true", default=False,
                     help="Also run tests that call the real Gemini API.")


def pytest_collection_modifyitems(config, items):
    run_live = config.getoption("--live")
    skip_live = pytest.mark.skip(reason="calls the real Gemini API — run with: pytest --live")
    for item in items:
        names = LIVE_TESTS.get(Path(str(item.fspath)).name)
        if names and (names == "*" or item.originalname in names):
            item.add_marker(pytest.mark.live)
            if not run_live:
                item.add_marker(skip_live)


# ── Fixtures for API tests ───────────────────────────────────────────────

PASSWORD = "correct-horse-battery"


@pytest.fixture(autouse=True)
def workdir(request, tmp_path, monkeypatch):
    """
    Every offline test runs inside its own empty folder, so anything written
    to drafts/ or outputs/ lands there and is thrown away afterwards.
    Live tests keep the project folder, as before.
    """
    if request.node.get_closest_marker("live") is None:
        monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def db():
    """A fresh, empty user table for every test."""
    from sqlmodel import SQLModel
    from app.db import engine, init_db

    SQLModel.metadata.drop_all(engine)
    init_db()
    yield engine


@pytest.fixture
def client(workdir, db):
    """
    An HTTP client for the app.
    Not used as a context manager on purpose: that would run the startup
    hook, which loads the ChromaDB index — not needed for API tests.
    """
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


@pytest.fixture
def make_user(db):
    """make_user(email, role="educator", password=PASSWORD) → User"""
    from sqlmodel import Session
    from app.services.auth import create_user

    def _make(email, role="educator", password=PASSWORD, full_name=None):
        with Session(db) as session:
            return create_user(session, email, full_name or email.split("@")[0].title(),
                               password, role)
    return _make


@pytest.fixture
def login(client):
    """login(email, password=PASSWORD) → {"Authorization": "Bearer …"}"""
    def _login(email, password=PASSWORD):
        r = client.post("/auth/login", data={"username": email, "password": password})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}
    return _login


@pytest.fixture
def educator(make_user, login):
    make_user("teacher@school.test", "educator", full_name="Asha Teacher")
    return login("teacher@school.test")


@pytest.fixture
def other_educator(make_user, login):
    make_user("other@school.test", "educator", full_name="Ravi Other")
    return login("other@school.test")


@pytest.fixture
def admin(make_user, login):
    make_user("admin@school.test", "admin", full_name="Admin User")
    return login("admin@school.test")


# ── A stand-in for the AI pipeline ───────────────────────────────────────

def _fake_pipeline(student_data: dict, iep_id: str = None) -> dict:
    """
    Returns what the real pipeline returns, without calling Gemini.
    The PDF is built by the real ReportLab code, so download and finalize
    are tested against a genuine file.
    """
    from agents.state import ComplianceStatus, WorkflowStatus
    from app.services.draft_store import EDITABLE_SECTIONS
    from pdf_generator.iep_pdf import generate_iep_pdf

    profile = {
        "student_name":        student_data["student_name"],
        "age":                 student_data["age"],
        "grade":               student_data["grade"],
        "school_name":         student_data["school_name"],
        "disability_category": student_data["disability_category"],
        "disability_severity": student_data["disability_severity"].title(),
        "dominant_language":   "English",
    }
    drafted = {"background_info": f"Background for {profile['student_name']}."}
    drafted.update({key: f"AI draft of {label}." for key, label in EDITABLE_SECTIONS})

    state = {
        "student_id":        iep_id,
        "iep_id":            iep_id,
        "student_profile":   profile,
        "drafted_iep":       drafted,
        "compliance_report": {
            "status":                   ComplianceStatus.PARTIAL,
            "mandatory_accommodations": ["25% extra exam time"],
            "rpwd_relevant_sections":   ["Section 16"],
            "compliance_notes":         "Test compliance notes.",
        },
        "workflow_status":   WorkflowStatus.COMPLETED,
        "generated_at":      "2026-01-01T00:00:00+00:00",
        "error_log":         [],
    }
    state["pdf_output_path"] = generate_iep_pdf(state, output_dir="outputs")
    return state


@pytest.fixture
def fake_pipeline(monkeypatch):
    """Replace the Gemini pipeline with _fake_pipeline for this test."""
    import app.routers.iep as iep_router
    calls = []

    def _run(student_data, iep_id=None):
        calls.append(student_data)
        return _fake_pipeline(student_data, iep_id)

    monkeypatch.setattr(iep_router, "run_iep_pipeline", _run)
    return calls
