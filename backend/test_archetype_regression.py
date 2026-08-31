"""Regression checks for the four primary standard workflow archetypes.

These tests exercise the public compose contract with deterministic metadata.
They intentionally place the baseline before family-specific blocks so every
family block receives its required ``model`` port.
"""

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
        "facets": {"modules": {}, "kinds": {}, "extensions": {}, "years": {}},
        "warnings": ["deterministic archetype regression snapshot"],
    }


def _auto_link(nodes, blocks):
    edges = []
    for target_index, target_node in enumerate(nodes):
        target = blocks[target_node["block_id"]]
        for target_port, target_type in target.get("input_ports", {}).items():
            for source_node in reversed(nodes[:target_index]):
                source = blocks[source_node["block_id"]]
                match = next(
                    (port for port, value in source.get("output_ports", {}).items() if value == target_type),
                    None,
                )
                if match:
                    edges.append(
                        {
                            "source": source_node["node_id"],
                            "source_port": match,
                            "target": target_node["node_id"],
                            "target_port": target_port,
                        }
                    )
                    break
    return edges


def test_primary_archetypes_have_valid_standard_compositions(monkeypatch):
    monkeypatch.setattr(api, "store", api.EventStore())
    monkeypatch.setattr(api.knowledge_base, "summary", lambda force_refresh=False: dict(_summary()))
    client = TestClient(api.app)
    catalog = client.get(f"/api/projects/{api.PROJECT_ID}/capabilities/catalog").json()
    blocks = {item["id"]: item for item in catalog["workflow_blocks"]}
    methods = {item["id"]: item for item in catalog["methods"]}
    family_methods = {
        "prediction": "linear-regression",
        "optimization": "linear-programming",
        "mechanism": "runge-kutta-ode",
        "simulation": "monte-carlo",
    }
    family_blocks = {
        "prediction": ["baseline-model"],
        "optimization": ["optimization"],
        "mechanism": ["scenario-contract", "mechanism-model", "simulation"],
        "simulation": ["scenario-contract", "simulation"],
    }
    for archetype, method_id in family_methods.items():
        # Baseline precedes any family block that consumes a model.
        block_ids = [
            "problem-decomposition",
            "data-audit",
            "parameter-contract",
            "baseline-model",
            *([item for item in family_blocks[archetype] if item != "baseline-model"]),
            "validation",
            "critic-challenger",
            "sensitivity",
            "writing",
        ]
        if archetype in {"mechanism", "simulation"}:
            block_ids.append("defense")
        nodes = [
            {
                "node_id": f"{block_id}-{index + 1}",
                "block_id": block_id,
                "method_id": method_id if block_id == ("mechanism-model" if archetype == "mechanism" else "simulation" if archetype == "simulation" else "optimization" if archetype == "optimization" else "baseline-model") else None,
                "label": block_id,
                "config": {},
            }
            for index, block_id in enumerate(block_ids)
        ]
        response = client.post(
            f"/api/projects/{api.PROJECT_ID}/capabilities/compose",
            json={
                "nodes": nodes,
                "edges": _auto_link(nodes, blocks),
                "preset_id": "standard-cumcm",
                "archetype_id": archetype,
                "scope": ["Q1"],
                "base_revision": catalog["capability_revision"],
                "idempotency_key": f"archetype-regression-{archetype}",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "READY_FOR_REVIEW", (archetype, body)
        assert body["validation"]["valid"] is True
        assert body["validation"]["missing_required_blocks"] == []
        assert body["validation"]["hard_gate"]["ready"] is True

