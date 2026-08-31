"""Independent tests for the pure modelling capability catalogue."""

import pytest

try:
    from capability_catalog import (
        BUILTIN_BLOCKS,
        BUILTIN_METHODS,
        compose_workflow,
        metadata_snapshot_to_catalog,
        validate_composition,
    )
except ImportError:  # pragma: no cover
    from backend.capability_catalog import (
        BUILTIN_BLOCKS,
        BUILTIN_METHODS,
        compose_workflow,
        metadata_snapshot_to_catalog,
        validate_composition,
    )


def test_catalog_projects_metadata_without_scanning_or_executing():
    catalog = metadata_snapshot_to_catalog({
        "root_id": "math-modeling-pack", "source_status": "LOCAL_INDEXED",
        "index_revision": "kb:" + "a" * 64, "catalog_consistent": False,
    })
    assert catalog["catalog_version"].startswith("capability-catalog/")
    assert catalog["source"]["index_revision"].startswith("kb:")
    assert len(catalog["methods"]) >= 12
    assert all(item["source_kind"] == "curated/inferred" for item in catalog["methods"])
    assert "not source-text facts" in catalog["source"]["usage_note"]


def test_builtin_method_cards_have_modeling_interfaces_and_evidence_refs():
    assert len(BUILTIN_METHODS) >= 12
    ids = {card.id for card in BUILTIN_METHODS}
    assert {"linear-regression", "linear-programming", "finite-difference-pde", "monte-carlo"} <= ids
    for card in BUILTIN_METHODS:
        assert card.inputs and card.outputs and card.validation and card.fallback
        assert card.assumptions and card.prohibitions
        assert card.evidence_refs and card.evidence_refs[0].startswith("playbook:")


def valid_nodes():
    return {
        "q": "problem-decomposition",
        "data": "data-audit",
        "base": "baseline-model",
        "check": "validation",
        "paper": "writing",
    }


def valid_edges():
    return [
        ("q", "subproblems", "base", "subproblem"),
        ("q", "subproblems", "paper", "subproblems"),
        ("data", "data_contract", "base", "data_contract"),
        ("base", "model", "check", "model"),
        ("base", "result", "check", "result"),
        ("base", "result", "paper", "result"),
        ("check", "validation_report", "paper", "validation_report"),
    ]


def test_valid_composition_is_acyclic_port_matched_and_evidence_linked():
    report = validate_composition(valid_nodes(), valid_edges())
    assert report["valid"] is True
    assert report["errors"] == []
    assert set(report["topological_order"]) == set(valid_nodes())
    result = compose_workflow(valid_nodes(), valid_edges())
    assert result["validation"]["valid"] is True


def test_composition_rejects_port_mismatch():
    edges = valid_edges() + [("q", "evidence", "base", "data_contract")]
    report = validate_composition(valid_nodes(), edges)
    assert report["valid"] is False
    assert any(error.startswith("port_type_mismatch:") for error in report["errors"])
    with pytest.raises(ValueError, match="invalid workflow composition"):
        compose_workflow(valid_nodes(), edges)


def test_composition_rejects_cycle():
    nodes = {"base": "baseline-model", "check": "validation"}
    edges = [("base", "model", "check", "model"), ("base", "result", "check", "result"), ("check", "validation_report", "base", "data_contract")]
    report = validate_composition(nodes, edges)
    assert report["valid"] is False
    assert any(error.startswith("cycle:") for error in report["errors"])


def test_composition_requires_validation_and_evidence_chain_to_writing():
    nodes = {"q": "problem-decomposition", "data": "data-audit", "base": "baseline-model", "paper": "writing"}
    edges = [("q", "subproblems", "paper", "subproblems"), ("data", "data_contract", "base", "data_contract"), ("base", "result", "paper", "result")]
    report = validate_composition(nodes, edges)
    assert report["valid"] is False
    assert "required_validation_node_missing" in report["errors"]
    assert "evidence_chain_missing:validation_to_writing" in report["errors"]


def test_composition_rejects_missing_required_model_input():
    nodes = {"q": "problem-decomposition", "check": "validation"}
    edges = []
    report = validate_composition(nodes, edges)
    assert report["valid"] is False
    assert "required_input_missing:check:model" in report["errors"]
    assert "required_input_missing:check:result" in report["errors"]


def test_unknown_block_and_node_are_fail_closed():
    report = validate_composition({"q": "not-a-block"}, [("q", "out", "ghost", "in")])
    assert report["valid"] is False
    assert "unknown_block:q:not-a-block" in report["errors"]
    assert "unknown_node:q->ghost" in report["errors"]


def test_empty_snapshot_is_unavailable_but_still_has_catalog():
    catalog = metadata_snapshot_to_catalog(None)
    assert catalog["source"]["source_status"] == "UNAVAILABLE"
    assert catalog["workflow_blocks"]
    assert catalog["problem_archetypes"]
