"""HTTP contract tests for the read-only capability layer."""

from fastapi.testclient import TestClient

import app as api


def _summary():
    return {
        "root_id": "math-modeling-pack",
        "source_status": "LOCAL_INDEXED",
        "index_revision": "kb:" + "a" * 64,
        "indexed_count": 12,
        "valid_count": 12,
        "catalog_consistent": False,
        "facets": {"modules": {"01_国赛资料模块": 8}, "kinds": {"paper": 4, "code": 3, "template": 2}, "extensions": {".pdf": 8}, "years": {"2024": 2}},
        "warnings": ["metadata test snapshot"],
    }


def client(monkeypatch):
    monkeypatch.setattr(api, "store", api.EventStore())
    monkeypatch.setattr(api.knowledge_base, "summary", lambda force_refresh=False: dict(_summary()))
    return TestClient(api.app)


def test_catalog_exposes_source_boundary_and_playbook_cards(monkeypatch):
    response = client(monkeypatch).get(f"/api/projects/{api.PROJECT_ID}/capabilities/catalog")
    assert response.status_code == 200
    body = response.json()
    assert body["catalog_version"] == "capability-catalog/v1"
    assert body["source"]["coverage"] == "metadata_plus_curated_playbook"
    assert body["source"]["asset_signals"]["paper_candidates"] == 4
    assert len(body["methods"]) >= 12
    assert all(item["source_kind"] == "curated/inferred" for item in body["methods"])
    assert body["capability_revision"].startswith("cap:")


def test_catalog_exposes_typed_method_choices_for_all_puzzle_kinds(monkeypatch):
    c = client(monkeypatch)
    body = c.get(f"/api/projects/{api.PROJECT_ID}/capabilities/catalog").json()
    methods = body["methods"]
    kinds = {kind for method in methods for kind in method.get("compatible_block_kinds", [])}
    workflow_kinds = {block["kind"] for block in body["workflow_blocks"]}
    assert workflow_kinds <= kinds
    required_fields = {
        "applicability", "prohibitions", "assumptions", "inputs", "outputs",
        "validation", "fallback", "evidence_refs", "compatible_block_kinds",
    }
    assert all(required_fields <= set(method) for method in methods)
    # Spot-check the categories that were previously absent from the catalog.
    families = {method["family"] for method in methods}
    assert {"problem", "data", "contract", "review", "writing", "defense"} <= families


def test_suggest_is_transparent_and_fail_closed(monkeypatch):
    response = client(monkeypatch).get(f"/api/projects/{api.PROJECT_ID}/capabilities/suggest", params={"q": "带约束的调度优化", "limit": 4})
    assert response.status_code == 200
    body = response.json()
    assert body["archetypes"][0]["id"] == "optimization"
    assert body["archetypes"][0]["claim_class"] == "inferred"
    assert body["methods"][0]["claim_class"] == "hypothesis"
    assert body["warnings"]


def _valid_payload(base_revision=None):
    return {
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
        "preset_id": "data-to-paper",
        "archetype_id": "prediction",
        "scope": ["Q1"],
        "base_revision": base_revision or "cap:" + "b" * 64,
        "idempotency_key": "compose-api-1",
    }


def test_compose_returns_assembly_revision_and_status(monkeypatch):
    c = client(monkeypatch)
    catalog = c.get(f"/api/projects/{api.PROJECT_ID}/capabilities/catalog").json()
    response = c.post(f"/api/projects/{api.PROJECT_ID}/capabilities/compose", json=_valid_payload(catalog["capability_revision"]))
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "READY_FOR_REVIEW"
    assert body["assembly_revision"].startswith("assembly:")
    assert body["validation"]["valid"] is True
    assert body["composition"]["nodes"][2]["claim_class"] == "hypothesis"


def test_compose_rejects_stale_catalog_and_unknown_method(monkeypatch):
    c = client(monkeypatch)
    stale = _valid_payload(base_revision="cap:" + "c" * 64)
    response = c.post(f"/api/projects/{api.PROJECT_ID}/capabilities/compose", json=stale)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "CAPABILITY_REVISION_STALE"
    current = c.get(f"/api/projects/{api.PROJECT_ID}/capabilities/catalog").json()["capability_revision"]
    bad = _valid_payload(base_revision=current)
    bad["nodes"][2]["method_id"] = "not-a-card"
    response = c.post(f"/api/projects/{api.PROJECT_ID}/capabilities/compose", json=bad)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "CAPABILITY_REF_INVALID"


def test_message_can_carry_assembly_metadata_without_becoming_verified(monkeypatch):
    c = client(monkeypatch)
    base = c.get(f"/api/projects/{api.PROJECT_ID}/snapshot").json()["revision"]
    response = c.post(f"/api/projects/{api.PROJECT_ID}/messages", json={
        "text": "装配链待独立复核",
        "base_revision": base,
        "assembly_revision": "assembly:" + "d" * 64,
        "capability_revision": "cap:" + "b" * 64,
        "idempotency_key": "assembly-message-1",
    })
    assert response.status_code == 200
    record = c.get(f"/api/projects/{api.PROJECT_ID}/snapshot").json()["messages"][0]
    assert record["assembly_revision"].startswith("assembly:")
    assert record["capability_revision"].startswith("cap:")
    assert record["status"] == "UNVERIFIED"


def test_compose_returns_diff_and_required_gate(monkeypatch):
    c = client(monkeypatch)
    catalog = c.get(f"/api/projects/{api.PROJECT_ID}/capabilities/catalog").json()
    payload = _valid_payload(catalog["capability_revision"])
    payload["previous_nodes"] = payload["nodes"][:4]
    payload["previous_edges"] = payload["edges"][:4]
    body = c.post(f"/api/projects/{api.PROJECT_ID}/capabilities/compose", json=payload).json()
    assert body["diff"]["changed"] is True
    assert body["diff"]["missing_required_blocks"] == []
    assert set(body["validation"]["required_block_ids"]) == {"problem-decomposition", "baseline-model", "validation", "writing"}


def test_commit_persists_assembly_and_emits_sync_event(monkeypatch):
    c = client(monkeypatch)
    catalog = c.get(f"/api/projects/{api.PROJECT_ID}/capabilities/catalog").json()
    payload = _valid_payload(catalog["capability_revision"])
    composed = c.post(f"/api/projects/{api.PROJECT_ID}/capabilities/compose", json=payload).json()
    payload.update({
        "assembly_revision": composed["assembly_revision"],
        "capability_revision": composed["catalog_revision"],
        "action": "SUBMIT_REVIEW",
        "base_revision": c.get(f"/api/projects/{api.PROJECT_ID}/snapshot").json()["revision"],
        "idempotency_key": "assembly-commit-api-1",
    })
    response = c.post(f"/api/projects/{api.PROJECT_ID}/capabilities/commit", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["event"]["type"] == "ASSEMBLY_UPDATED"
    snapshot = c.get(f"/api/projects/{api.PROJECT_ID}/snapshot").json()
    assert snapshot["assembly"]["assembly_revision"] == composed["assembly_revision"]
    events = c.get(f"/api/projects/{api.PROJECT_ID}/events").json()["events"]
    assert any(item["type"] == "ASSEMBLY_UPDATED" for item in events)


def test_problem_contract_route_keeps_dynamic_draft_unverified(monkeypatch):
    c = client(monkeypatch)
    response = c.post(f"/api/projects/{api.PROJECT_ID}/capabilities/problem-contract", json={
        "text": "问题一：根据数据预测 y。\n问题二：在约束下优化方案，并验证敏感性。",
        "source_refs": ["kbdoc:kbdoc_aaaaaaaaaaaaaaaa"],
    })
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "DRAFT_UNVERIFIED"
    assert len(body["subproblems"]) == 2
    assert body["archetype_cue_suggestions"][0]["claim_class"] == "hypothesis"


def test_innovation_card_is_hashed_audited_and_persisted_as_hypothesis(monkeypatch):
    c = client(monkeypatch)
    catalog = c.get(f"/api/projects/{api.PROJECT_ID}/capabilities/catalog").json()
    payload = _valid_payload(catalog["capability_revision"])
    payload["innovation_card"] = {
        "baseline": "线性回归 + 固定切分",
        "difference": "加入滚动窗口和约束扰动",
        "necessity": "题面存在时间漂移与资源边界",
        "boundary": "样本外分布变化时退回 baseline",
        "validation": "rolling-backtest；约束违反率阈值 5%",
        "subproblem_id": "Q1",
        "claim_class": "verified",
    }
    composed = c.post(f"/api/projects/{api.PROJECT_ID}/capabilities/compose", json=payload)
    assert composed.status_code == 200
    body = composed.json()
    assert body["innovation_gate"]["ready"] is True
    assert body["innovation_card"]["claim_class"] == "hypothesis"
    assert body["diff"]["innovation_changed"] is True
    payload.update({
        "assembly_revision": body["assembly_revision"],
        "capability_revision": body["catalog_revision"],
        "action": "SUBMIT_REVIEW",
        "base_revision": c.get(f"/api/projects/{api.PROJECT_ID}/snapshot").json()["revision"],
        "idempotency_key": "innovation-commit-1",
    })
    committed = c.post(f"/api/projects/{api.PROJECT_ID}/capabilities/commit", json=payload)
    assert committed.status_code == 200
    record = c.get(f"/api/projects/{api.PROJECT_ID}/snapshot").json()["assembly"]
    assert record["innovation_card"]["claim_class"] == "hypothesis"
    assert record["innovation_gate"]["status"] == "READY_FOR_REVIEW"


def test_method_block_mismatch_is_a_warning_not_a_hidden_rewrite(monkeypatch):
    c = client(monkeypatch)
    catalog = c.get(f"/api/projects/{api.PROJECT_ID}/capabilities/catalog").json()
    payload = _valid_payload(catalog["capability_revision"])
    payload["nodes"][2]["method_id"] = "linear-programming"
    body = c.post(f"/api/projects/{api.PROJECT_ID}/capabilities/compose", json=payload).json()
    assert body["status"] == "READY_FOR_REVIEW"
    warning = body["method_block_warnings"][0]
    assert warning["selected_block"] == "baseline-model"
    assert warning["suggested_block"] == "optimization"
    assert body["composition"]["nodes"][2]["method_id"] == "linear-programming"


def test_mechanism_simulation_preset_contains_transparent_baseline(monkeypatch):
    c = client(monkeypatch)
    catalog = c.get(f"/api/projects/{api.PROJECT_ID}/capabilities/catalog").json()
    preset = next(item for item in catalog["workflow_presets"] if item["id"] == "mechanism-simulation")
    assert "baseline-model" in preset["block_ids"]


def test_content_packs_are_catalogued_validated_and_part_of_assembly_diff(monkeypatch):
    c = client(monkeypatch)
    catalog = c.get(f"/api/projects/{api.PROJECT_ID}/capabilities/catalog").json()
    assert len(catalog["content_packs"]) >= 5
    payload = _valid_payload(catalog["capability_revision"])
    payload["content_pack_ids"] = ["problem-evidence", "counterexample"]
    payload["previous_content_pack_ids"] = ["paper-template"]
    body = c.post(f"/api/projects/{api.PROJECT_ID}/capabilities/compose", json=payload).json()
    assert body["status"] == "READY_FOR_REVIEW"
    assert body["content_pack_ids"] == ["counterexample", "problem-evidence"]
    assert body["diff"]["content_pack_changed"] is True
    assert body["diff"]["content_pack_added"] == ["counterexample", "problem-evidence"]
    assert body["diff"]["content_pack_removed"] == ["paper-template"]
    payload["content_pack_ids"] = ["not-a-pack"]
    bad = c.post(f"/api/projects/{api.PROJECT_ID}/capabilities/compose", json=payload)
    assert bad.status_code == 422
    assert bad.json()["detail"]["code"] == "CONTENT_PACK_NOT_FOUND"
