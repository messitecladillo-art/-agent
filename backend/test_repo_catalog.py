"""Contract tests for the allowlisted repository workspace catalogue."""

from pathlib import Path

from fastapi.testclient import TestClient

try:  # pytest from the backend directory
    import app as api
    from repo_catalog import WorkspaceCatalog
except ImportError:  # pragma: no cover - package-style collection
    from backend import app as api
    from backend.repo_catalog import WorkspaceCatalog


def _fixture_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "docs" / "guide").mkdir(parents=True)
    (root / "skills").mkdir()
    (root / "notes").mkdir()
    (root / "README.md").write_text("workspace catalog overview", encoding="utf-8")
    (root / "TASKS.md").write_text("T07 repository context", encoding="utf-8")
    (root / "AGENTS.md").write_text("allowlisted routing", encoding="utf-8")
    (root / "docs" / "guide" / "retrieval.md").write_text("bounded lexical search and source refs", encoding="utf-8")
    (root / "skills" / "routing.py").write_text("# do not execute\n", encoding="utf-8")
    (root / "notes" / "private.txt").write_text("excluded by path? no, notes is allowlisted", encoding="utf-8")
    (root / "backend").mkdir()
    (root / "backend" / "secret.py").write_text("not indexed", encoding="utf-8")
    (root / ".env").write_text("NOPE=1", encoding="utf-8")
    return root


def test_catalog_is_allowlisted_and_manifested(tmp_path):
    root = _fixture_root(tmp_path)
    result = WorkspaceCatalog(root).catalog()
    paths = {item["path_rel"] for item in result["items"]}
    assert "README.md" in paths
    assert "docs/guide/retrieval.md" in paths
    assert "skills/routing.py" in paths
    assert "backend/secret.py" not in paths
    assert ".env" not in paths
    assert result["manifest_sha"].startswith("sha256:")
    assert result["counts"]["items"] == len(result["items"])
    assert all(ref.startswith("repo:") for ref in result["source_refs"])
    assert all(not Path(row["path"]).is_absolute() for row in result["items"])


def test_search_returns_bounded_body_hits_and_source_refs(tmp_path):
    root = _fixture_root(tmp_path)
    result = WorkspaceCatalog(root).search("source refs", top_k=3)
    assert result["schema_version"] == "workspace-search/v1"
    assert result["results"]
    hit = result["results"][0]
    assert hit["match_source"] == "body"
    assert "source refs" in hit["snippet"]
    assert result["source_refs"] == [hit["source_ref"]]
    assert result["retrieval_boundary"]["allowlist_only"] is True


def test_empty_search_is_explicit_browse_and_path_filter_is_safe(tmp_path):
    root = _fixture_root(tmp_path)
    browse = WorkspaceCatalog(root).search("", top_k=2)
    assert browse["returned_count"] == 2
    assert all(row["match_source"] == "browse" for row in browse["results"])
    filtered = WorkspaceCatalog(root).search("", path="docs")
    assert filtered["results"]
    assert all(row["path_rel"].startswith("docs/") for row in filtered["results"])


def test_project_api_rejects_traversal_and_exposes_catalog(tmp_path, monkeypatch):
    previous = api.workspace_catalog
    monkeypatch.setattr(api, "workspace_catalog", WorkspaceCatalog(_fixture_root(tmp_path)))
    try:
        client = TestClient(api.app)
        catalog = client.get(f"/api/projects/{api.PROJECT_ID}/workspace/catalog")
        assert catalog.status_code == 200
        assert catalog.json()["schema_version"] == "workspace-catalog/v1"
        search = client.get(f"/api/projects/{api.PROJECT_ID}/workspace/search", params={"q": "routing", "path": "../"})
        assert search.status_code == 400
        assert client.get("/api/projects/not-this-project/workspace/catalog").status_code == 404
    finally:
        monkeypatch.setattr(api, "workspace_catalog", previous)
