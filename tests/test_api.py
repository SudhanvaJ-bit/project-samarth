import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from agents.state import WorkflowStatus, ComplianceStatus

def make_mock_final_state(iep_id: str):
    return {
        "workflow_status":   WorkflowStatus.COMPLETED,
        "compliance_report": {"status": ComplianceStatus.PARTIAL},
        "pdf_output_path":   f"outputs/IEP_Test_{iep_id[:8]}.pdf",
        "generated_at":      "2026-01-01T00:00:00+00:00",
        "error_log":         [],
        "drafted_iep":       {"background_info": "Test IEP"},
    }


VALID_PAYLOAD = {
    "student_name":         "Arjun Sharma",
    "age":                  10,
    "grade":                "Grade 4",
    "school_name":          "Delhi Public School, Bengaluru",
    "disability_category":  "Dyslexia",
    "disability_severity":  "moderate",
    "raw_notes":            (
        "Arjun struggles with reading and written expression. "
        "He reverses letters and has difficulty with comprehension. "
        "He excels in oral discussions and mathematics."
    ),
    "academic_history":     "Grade 3: 62% overall",
    "teacher_observations": "Engaged in group work, struggles with writing",
    "parent_concerns":      "Gets frustrated with reading tasks at home",
}


def get_test_client():
    """Create TestClient with mocked pipeline."""
    from app.main import app
    return TestClient(app)


def test_root_endpoint():
    """GET / returns project info."""
    print("\n🌐 Test 1: Root endpoint...")
    client = get_test_client()

    response = client.get("/")
    assert response.status_code == 200

    data = response.json()
    assert data["project"]    == "Project SAMARTH"
    assert data["version"]    == "1.0.0"
    assert "generate"         in data["endpoints"]
    print(f"  ✅ Status: {response.status_code}")
    print(f"  ✅ Project: {data['project']} v{data['version']}")


def test_health_endpoint():
    """GET /iep/health returns ok."""
    print("\n🌐 Test 2: Health endpoint...")
    client = get_test_client()

    response = client.get("/iep/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    print(f"  ✅ Health: {response.json()}")


def test_generate_iep_success():
    """POST /iep/generate returns 201 with mocked pipeline."""
    print("\n🌐 Test 3: Generate IEP (mocked pipeline)...")
    client = get_test_client()

    with patch("app.routers.iep.run_iep_pipeline") as mock_pipeline:
        mock_pipeline.return_value = make_mock_final_state("test-1234-5678")

        response = client.post("/iep/generate", json=VALID_PAYLOAD)

        assert response.status_code == 201, \
            f"Expected 201, got {response.status_code}: {response.text}"

        data = response.json()
        assert data["student_name"]    == "Arjun Sharma"
        assert data["workflow_status"] == "WorkflowStatus.COMPLETED"
        assert data["iep_id"]          is not None
        assert "download" in data["message"]

        print(f"  ✅ Status code    : {response.status_code}")
        print(f"  ✅ IEP ID         : {data['iep_id']}")
        print(f"  ✅ Student        : {data['student_name']}")
        print(f"  ✅ Workflow status: {data['workflow_status']}")
        print(f"  ✅ Message        : {data['message'][:60]}...")


def test_generate_iep_missing_fields():
    """POST /iep/generate returns 422 on missing required fields."""
    print("\n🌐 Test 4: Missing required fields...")
    client = get_test_client()

    bad_payload = {"student_name": "Test"}
    response    = client.post("/iep/generate", json=bad_payload)

    assert response.status_code == 422
    print(f"  ✅ Correctly rejected: {response.status_code} Unprocessable Entity")


def test_generate_iep_short_notes():
    """POST /iep/generate returns 422 when raw_notes too short."""
    print("\n🌐 Test 5: Notes too short...")
    client = get_test_client()

    short_payload = {**VALID_PAYLOAD, "raw_notes": "Too short"}
    response      = client.post("/iep/generate", json=short_payload)

    assert response.status_code == 422
    print(f"  ✅ Correctly rejected: notes too short → {response.status_code}")


def test_download_not_found():
    """GET /iep/{id}/download returns 404 for unknown ID."""
    print("\n🌐 Test 6: Download unknown IEP...")
    client = get_test_client()

    response = client.get("/iep/nonexistent-id-xyz/download")
    assert response.status_code == 404
    print(f"  ✅ Correctly returned: {response.status_code} Not Found")


def test_invalid_disability_category():
    """POST /iep/generate returns 422 for unknown disability."""
    print("\n🌐 Test 7: Invalid disability category...")
    client = get_test_client()

    bad_payload = {**VALID_PAYLOAD, "disability_category": "InvalidDisease"}
    response    = client.post("/iep/generate", json=bad_payload)

    assert response.status_code == 422
    print(f"  ✅ Correctly rejected: {response.status_code}")


def test_docs_available():
    """GET /docs returns Swagger UI."""
    print("\n🌐 Test 8: Swagger docs available...")
    client = get_test_client()

    response = client.get("/docs")
    assert response.status_code == 200
    print(f"  ✅ Swagger UI available at /docs")


if __name__ == "__main__":
    print("\n🧪 Running FastAPI Tests...\n")
    test_root_endpoint()
    test_health_endpoint()
    test_generate_iep_success()
    test_generate_iep_missing_fields()
    test_generate_iep_short_notes()
    test_download_not_found()
    test_invalid_disability_category()
    test_docs_available()
    print("\n🎉 ALL API TESTS PASSED — Step 10 Complete!\n")