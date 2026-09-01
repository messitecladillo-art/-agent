"""API contract tests for the LaTeX/PDF live compiler surface."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend import app as api


def test_toolchain_endpoint_is_explicit_and_project_scoped():
    client = TestClient(api.app)

    response = client.get(f"/api/projects/{api.PROJECT_ID}/latex/toolchain")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"AVAILABLE", "UNAVAILABLE"}
    assert "available" in payload
    assert "default_entrypoint" in payload
    assert str(api.ROOT) not in response.text
    assert client.get("/api/projects/not-this-project/latex/toolchain").status_code == 404


def test_compile_requires_a_current_revision_and_returns_a_job(monkeypatch):
    client = TestClient(api.app)
    revision = client.get(f"/api/projects/{api.PROJECT_ID}/snapshot").json()["revision"]
    # The checkout intentionally has no paper/main.tex fixture.  Stub only the
    # input gate so this test exercises queue/event semantics without creating a
    # synthetic paper in the user's repository.
    monkeypatch.setattr(api.latex_compiler, "validate_entrypoint", lambda _entrypoint: api.ROOT / "paper" / "main.tex")

    response = client.post(
        f"/api/projects/{api.PROJECT_ID}/latex/compile",
        json={
            "entrypoint": "paper/main.tex",
            "compiler": "auto",
            "engine": "auto",
            "clean": True,
            "base_revision": revision,
            "idempotency_key": "test-latex-api-queue-001",
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "QUEUED"
    assert payload["job_id"].startswith("latex-")
    assert payload["event"]["type"] == "LATEX_COMPILE_QUEUED"
    assert client.get(
        f"/api/projects/{api.PROJECT_ID}/latex/jobs/{payload['job_id']}"
    ).status_code in {200, 404}


def test_compile_rejects_stale_or_malformed_revision():
    client = TestClient(api.app)

    response = client.post(
        f"/api/projects/{api.PROJECT_ID}/latex/compile",
        json={
            "entrypoint": "paper/main.tex",
            "base_revision": "not-a-revision",
            "idempotency_key": "test-latex-api-invalid-revision-001",
        },
    )

    assert response.status_code == 422


def test_compile_rejects_absolute_or_missing_entrypoint_before_event():
    client = TestClient(api.app)
    revision = client.get(f"/api/projects/{api.PROJECT_ID}/snapshot").json()["revision"]

    response = client.post(
        f"/api/projects/{api.PROJECT_ID}/latex/compile",
        json={
            "entrypoint": str(api.ROOT / "paper" / "main.tex"),
            "base_revision": revision,
            "idempotency_key": "test-latex-api-unsafe-entrypoint-001",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_ENTRYPOINT"


def test_compile_same_idempotency_key_reuses_job(monkeypatch):
    client = TestClient(api.app)
    revision = client.get(f"/api/projects/{api.PROJECT_ID}/snapshot").json()["revision"]
    monkeypatch.setattr(api.latex_compiler, "validate_entrypoint", lambda _entrypoint: api.ROOT / "paper" / "main.tex")
    body = {
        "entrypoint": "paper/main.tex",
        "base_revision": revision,
        "idempotency_key": "test-latex-api-replay-001",
    }

    first = client.post(f"/api/projects/{api.PROJECT_ID}/latex/compile", json=body)
    second = client.post(f"/api/projects/{api.PROJECT_ID}/latex/compile", json=body)

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["job_id"] == second.json()["job_id"]
