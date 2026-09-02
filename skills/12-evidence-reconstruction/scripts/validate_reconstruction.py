#!/usr/bin/env python3
"""Validate a general evidence-reconstruction/v2 artifact.

The historical seven-step v1 contract remains available for regression.  This
validator handles exports with a variable number of steps and makes the
observed/inferred boundary explicit.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence


SCHEMA = "evidence-reconstruction/v2"
LEVELS = {"observed", "inferred", "hypothesis"}
STATUSES = {"DRAFT", "READY_FOR_REVIEW", "ACCEPTED", "BLOCKED", "PENDING_RESOLUTION"}
SHA_RE = re.compile(r"^(?:sha256:)?[0-9a-fA-F]{64}$")


def _load(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError("root must be an object")
    return value


def validate(data: Mapping[str, Any], *, strict: bool = False) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []
    if data.get("schema_version") != SCHEMA:
        errors.append(f"schema_version must be {SCHEMA}")
    for key in ("source_artifact", "source_kind", "input_revision", "status", "steps"):
        if key not in data:
            errors.append(f"missing root field: {key}")
    if data.get("status") not in STATUSES:
        errors.append("status is invalid")
    source_hash = data.get("source_sha256")
    if source_hash is not None and (not isinstance(source_hash, str) or not SHA_RE.fullmatch(source_hash)):
        errors.append("source_sha256 must be a SHA-256 digest when present")
    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        errors.append("steps must be a non-empty list")
        steps = []
    ids: set[str] = set()
    orders: List[int] = []
    for index, step in enumerate(steps):
        location = f"steps[{index}]"
        if not isinstance(step, Mapping):
            errors.append(f"{location} must be an object")
            continue
        step_id = step.get("id")
        if not isinstance(step_id, str) or not step_id.strip():
            errors.append(f"{location}.id must be non-empty")
        elif step_id in ids:
            errors.append(f"duplicate step id: {step_id}")
        else:
            ids.add(step_id)
        order = step.get("order")
        if not isinstance(order, int) or isinstance(order, bool):
            errors.append(f"{location}.order must be integer")
        else:
            orders.append(order)
        for key in ("inputs", "outputs", "responsibilities", "method_chain", "validation_gates", "evidence_refs", "open_questions"):
            value = step.get(key)
            if not isinstance(value, list):
                errors.append(f"{location}.{key} must be a list")
            elif key != "open_questions" and not value:
                warnings.append(f"{location}.{key} is empty")
        levels = step.get("evidence_levels", step.get("claim_levels", []))
        if not isinstance(levels, list):
            errors.append(f"{location}.evidence_levels must be a list")
        else:
            unknown = sorted(set(str(item).lower() for item in levels) - LEVELS)
            if unknown:
                errors.append(f"{location} has invalid evidence levels: {unknown}")
        if step.get("status") in {"VERIFIED", "ACCEPTED"} and any(
            str(item).lower() != "observed" for item in (step.get("evidence_levels") or [])
        ):
            warnings.append(f"{location}: accepted status contains non-observed evidence")
        handoffs = step.get("handoff_to", [])
        if not isinstance(handoffs, list):
            errors.append(f"{location}.handoff_to must be a list")
        else:
            for target in handoffs:
                if not isinstance(target, str) or not target.strip():
                    errors.append(f"{location}.handoff_to contains an empty target")
        if not isinstance(step.get("failure_policy"), str) or not step["failure_policy"].strip():
            errors.append(f"{location}.failure_policy is required")
    if orders and sorted(orders) != list(range(min(orders), min(orders) + len(orders))):
        errors.append("step orders must be contiguous")
    known = ids
    for index, step in enumerate(steps):
        if not isinstance(step, Mapping):
            continue
        for target in step.get("handoff_to", []) if isinstance(step.get("handoff_to"), list) else []:
            if target not in known:
                errors.append(f"steps[{index}] handoff target unknown: {target!r}")
    unresolved = data.get("unresolved", data.get("open_questions", []))
    if not isinstance(unresolved, list):
        errors.append("unresolved/open_questions must be a list")
    if data.get("status") in {"ACCEPTED"} and unresolved:
        warnings.append("accepted artifact still has unresolved items")
    if strict and warnings:
        errors.extend(warnings)
    unique_errors = list(dict.fromkeys(errors))
    return {
        "schema_version": "evidence-reconstruction-validation/v1",
        "valid": not unique_errors,
        "status": "READY_FOR_REVIEW" if not unique_errors and not warnings else ("BLOCKED" if unique_errors else "PENDING_RESOLUTION"),
        "errors": unique_errors,
        "warnings": list(dict.fromkeys(warnings)),
        "step_count": len(steps),
        "step_ids": sorted(ids),
        "input_revision": data.get("input_revision"),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)
    try:
        result = validate(_load(args.artifact), strict=args.strict)
    except Exception as exc:
        result = {"schema_version": "evidence-reconstruction-validation/v1", "valid": False, "errors": [str(exc)], "warnings": []}
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"valid={result['valid']} status={result.get('status','BLOCKED')} steps={result.get('step_count',0)}")
        for label in ("errors", "warnings"):
            for item in result.get(label, []):
                print(f"{label[:-1].upper()}: {item}")
    return 0 if result.get("valid") else 1


if __name__ == "__main__":
    raise SystemExit(main())
