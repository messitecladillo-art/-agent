"""HTTP and boundary tests for the repository Skill Registry v2."""

from fastapi.testclient import TestClient

import app as api


def test_skill_catalog_is_versioned_and_read_only():
    body = TestClient(api.app).get(
        f"/api/projects/{api.PROJECT_ID}/skills/catalog"
    )
    assert body.status_code == 200
    payload = body.json()
    assert payload["schema_version"] == "skill-registry/v2"
    assert payload["registry_revision"].startswith("skill:")
    assert payload["counts"]["skills"] == 13
    assert payload["counts"]["workflows"] == 3
    assert payload["counts"]["sources"] == 12
    assert payload["source_provenance"]["inventory_revision"] == "materials-inventory:2026-08-31"
    assert all("manifest" in row and row["status"] == "ACTIVE" for row in payload["skills"])


def test_skill_search_is_bounded_and_does_not_expose_absolute_paths():
    response = TestClient(api.app).get(
        f"/api/projects/{api.PROJECT_ID}/skills/search",
        params={"q": "数学 推导", "limit": 3},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["registry_revision"].startswith("skill:")
    assert len(payload["results"]) <= 3
    assert any(row["id"] == "mathematical-derivation" for row in payload["results"])
    for row in payload["results"]:
        assert not str(row["path"]).startswith(("C:", "/", "\\"))
        assert ".." not in str(row["path"])


def test_skill_detail_returns_manifest_and_bounded_preview():
    response = TestClient(api.app).get(
        f"/api/projects/{api.PROJECT_ID}/skills/model-routing"
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["entry"]["id"] == "model-routing"
    assert payload["manifest"]["schema_version"] == "skill-manifest/v2"
    assert payload["read_only"] is True
    assert payload["execution"] == "not_performed"
    assert len(payload["preview"]) <= 500


def test_skill_detail_rejects_unknown_id():
    response = TestClient(api.app).get(
        f"/api/projects/{api.PROJECT_ID}/skills/not-a-real-skill"
    )
    assert response.status_code == 404


def test_capability_catalog_carries_skill_registry_revision():
    response = TestClient(api.app).get(
        f"/api/projects/{api.PROJECT_ID}/capabilities/catalog"
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["skill_registry_revision"].startswith("skill:")
    assert payload["source"]["skill_registry"]["status"] == "READY"
    assert payload["source"]["skill_binding"]["status"] == "READY"
    assert payload["source"]["skill_binding"]["fully_bound"] == len(payload["methods"])
    route = next(item for item in payload["methods"] if item["id"] == "linear-programming")
    assert "model-routing" in route["skill_refs"]
    assert route["skill_binding_status"] == "BOUND"
