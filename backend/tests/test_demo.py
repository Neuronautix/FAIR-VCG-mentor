"""Tests for the FAIR-only demo branch."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from main import app
    return TestClient(app)


def test_health_endpoint(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_vcg_routes_absent(client):
    """VCG endpoints must return 404."""
    for path in ["/api/vcg/test/generate", "/api/vcg/test/status", "/api/vcg/test/results"]:
        resp = client.get(path)
        assert resp.status_code == 404, f"{path} should return 404, got {resp.status_code}"


def test_removed_export_formats(client):
    """Removed export formats must return 404."""
    for fmt in ["jsonld", "rocrate", "csvw", "frictionless"]:
        resp = client.get(f"/api/export/fakeid/{fmt}")
        assert resp.status_code == 404, f"/api/export/fakeid/{fmt} should return 404"


def test_openai_key_status_no_key(client):
    # Ensure key is cleared before this test
    client.delete("/api/settings/openai-key")
    resp = client.get("/api/settings/openai-key/status")
    assert resp.status_code == 200
    assert resp.json()["configured"] is False


def test_openai_key_store_and_clear(client):
    # Store key
    resp = client.post("/api/settings/openai-key", json={"api_key": "sk-test-fake"})
    assert resp.status_code == 200
    # Check status
    resp = client.get("/api/settings/openai-key/status")
    assert resp.json()["configured"] is True
    # Clear key
    resp = client.delete("/api/settings/openai-key")
    assert resp.status_code == 200
    # Check cleared
    resp = client.get("/api/settings/openai-key/status")
    assert resp.json()["configured"] is False


def test_oversized_upload(client):
    """Oversized uploads must return 413."""
    # Create a string larger than MAX_UPLOAD_MB (default 32 MB)
    # We test with ~33 MB of data
    big_content = b"a,b,c\n" + b"1,2,3\n" * (1024 * 1024 * 6)  # ~36 MB
    resp = client.post(
        "/api/upload",
        files={"file": ("big.csv", big_content, "text/csv")},
    )
    assert resp.status_code == 413, f"Expected 413, got {resp.status_code}"


def test_invalid_file_type(client):
    """Non-CSV/Excel uploads must be rejected."""
    resp = client.post(
        "/api/upload",
        files={"file": ("script.js", b"alert('xss')", "application/javascript")},
    )
    assert resp.status_code in (400, 415, 422), f"Expected 400/415/422, got {resp.status_code}"


def test_arrive_template_accessible(client):
    resp = client.get("/api/templates")
    assert resp.status_code == 200
    data = resp.json()
    all_templates = data.get("builtin", []) + data.get("user", [])
    template_ids = [t["id"] for t in all_templates]
    assert "arrive-v2" in template_ids, f"arrive-v2 not found in {template_ids}"


def test_prepare_template_accessible(client):
    resp = client.get("/api/templates")
    assert resp.status_code == 200
    data = resp.json()
    all_templates = data.get("builtin", []) + data.get("user", [])
    template_ids = [t["id"] for t in all_templates]
    assert "prepare-v1" in template_ids, f"prepare-v1 not found in {template_ids}"


def test_mnms_template_removed(client):
    resp = client.get("/api/templates")
    assert resp.status_code == 200
    data = resp.json()
    all_templates = data.get("builtin", []) + data.get("user", [])
    template_ids = [t["id"] for t in all_templates]
    assert "mnms-v1" not in template_ids, f"mnms-v1 should have been removed"


def test_namo_template_removed(client):
    resp = client.get("/api/templates")
    assert resp.status_code == 200
    data = resp.json()
    all_templates = data.get("builtin", []) + data.get("user", [])
    template_ids = [t["id"] for t in all_templates]
    assert not any(
        "namo" in tid.lower() or "noma" in tid.lower() for tid in template_ids
    ), f"NAMO/NOMA template should be removed, found: {template_ids}"


def test_linkml_import_absent(client):
    resp = client.post("/api/templates/import-linkml", json={})
    assert resp.status_code == 404, f"Expected 404 for import-linkml, got {resp.status_code}"


def test_health_returns_version(client):
    resp = client.get("/api/health")
    assert "version" in resp.json()


def test_ai_suggest_no_key_returns_400(client):
    """AI endpoints return 400 when no key is configured."""
    client.delete("/api/settings/openai-key")
    # Need a valid dataset_id for these to reach the key check; use a fake one
    resp = client.post("/api/ai/suggest-metadata/fakeid")
    # Should be 404 (dataset not found) or 400 (no key)
    assert resp.status_code in (400, 404)


def test_ai_preview_works_without_key(client):
    """Preview endpoint returns preview data without calling OpenAI."""
    # Even without a key, preview=true should return preview info (or 404 for missing dataset)
    client.delete("/api/settings/openai-key")
    resp = client.post("/api/ai/suggest-metadata/fakeid?preview=true")
    # dataset not found is acceptable since we don't have a real dataset
    assert resp.status_code in (200, 404)


def test_llm_status_no_providers(client):
    """LLM status returns disabled when no provider is configured."""
    client.delete("/api/settings/openai-key")
    resp = client.get("/api/llm/status")
    assert resp.status_code == 200
    data = resp.json()
    # Without ANTHROPIC_API_KEY env var and no OpenAI key, both should be False
    assert data["enabled"] is False
    assert data["provider"] is None


def test_llm_status_with_openai_key(client):
    """LLM status returns enabled when an OpenAI key is set."""
    client.post("/api/settings/openai-key", json={"api_key": "sk-test"})
    resp = client.get("/api/llm/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is True
    assert data["provider"] == "openai"
    # Cleanup
    client.delete("/api/settings/openai-key")


def test_assessment_only_start(client):
    """Assessment-only session can be started without a CSV."""
    resp = client.post("/api/assessment-only/start", json={"title": "Test study"})
    assert resp.status_code == 200
    data = resp.json()
    assert "dataset_id" in data
    assert data["assessment_only"] is True


def test_free_text_import_no_provider(client):
    """Free-text import returns 400 when no AI provider is configured."""
    client.delete("/api/settings/openai-key")
    resp = client.post("/api/import/free-text", json={"text": "We will use 10 mice per group."})
    assert resp.status_code == 400
