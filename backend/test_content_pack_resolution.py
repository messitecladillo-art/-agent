"""API/unit coverage for source-bound content-pack resolution."""

from pathlib import Path

from fastapi.testclient import TestClient

try:  # pytest from the repository root
    import app as api
    from knowledge_base import KnowledgeBase
except ImportError:  # pragma: no cover - package-style collection
    from backend import app as api
    from backend.knowledge_base import KnowledgeBase


def _temporary_client(tmp_path, monkeypatch):
    root = tmp_path / "pack"
    module = root / "06_论文写作与备赛模块"
    module.mkdir(parents=True)
    (module / "范文_敏感性分析.md").write_text(
        "敏感性分析、误差边界、适用条件与反例；结果需要独立验证。",
        encoding="utf-8",
    )
    # A synchronising file must influence coverage status but must never be
    # returned as a search result or opened by the resolver.
    (root / "unfinished.qkdownloading").write_text("partial", encoding="utf-8")
    previous = api.knowledge_base
    monkeypatch.setattr(api, "knowledge_base", KnowledgeBase(str(root)))
    return TestClient(api.app), previous


def test_catalog_content_pack_exposes_pending_coverage_and_safe_resolver(tmp_path, monkeypatch):
    client, previous = _temporary_client(tmp_path, monkeypatch)
    try:
        response = client.get(f"/api/projects/{api.PROJECT_ID}/capabilities/catalog")
        assert response.status_code == 200
        pack = next(item for item in response.json()["content_packs"] if item["id"] == "counterexample")
        assert pack["claim_class"] == "hypothesis"
        assert pack["evidence_refs"] == []
        assert pack["coverage_state"] == "PARTIAL_PENDING"
        assert pack["coverage"]["index_revision"].startswith("kb:")
        assert pack["resolve_endpoint"].endswith("/counterexample/resolve")
    finally:
        monkeypatch.setattr(api, "knowledge_base", previous)


def test_resolve_binds_current_index_citations_and_relative_paths(tmp_path, monkeypatch):
    client, previous = _temporary_client(tmp_path, monkeypatch)
    try:
        response = client.get(
            f"/api/projects/{api.PROJECT_ID}/capabilities/content-packs/counterexample/resolve",
            params={"top_k": 1, "with_preview": "true"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["schema_version"] == "content-pack-resolution/v1"
        assert body["query_source"] == "pack_default"
        assert body["index_revision"].startswith("kb:")
        assert body["source_status"] == "LOCAL_PENDING"
        assert body["coverage_state"] == "PARTIAL_PENDING"
        assert body["coverage"]["evidence_ref_count"] == 1
        assert body["evidence_refs"] == body["citation_refs"]
        assert body["results"]
        hit = body["results"][0]
        assert hit["citation_ref"].startswith("kbdoc:kbdoc_")
        assert hit["evidence_ref"] == hit["citation_ref"]
        assert hit["index_revision"] == body["index_revision"]
        assert hit["claim_class"] == "observed"
        assert hit["applicability_claim_class"] == "hypothesis"
        assert hit["usage"]
        assert hit["extract_status"] == "TEXT_EXTRACTED"
        assert hit["path"] == hit["path_rel"]
        assert not Path(hit["path"]).is_absolute()
        assert ".." not in hit["path"].replace("\\", "/").split("/")
        assert "页级" in " ".join(body["warnings"])
    finally:
        monkeypatch.setattr(api, "knowledge_base", previous)


def test_resolve_supports_query_override_and_rejects_unknown_or_unsafe_pack(tmp_path, monkeypatch):
    client, previous = _temporary_client(tmp_path, monkeypatch)
    try:
        overridden = client.get(
            "/api/capabilities/content-packs/counterexample/resolve",
            params={"q": "敏感性分析", "top_k": 1},
        )
        assert overridden.status_code == 200
        assert overridden.json()["query"] == "敏感性分析"
        assert overridden.json()["query_source"] == "override"

        unknown = client.get(
            f"/api/projects/{api.PROJECT_ID}/capabilities/content-packs/not-a-pack/resolve"
        )
        assert unknown.status_code == 404
        assert unknown.json()["detail"]["code"] == "CONTENT_PACK_NOT_FOUND"

        traversal = client.get(
            f"/api/projects/{api.PROJECT_ID}/capabilities/content-packs/%2e%2e%2fresolve"
        )
        assert traversal.status_code in {404, 405}
    finally:
        monkeypatch.setattr(api, "knowledge_base", previous)


def test_compose_carries_content_pack_coverage_without_resolving_files(tmp_path, monkeypatch):
    client, previous = _temporary_client(tmp_path, monkeypatch)
    try:
        catalog = client.get(f"/api/projects/{api.PROJECT_ID}/capabilities/catalog").json()
        payload = {
            "nodes": [
                {"node_id": "q", "block_id": "problem-decomposition"},
                {"node_id": "data", "block_id": "data-audit"},
                {"node_id": "base", "block_id": "baseline-model", "method_id": "linear-regression"},
                {"node_id": "check", "block_id": "validation"},
                {"node_id": "paper", "block_id": "writing"},
            ],
            "edges": [
                {"source": "q", "source_port": "subproblems", "target": "data", "target_port": "subproblems"},
                {"source": "q", "source_port": "subproblems", "target": "base", "target_port": "subproblem"},
                {"source": "data", "source_port": "data_contract", "target": "base", "target_port": "data_contract"},
                {"source": "base", "source_port": "model", "target": "check", "target_port": "model"},
                {"source": "base", "source_port": "result", "target": "check", "target_port": "result"},
                {"source": "q", "source_port": "subproblems", "target": "paper", "target_port": "subproblems"},
                {"source": "base", "source_port": "result", "target": "paper", "target_port": "result"},
                {"source": "check", "source_port": "validation_report", "target": "paper", "target_port": "validation_report"},
            ],
            "content_pack_ids": ["counterexample"],
            "base_revision": catalog["capability_revision"],
            "idempotency_key": "content-pack-compose-temp-1",
        }
        response = client.post(f"/api/projects/{api.PROJECT_ID}/capabilities/compose", json=payload)
        assert response.status_code == 200
        body = response.json()
        assert body["content_pack_evidence_refs"] == []
        assert body["content_pack_coverage"]["counterexample"]["state"] == "PARTIAL_PENDING"
        assert body["content_packs"][0]["coverage_state"] == "PARTIAL_PENDING"
    finally:
        monkeypatch.setattr(api, "knowledge_base", previous)


def test_compose_can_carry_resolver_refs_only_at_same_index_revision(tmp_path, monkeypatch):
    client, previous = _temporary_client(tmp_path, monkeypatch)
    try:
        catalog = client.get(f"/api/projects/{api.PROJECT_ID}/capabilities/catalog").json()
        resolved = client.get(
            f"/api/projects/{api.PROJECT_ID}/capabilities/content-packs/counterexample/resolve",
            params={"top_k": 1},
        ).json()
        # Keep the graph intentionally tiny here; the existing composition
        # contract test covers all typed edges.  This assertion focuses on
        # source binding and revision fencing.
        payload = {
            "nodes": [
                {"node_id": "q", "block_id": "problem-decomposition"},
                {"node_id": "data", "block_id": "data-audit"},
                {"node_id": "base", "block_id": "baseline-model"},
                {"node_id": "check", "block_id": "validation"},
                {"node_id": "paper", "block_id": "writing"},
            ],
            "edges": [
                {"source": "q", "source_port": "subproblems", "target": "data", "target_port": "subproblems"},
                {"source": "q", "source_port": "subproblems", "target": "base", "target_port": "subproblem"},
                {"source": "data", "source_port": "data_contract", "target": "base", "target_port": "data_contract"},
                {"source": "base", "source_port": "model", "target": "check", "target_port": "model"},
                {"source": "base", "source_port": "result", "target": "check", "target_port": "result"},
                {"source": "q", "source_port": "subproblems", "target": "paper", "target_port": "subproblems"},
                {"source": "base", "source_port": "result", "target": "paper", "target_port": "result"},
                {"source": "check", "source_port": "validation_report", "target": "paper", "target_port": "validation_report"},
            ],
            "content_pack_ids": ["counterexample"],
            "content_pack_evidence_refs": resolved["evidence_refs"],
            "content_pack_index_revision": resolved["index_revision"],
            "content_pack_resolution_revision": resolved["resolution_revision"],
            "base_revision": catalog["capability_revision"],
            "idempotency_key": "content-pack-bound-compose-1",
        }
        response = client.post(f"/api/projects/{api.PROJECT_ID}/capabilities/compose", json=payload)
        assert response.status_code == 200
        body = response.json()
        assert body["content_pack_evidence_state"] == "BOUND_CANDIDATE"
        assert body["content_pack_evidence_refs"] == resolved["evidence_refs"]
        assert body["content_pack_index_revision"] == resolved["index_revision"]

        payload["content_pack_index_revision"] = "kb:" + "f" * 64
        stale = client.post(f"/api/projects/{api.PROJECT_ID}/capabilities/compose", json=payload)
        assert stale.status_code == 409
        assert stale.json()["detail"]["code"] == "CONTENT_PACK_INDEX_REVISION_STALE"
    finally:
        monkeypatch.setattr(api, "knowledge_base", previous)
