#!/usr/bin/env python3
"""Audit a fixed/DYI mathematical-modelling workflow artifact.

This is a read-only structural checker.  It does not run a solver and does not
trust user supplied code.  It accepts the UI's workflow-puzzle/v1 shape and
the repository's stricter workflow-assembly/v2 shape, returning an auditable
report rather than silently repairing a graph.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple


REQUIRED_BLOCKS = {"problem-decomposition", "baseline-model", "validation", "writing"}
RANDOM_METHOD_MARKERS = ("random", "monte", "genetic", "particle", "anneal", "simulation", "stochastic", "sampling")
PORT_TYPES = {
    "problem-decomposition": ({"problem_contract"}, {"subproblems": "subproblems", "evidence": "evidence"}),
    "data-audit": ({"problem_contract"}, {"data_contract": "data_contract"}),
    "parameter-contract": ({"problem_contract", "data_contract"}, {"model_contract": "model_contract"}),
    "scenario-contract": ({"model_contract"}, {"scenario": "scenario"}),
    "baseline-model": ({"data_contract", "model_contract"}, {"baseline_result": "result", "model_contract": "model_contract"}),
    "mechanism-model": ({"model_contract", "scenario"}, {"model_result": "result", "mechanism_contract": "mechanism_contract"}),
    "optimization": ({"model_contract", "scenario"}, {"model_result": "result", "decision": "decision"}),
    "simulation": ({"model_contract", "scenario"}, {"simulation_result": "result"}),
    "validation": ({"result", "model_contract"}, {"validation_report": "validation_report"}),
    "critic-challenger": ({"result", "validation_report"}, {"critique_report": "review"}),
    "sensitivity": ({"result", "model_contract"}, {"sensitivity_report": "validation_report"}),
    "writing": ({"question_map", "validation_report"}, {"paper_contract": "paper_contract"}),
    "defense": ({"paper_contract", "validation_report"}, {"release_pack": "release_pack"}),
}


def _load(path: Path) -> Dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("artifact root must be an object")
    return value


def _nodes(raw: Any) -> Tuple[List[Dict[str, Any]], List[str]]:
    errors: List[str] = []
    if isinstance(raw, Mapping):
        values: List[Dict[str, Any]] = []
        for node_id, block_id in raw.items():
            values.append({"node_id": node_id, "block_id": block_id})
        return values, errors
    if not isinstance(raw, list):
        return [], ["nodes must be an object or list"]
    values = []
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            errors.append(f"node[{index}] must be an object")
            continue
        node = dict(item)
        node.setdefault("node_id", node.get("id"))
        values.append(node)
    return values, errors


def _edge_values(raw: Any) -> Tuple[List[Tuple[str, str, str, str]], List[str]]:
    errors: List[str] = []
    if not isinstance(raw, list):
        return [], ["edges must be a list"]
    result: List[Tuple[str, str, str, str]] = []
    for index, item in enumerate(raw):
        if isinstance(item, Mapping):
            src = item.get("from", item.get("source"))
            src_port = item.get("from_port", item.get("source_port", ""))
            dst = item.get("to", item.get("target"))
            dst_port = item.get("to_port", item.get("target_port", ""))
            row = (src, src_port, dst, dst_port)
        elif isinstance(item, (list, tuple)) and len(item) == 4:
            row = tuple(item)  # type: ignore[assignment]
        else:
            errors.append(f"edge[{index}] must contain source, source_port, target, target_port")
            continue
        if not all(isinstance(value, str) and value for value in row):
            errors.append(f"edge[{index}] has invalid endpoint or port")
            continue
        result.append(row)  # type: ignore[arg-type]
    return result, errors


def _topology(node_ids: Sequence[str], edges: Sequence[Tuple[str, str, str, str]], errors: List[str]) -> List[str]:
    adjacency = {node: [] for node in node_ids}
    indegree = {node: 0 for node in node_ids}
    for src, _, dst, _ in edges:
        if src not in adjacency or dst not in adjacency:
            errors.append(f"unknown_node:{src}->{dst}")
            continue
        adjacency[src].append(dst)
        indegree[dst] += 1
    queue = sorted(node for node, degree in indegree.items() if degree == 0)
    order: List[str] = []
    while queue:
        node = queue.pop(0)
        order.append(node)
        for nxt in sorted(adjacency[node]):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)
                queue.sort()
    if len(order) != len(node_ids):
        errors.append("cycle_detected")
    return order


def _port_map(node: Mapping[str, Any], block_id: str) -> Tuple[set[str], Dict[str, str]]:
    explicit_inputs = node.get("input_ports")
    explicit_outputs = node.get("output_ports")
    if isinstance(explicit_inputs, Mapping) and isinstance(explicit_outputs, Mapping):
        return set(str(k) for k in explicit_inputs), {str(k): str(v) for k, v in explicit_outputs.items()}
    defaults = PORT_TYPES.get(block_id, (set(), {}))
    return set(defaults[0]), dict(defaults[1])


def audit(value: Mapping[str, Any], *, strict: bool = False) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []
    schema = value.get("schema_version", value.get("schema", ""))
    if schema not in {"workflow-assembly/v2", "workflow-puzzle/v1"}:
        errors.append("unsupported schema_version")
    revision = value.get("input_revision", value.get("revision", value.get("catalogRevision")))
    if not isinstance(revision, str) or not revision.strip():
        errors.append("input_revision/revision is required")
    node_list, node_errors = _nodes(value.get("nodes", value.get("assembly", {}).get("nodes") if isinstance(value.get("assembly"), Mapping) else None))
    errors.extend(node_errors)
    ids: List[str] = []
    block_by_node: Dict[str, str] = {}
    node_objects: Dict[str, Mapping[str, Any]] = {}
    for index, node in enumerate(node_list):
        node_id = node.get("node_id")
        block_id = node.get("block_id", node.get("blockId"))
        if not isinstance(node_id, str) or not node_id:
            errors.append(f"node[{index}] missing node_id")
            continue
        if node_id in block_by_node:
            errors.append(f"duplicate_node:{node_id}")
        ids.append(node_id)
        if not isinstance(block_id, str) or not block_id:
            errors.append(f"node[{node_id}] missing block_id")
            continue
        block_by_node[node_id] = block_id
        node_objects[node_id] = node
    edge_raw = value.get("edges")
    if edge_raw is None and isinstance(value.get("assembly"), Mapping):
        edge_raw = value["assembly"].get("edges")
    edges, edge_errors = _edge_values(edge_raw if edge_raw is not None else [])
    errors.extend(edge_errors)
    order = _topology(ids, edges, errors)
    present_blocks = set(block_by_node.values())
    missing = sorted(REQUIRED_BLOCKS - present_blocks)
    errors.extend(f"required_block_missing:{item}" for item in missing)

    incoming: Dict[str, set[str]] = {node: set() for node in ids}
    validation_nodes: set[str] = set()
    writing_nodes: set[str] = set()
    model_nodes: set[str] = set()
    for node_id, block_id in block_by_node.items():
        if block_id == "validation":
            validation_nodes.add(node_id)
        if block_id == "writing":
            writing_nodes.add(node_id)
        if block_id in {"baseline-model", "mechanism-model", "optimization", "simulation"}:
            model_nodes.add(node_id)
        _, outputs = _port_map(node_objects[node_id], block_id)
        for src, src_port, dst, dst_port in edges:
            if src != node_id or dst not in block_by_node:
                continue
            incoming[dst].add(dst_port)
            if src_port not in outputs:
                errors.append(f"unknown_output_port:{src}:{src_port}")
            dst_inputs, _ = _port_map(node_objects[dst], block_by_node[dst])
            if dst_port not in dst_inputs:
                errors.append(f"unknown_input_port:{dst}:{dst_port}")
            elif src_port in outputs and outputs[src_port] != "any":
                # Destination port type is inferred from explicit mapping when
                # available; built-ins use names as semantic types below.
                dst_type = (node_objects[dst].get("input_port_types", {}) or {}).get(dst_port)
                if dst_type and dst_type != outputs[src_port]:
                    errors.append(f"port_type_mismatch:{src}.{src_port}->{dst}.{dst_port}")
    for node_id, block_id in block_by_node.items():
        required_inputs, _ = _port_map(node_objects[node_id], block_id)
        if block_id != "problem-decomposition":
            missing_inputs = sorted(required_inputs - incoming[node_id])
            # For custom blocks, no built-in port list means no false positives.
            if block_id in PORT_TYPES:
                errors.extend(f"required_input_missing:{node_id}:{port}" for port in missing_inputs)
    # Evidence chain: at least one model feeds validation, and validation feeds
    # writing.  Reachability is checked independently from port names.
    adjacency = {node: [] for node in ids}
    for src, _, dst, _ in edges:
        if src in adjacency and dst in adjacency:
            adjacency[src].append(dst)
    reachable_from_models: set[str] = set()
    stack = list(model_nodes)
    while stack:
        current = stack.pop()
        for nxt in adjacency[current]:
            if nxt not in reachable_from_models:
                reachable_from_models.add(nxt)
                stack.append(nxt)
    if validation_nodes and not validation_nodes.intersection(reachable_from_models):
        errors.append("evidence_chain_missing:model_to_validation")
    reachable_from_validation: set[str] = set()
    stack = list(validation_nodes)
    while stack:
        current = stack.pop()
        for nxt in adjacency[current]:
            if nxt not in reachable_from_validation:
                reachable_from_validation.add(nxt)
                stack.append(nxt)
    if writing_nodes and not writing_nodes.intersection(reachable_from_validation):
        errors.append("evidence_chain_missing:validation_to_writing")

    # A selected method is required for a reviewable composition.  A draft may
    # intentionally leave it blank, but strict mode reports a blocker.
    unselected = [node for node, obj in node_objects.items() if not obj.get("method_id", obj.get("methodId"))]
    if unselected:
        warnings.append("unselected_nodes:" + ",".join(sorted(unselected)))
    evidence_refs = value.get("evidence_refs", value.get("evidenceRefs", []))
    if not isinstance(evidence_refs, list):
        errors.append("evidence_refs must be a list")
        evidence_refs = []
    if not evidence_refs:
        warnings.append("no_evidence_refs")
    # Explicitly reject known unsafe flags rather than trying to sanitize them.
    flags = value.get("flags", {})
    if isinstance(flags, Mapping):
        if flags.get("uses_future_information") or flags.get("future_information"):
            errors.append("future_information_forbidden")
        if flags.get("unknown_code_execution") or flags.get("exec_unknown_code"):
            errors.append("unknown_code_execution_forbidden")
        if flags.get("write_outside_boundary") or flags.get("越权写入"):
            errors.append("write_boundary_violation")
    for node_id, obj in node_objects.items():
        method = str(obj.get("method_id", obj.get("methodId", ""))).lower()
        block = str(block_by_node[node_id]).lower()
        if any(marker in method or marker in block for marker in RANDOM_METHOD_MARKERS):
            config = obj.get("config", {})
            seeds = config.get("seeds", config.get("seed")) if isinstance(config, Mapping) else None
            if seeds in (None, "", []):
                warnings.append(f"random_seed_missing:{node_id}")

    status = str(value.get("status", "DRAFT")).upper()
    action = str(value.get("action", "")).upper()
    if strict and warnings:
        errors.extend(warnings)
    if action in {"SUBMIT_REVIEW", "RELEASE", "RELEASED"} and (errors or status in {"DRAFT", "BLOCKED", "PENDING_RESOLUTION"}):
        errors.append("release_action_requires_clean_verified_artifact")
    unique_errors = list(dict.fromkeys(errors))
    return {
        "schema_version": "workflow-audit/v2",
        "valid": not unique_errors,
        "status": "READY_FOR_REVIEW" if not unique_errors and not warnings else ("BLOCKED" if unique_errors else "DRAFT"),
        "errors": unique_errors,
        "warnings": list(dict.fromkeys(warnings)),
        "node_count": len(block_by_node),
        "edge_count": len(edges),
        "topological_order": order,
        "present_block_ids": sorted(present_blocks),
        "required_block_ids": sorted(REQUIRED_BLOCKS),
        "missing_required_blocks": missing,
        "unselected_nodes": sorted(unselected),
        "revision": revision,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)
    try:
        value = _load(args.artifact)
        result = audit(value, strict=args.strict)
    except Exception as exc:
        result = {"schema_version": "workflow-audit/v2", "valid": False, "errors": [str(exc)], "warnings": []}
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"valid={result['valid']} status={result.get('status','BLOCKED')}")
        for label in ("errors", "warnings"):
            for item in result.get(label, []):
                print(f"{label[:-1].upper()}: {item}")
    return 0 if result.get("valid") else 1


if __name__ == "__main__":
    raise SystemExit(main())
